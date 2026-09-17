# -*- coding: utf-8 -*-
"""一键送校验 / 导入通过项：argv 组装、报告判定、入库改名平展。"""
import json
import os
import shutil
import subprocess
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

    def _patch_common(self):
        win = self.win
        real_box = win._wrap_box
        real_prog = win._make_progress
        boxes = []
        win._wrap_box = lambda *a, **k: boxes.append(a) or None
        win._make_progress = lambda title, total: (
            None, lambda *a, **k: True, {"finish": lambda *a, **k: None})
        def restore():
            win._wrap_box = real_box
            win._make_progress = real_prog
        return boxes, restore

    def test_send_builds_argv(self):
        win = self.win
        boxes, restore = self._patch_common()
        calls = []
        real_popen = subprocess.Popen
        subprocess.Popen = lambda argv, **k: calls.append((list(argv), k)) or None
        try:
            win._send_coll_to_verify()
        finally:
            subprocess.Popen = real_popen
            restore()
        self.assertEqual(len(calls), 1)
        argv, kw = calls[0]
        self.assertEqual(argv[1:3], ["-m", "pycbeta.gui"])
        self.assertIn("--verify", argv)
        self.assertIn("--autostart", argv)
        self.assertNotIn("--preset", argv)   # 出厂默认不传
        self.assertEqual(argv[argv.index("--formats") + 1], "pdf")   # 随右栏勾选
        ids = Path(argv[argv.index("--ids-file") + 1])
        self.assertEqual(ids.read_text(encoding="utf-8").split(), ["T0001", "T0002"])
        self.assertEqual(Path(argv[argv.index("--out") + 1]),
                         Path(win.config["verify_dir"]) / "v")
        self.assertTrue(any("已送" in str(a) for a in boxes))

    def test_send_blocks_on_tmp_preset(self):
        win = self.win
        boxes, restore = self._patch_common()
        calls = []
        real_popen = subprocess.Popen
        subprocess.Popen = lambda *a, **k: calls.append(a) or None
        win._tmp_preset = Path(self.tmp / "tmp.json")
        try:
            win._send_coll_to_verify()
        finally:
            del win._tmp_preset
            subprocess.Popen = real_popen
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
        self.assertTrue(any("入库 1 部" in str(a) for a in boxes), boxes)

    def test_import_no_reports(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        vdir = b.verify_coll_dir(self.win.config, "v")
        shutil.rmtree(vdir, ignore_errors=True)
        vdir.mkdir(parents=True)
        boxes, restore = self._patch_common()
        try:
            self.win._import_verified()
        finally:
            restore()
        self.assertTrue(any("暂无校验" in str(a) for a in boxes))


if __name__ == "__main__":
    unittest.main()
