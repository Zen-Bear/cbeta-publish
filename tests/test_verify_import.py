# -*- coding: utf-8 -*-
"""进程内生成并校验 / 自动+手动导入：报告判定、两种命名、入库改名、argv。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    col = tmp / "collections" / "custom"
    col.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class VerifyReportTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _rp(self, text):
        p = self.dir / "S_verify_report.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_ok_only_passes(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        p = self._rp("=== T0001\n  [OK]  docx 缺0 多0\n")
        self.assertTrue(b.verify_report_pass(p))

    def test_fail_blocks(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        p = self._rp("=== T0001\n  [OK]  docx 缺0 多0\n  [FAIL] txt_notes 缺3 多1\n")
        self.assertFalse(b.verify_report_pass(p))

    def test_neutral_is_undetermined(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        p = self._rp("=== T0001\n  [--]  pdf covered by docx\n")
        self.assertIsNone(b.verify_report_pass(p))
        self.assertIsNone(b.verify_report_pass(self.dir / "nope.txt"))


class VerifySendImportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        win = cls.win
        win.config["verify_dir"] = str(cls.tmp / "vf")
        win.config["xml_to_ebooks_dir"] = str(cls.tmp / "xb")
        (cls.tmp / "x2p").mkdir()
        win.config["xml2pdf"]["path"] = str(cls.tmp / "x2p")
        win.config["xml2pdf"]["preset"] = ""
        col = Path(win.config["collections_dir"]) / "custom" / "验测.json"
        col.write_text(json.dumps({"id": "v", "name": "验测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001", "T0002"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("验测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # 每个用例独立：清校验目录与自制书目录
        from cbeta_publish.books import xml2pdf_bridge as b
        shutil.rmtree(b.verify_coll_dir(self.win.config, "v"), ignore_errors=True)
        shutil.rmtree(Path(self.win.config["xml_to_ebooks_dir"]), ignore_errors=True)

    def _patch_common(self):
        win = self.win
        real_box = win._wrap_box
        real_prog = win._make_progress
        boxes = []
        self._finishes = []
        win._wrap_box = lambda *a, **k: boxes.append(a) or None

        def fake_prog(title, total):
            def finish(lines=None, *a, **k):
                self._finishes.append([str(x) for x in (lines or [])])
            return None, (lambda *a, **k: True), {"finish": finish}
        win._make_progress = fake_prog

        def restore():
            win._wrap_box = real_box
            win._make_progress = real_prog
        return boxes, restore

    def _patch_verify(self, verdict_lines="=== T0001\n  [OK]  docx 缺0 多0\n"):
        """替换 bridge.verify_work：写出报告与产物，模拟进程内校验成功。"""
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b.verify_work
        calls = []

        def fake(work, fmts, out_dir, config, preset=None, stop=None):
            calls.append((work, list(fmts), str(out_dir)))
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{work} 大般若經.pdf").write_bytes(b"PDF")
            vd = out / f"{work} 大般若經（验证）"
            vd.mkdir(parents=True, exist_ok=True)
            rp = vd / "report.txt"
            rp.write_text(verdict_lines, encoding="utf-8")
            return rp
        b.verify_work = fake
        return calls, lambda: setattr(b, "verify_work", real)

    def test_send_runs_inprocess_and_autoimports(self):
        win = self.win
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(False)
        boxes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        try:
            win._send_coll_to_verify()
        finally:
            restore_v()
            restore()
        self.assertEqual(len(calls), 2)                     # 逐本调用
        self.assertEqual(calls[0][1], ["pdf"])              # 随右栏勾选
        self.assertEqual(calls[0][2], str(Path(win.config["verify_dir"]) / "v"))
        base = Path(win.config["xml_to_ebooks_dir"])
        self.assertEqual((base / "pdf" / "T0001.pdf").read_bytes(), b"PDF")  # 自动导入
        self.assertTrue((base / "pdf" / "T0002.pdf").exists())

    def test_send_reports_failure(self):
        # 报告含 [FAIL] → 不入库
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        boxes, restore = self._patch_common()
        calls, restore_v = self._patch_verify("=== T0001\n  [FAIL] docx 缺3 多1\n")
        base = Path(win.config["xml_to_ebooks_dir"])
        for w in ("T0001", "T0002"):
            (base / "pdf" / f"{w}.pdf").unlink(missing_ok=True)
        try:
            win._send_coll_to_verify()
        finally:
            restore_v()
            restore()
        self.assertFalse((base / "pdf" / "T0001.pdf").exists())

    def test_send_blocks_on_tmp_preset(self):
        win = self.win
        boxes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        win._tmp_preset = Path(self.tmp / "tmp.json")
        try:
            win._send_coll_to_verify()
        finally:
            del win._tmp_preset
            restore_v()
            restore()
        self.assertEqual(calls, [])
        self.assertTrue(any("临时预设" in str(a) for a in boxes))

    def _mk_verify_tree(self):
        # 真实上游布局：正式产物在顶层 `{id 书名}.{fmt}`；
        # 报告与对比物在 `{id 书名}（验证）/`，报告名 stem=work id
        from cbeta_publish.books import xml2pdf_bridge as b
        vdir = b.verify_coll_dir(self.win.config, "v")
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.pdf").write_bytes(b"PDF")
        (vdir / "T0001 大般若經.docx").write_bytes(b"DOCX")
        vd1 = vdir / "T0001 大般若經（验证）"
        vd1.mkdir(parents=True, exist_ok=True)
        (vd1 / "T0001_verify_report.txt").write_text(
            "=== T0001\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
        (vdir / "T0002 X.epub").write_bytes(b"EPUB")
        vd2 = vdir / "T0002 X（验证）"
        vd2.mkdir(parents=True, exist_ok=True)
        (vd2 / "T0002_verify_report.txt").write_text(
            "=== T0002\n  [FAIL] txt_notes 缺3 多1\n", encoding="utf-8")
        return vdir

    def test_import_pass_only(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        vdir = self._mk_verify_tree()
        boxes, restore = self._patch_common()
        try:
            self.win._import_verified()
        finally:
            restore()
        base = Path(self.win.config["xml_to_ebooks_dir"])
        self.assertEqual((base / "pdf" / "T0001.pdf").read_bytes(), b"PDF")    # 通过入库改名
        self.assertEqual((base / "docx" / "T0001.docx").read_bytes(), b"DOCX")  # 多格式都入
        self.assertFalse((base / "epub" / "T0002.epub").exists())               # 未通过不入库
        self.assertTrue(any("入库 1 部" in x for f in self._finishes for x in f),
                        self._finishes)

    def test_import_no_reports_cancel(self):
        # 本丛书校验目录无报告 → 弹目录选择；取消则什么都不做
        from PySide6.QtWidgets import QFileDialog
        from cbeta_publish.books import xml2pdf_bridge as b
        vdir = b.verify_coll_dir(self.win.config, "v")
        shutil.rmtree(vdir, ignore_errors=True)
        real = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
        boxes, restore = self._patch_common()
        try:
            self.win._import_verified()
        finally:
            QFileDialog.getExistingDirectory = real
            restore()
        self.assertEqual(boxes, [])

    def test_import_from_chosen_dir(self):
        # 选另一个目录（模拟独立窗输出）→ 递归识别报告并入自制书目录
        from PySide6.QtWidgets import QFileDialog
        other = Path(tempfile.mkdtemp())
        try:
            (other / "T0001 大般若經.pdf").write_bytes(b"PDF")
            vd = other / "T0001 大般若經（验证）"
            vd.mkdir(parents=True)
            (vd / "T0001_verify_report.txt").write_text(
                "=== T0001\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
            real = QFileDialog.getExistingDirectory
            QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(other))
            boxes, restore = self._patch_common()
            try:
                self.win._import_verified()
            finally:
                QFileDialog.getExistingDirectory = real
                restore()
            base = Path(self.win.config["xml_to_ebooks_dir"])
            self.assertEqual((base / "pdf" / "T0001.pdf").read_bytes(), b"PDF")
        finally:
            shutil.rmtree(other, ignore_errors=True)


class VerifyRulesDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_rules_text_covers_spec(self):
        txt = self.win._verify_rules_text()
        for key in ("（验证）", "[FAIL]", "[OK]", "{fmt}/{work}", "目录选择",
                    "_verify_report.txt", "report.txt", "顶层"):
            self.assertIn(key, txt)

    def test_menu_has_rules_action(self):
        menus = [a for a in self.win.menuBar().actions()
                 if a.text().replace("&", "") == "自制书籍"]
        self.assertEqual(len(menus), 1)
        acts = [a.text() for a in menus[0].menu().actions()]
        self.assertIn("独立窗输出与导入规则…", acts)


class ExitCleanupTest(unittest.TestCase):
    """退出精确清理：临时预设删除、在途 wrapper 兜底删除、校验线程停止。"""

    def test_close_deletes_transient_preset_and_live_wrappers(self):
        import tempfile
        from PySide6.QtGui import QCloseEvent
        import cbeta_publish.books.xml2pdf_bridge as b
        saved_live = set(b._LIVE_TEMP_FILES)
        b._LIVE_TEMP_FILES.clear()
        win, tmp = _make_window()
        try:
            self.assertFalse(win._coll_changed)
            fd, preset = tempfile.mkstemp(prefix="cbeta-publish-preset-", suffix=".json")
            os.close(fd)
            win._tmp_preset = Path(preset)
            b._track_temp(preset)
            fd2, wrap = tempfile.mkstemp(prefix="cbeta-publish-run-", suffix=".json")
            os.close(fd2)
            b._track_temp(wrap)
            calls = []

            class _W:
                def isRunning(self):
                    return True

                def stop(self):
                    calls.append("stop")

                def wait(self, ms=None):
                    calls.append(("wait", ms))
                    return True

            win._verify_worker = _W()
            ev = QCloseEvent()
            win.closeEvent(ev)
            self.assertTrue(ev.isAccepted())
            self.assertFalse(Path(preset).exists())
            self.assertFalse(Path(wrap).exists())
            self.assertIsNone(win._tmp_preset)
            self.assertIn("stop", calls)
            self.assertEqual(b._LIVE_TEMP_FILES, set())
        finally:
            b._LIVE_TEMP_FILES.clear()
            b._LIVE_TEMP_FILES.update(saved_live)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
