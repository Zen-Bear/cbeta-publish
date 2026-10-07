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

    def test_new_naming_scanned_with_underscore_stem(self):
        # 新命名 {id}_{书名}_校验报告.txt：能扫到，stem 保留下划线部分
        from cbeta_publish.books import xml2pdf_bridge as b
        vd = self.dir / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True)
        (vd / "T0001_长阿含经_校验报告.txt").write_text(
            "=== T0001\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
        got = b.verify_reports(self.dir)
        self.assertEqual(len(got), 1)
        rp, stem = got[0]
        self.assertEqual(stem, "T0001_长阿含经")
        self.assertTrue(b._verify_stem_matches(stem, "T0001"))
        self.assertFalse(b._verify_stem_matches(stem, "T0002"))

    def test_same_dir_old_new_dedupe_newest(self):
        # 同一验证目录新旧命名并存：只取最新一份
        import os
        from cbeta_publish.books import xml2pdf_bridge as b
        vd = self.dir / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True)
        old = vd / "report.txt"
        new = vd / "T0001_长阿含经_校验报告.txt"
        old.write_text("=== T0001\n  [FAIL]  docx 缺3 多1\n", encoding="utf-8")
        new.write_text("=== T0001\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
        os.utime(old, (1000, 1000))
        os.utime(new, (2000, 2000))
        got = b.verify_reports(self.dir)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0].name, "T0001_长阿含经_校验报告.txt")
        self.assertTrue(b.verify_report_pass(got[0][0]))

    def test_underscore_match_safety(self):
        # 下划线分隔匹配：T185 不误命中 T1858（要求分隔符对齐）
        from cbeta_publish.books import xml2pdf_bridge as b
        self.assertTrue(b._verify_stem_matches("T185", "T185"))
        self.assertTrue(b._verify_stem_matches("T185_x", "T185"))
        self.assertTrue(b._verify_stem_matches("T185 x", "T185"))
        self.assertFalse(b._verify_stem_matches("T1858_x", "T185"))
        self.assertFalse(b._verify_stem_matches("T185_x", "T1858"))
        self.assertFalse(b._verify_stem_matches("", "T0001"))
        self.assertFalse(b._verify_stem_matches("T0001", ""))

    def test_find_verify_report_new_naming(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        vd = self.dir / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True)
        (vd / "T0001_长阿含经_校验报告.txt").write_text("x", encoding="utf-8")
        self.assertEqual(
            b.find_verify_report(self.dir, "T0001").name,
            "T0001_长阿含经_校验报告.txt")
        (self.dir / "T0002_校验报告.txt").write_text("x", encoding="utf-8")
        self.assertEqual(
            b.find_verify_report(self.dir, "T0002").name, "T0002_校验报告.txt")

    def test_find_verify_report_nested_new_layout(self):
        # 上游新布局：报告在 `{out}/验证/{id 书名}（验证）/`
        from cbeta_publish.books import xml2pdf_bridge as b
        vd = self.dir / b.VERIFY_ROOT_NAME / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True)
        (vd / "T0001_长阿含经_校验报告.txt").write_text("x", encoding="utf-8")
        got = b.find_verify_report(self.dir, "T0001")
        self.assertIsNotNone(got)
        self.assertEqual(got.name, "T0001_长阿含经_校验报告.txt")
        self.assertEqual(got.parent.parent.name, b.VERIFY_ROOT_NAME)

    def test_products_exclude_reports(self):
        # 校验报告（新旧命名）与转换报告都不算 txt 产物
        from cbeta_publish.gui.main_window import MainWindow
        vdir = self.dir / "vprod"
        vdir.mkdir(parents=True)
        prod = vdir / "T0001 长阿含经.txt"
        prod.write_bytes(b"TXT")
        vd = vdir / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True)
        (vd / "T0001_长阿含经_校验报告.txt").write_bytes(b"R")
        (vdir / "T0001 长阿含经_转换报告.txt").write_bytes(b"C")
        got = MainWindow._verify_products(vdir, "T0001")
        self.assertEqual(got, [("txt", prod)])


class VerifyReportJsonTest(unittest.TestCase):
    """`report.json` 优先判读（2026-10-07 统一定名；txt 回退）。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _mk(self, txt="=== T0001\n  [OK]  docx 缺0 多0\n", body=None,
            json_name="report.json"):
        vd = self.dir / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        rp = vd / "report.txt"
        rp.write_text(txt, encoding="utf-8")
        if body is not None:
            text = body if isinstance(body, str) else json.dumps(
                body, ensure_ascii=False)
            (vd / json_name).write_text(text, encoding="utf-8")
        return rp

    def test_json_verdicts_reading(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        rp = self._mk(body={"schema": 1, "fmts": {
            "docx": {"verdict": "pass", "missing": 0, "extra": 0},
            "pdf": {"verdict": "undetermined", "reason": "covered:docx"},
            "epub": {"verdict": "fail", "missing": 48, "extra": 97,
                     "diff_scope": "body"},
            "md": {"verdict": "error", "reason": "verify_error"}}})
        self.assertEqual(b.verify_report_formats(rp),
                         {"docx": True, "epub": False})
        self.assertEqual(b.verify_report_pending(rp),
                         {"pdf": "covered:docx", "md": "verify_error"})
        self.assertEqual(b.verify_report_numbers(rp),
                         {"docx": (0, 0), "epub": (48, 97)})
        self.assertFalse(b.verify_report_pass(rp))
        self.assertEqual(b.verify_report_diff_scopes(rp), {"epub": "body"})
        self.assertEqual(b.verify_json_formats(rp),
                         ["docx", "epub", "md", "pdf"])

    def test_json_wins_over_txt(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        rp = self._mk(txt="=== T0001\n  [FAIL] docx 缺3 多1\n",
                      body={"schema": 1, "fmts": {"docx": {"verdict": "pass"}}})
        self.assertEqual(b.verify_report_formats(rp), {"docx": True})
        self.assertTrue(b.verify_report_pass(rp))

    def test_json_corrupt_or_schema_falls_back(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        for body in ("{not json",
                     {"schema": 2, "fmts": {"docx": {"verdict": "fail"}}}):
            rp = self._mk(txt="=== T0001\n  [OK]  docx 缺0 多0\n", body=body)
            self.assertTrue(b.verify_report_pass(rp), body)
            self.assertEqual(b.verify_report_formats(rp), {"docx": True})

    def test_json_coverage_synthesis(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        rp = self._mk(body={"schema": 1,
                            "inputs": {"coverage": {"pdf": "docx"}},
                            "fmts": {"pdf": {"verdict": "undetermined"},
                                     "docx": {"verdict": "pass"}}})
        pending = b.verify_report_pending(rp)
        self.assertEqual(pending.get("pdf"), "covered:docx")
        st = b.apply_verify_coverage(b.verify_report_formats(rp), pending)
        self.assertTrue(st.get("pdf"))

    def test_old_json_name_ignored(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        rp = self._mk(txt="=== T0001\n  [FAIL] docx 缺3 多1\n",
                      body={"schema": 1, "fmts": {"docx": {"verdict": "pass"}}},
                      json_name="T0001_verify_report.json")
        self.assertEqual(b.verify_report_formats(rp), {"docx": False})
        self.assertFalse(b.verify_report_pass(rp))

    def test_comparison_files_exist_filter(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        vd = self.dir / "T0001 长阿含经（验证）"
        vd.mkdir(parents=True)
        cmp_file = vd / "docx" / "T01n0001.docx"
        cmp_file.parent.mkdir()
        cmp_file.write_bytes(b"X")
        rp = self._mk(body={"schema": 1, "fmts": {"docx": {
            "verdict": "fail", "missing": 1, "extra": 0,
            "formal_outputs": [str(cmp_file), str(vd / "docx" / "gone.docx")]}}})
        self.assertEqual(b.verify_report_comparison_files(rp),
                         {"docx": [cmp_file]})
        self.assertEqual(b.verify_report_diff_scopes(rp), {})

    def test_conservative_diff_scope_helpers(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        self.assertEqual(
            b.conservative_diff_scope(["notes_only", "body", "unknown"]), "body")
        self.assertEqual(
            b.conservative_diff_scope(["notes_only", "unknown"]), "unknown")
        self.assertIsNone(b.conservative_diff_scope([None, ""]))
        self.assertEqual(b.diff_scope_text("notes_only"), "差异仅注释")
        self.assertEqual(b.diff_scope_text(None), "")


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
        self.assertEqual((base / "pdf" / "T0001 大般若經.pdf").read_bytes(), b"PDF")  # 自动导入
        self.assertTrue((base / "pdf" / "T0002 大般若經.pdf").exists())

    def test_send_reports_failure(self):
        # 报告含 [FAIL] → 不入库
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        boxes, restore = self._patch_common()
        calls, restore_v = self._patch_verify("=== T0001\n  [FAIL] docx 缺3 多1\n")
        base = Path(win.config["xml_to_ebooks_dir"])
        for w in ("T0001", "T0002"):
            (base / "pdf" / f"{w}.pdf").unlink(missing_ok=True)
            (base / "pdf" / f"{w} 大般若經.pdf").unlink(missing_ok=True)
        try:
            win._send_coll_to_verify()
        finally:
            restore_v()
            restore()
        self.assertFalse((base / "pdf" / "T0001.pdf").exists())
        self.assertFalse((base / "pdf" / "T0001 大般若經.pdf").exists())
        # 未放行且托管目录：暂存 pdf 已删除；review 仍记 fail
        vdir = Path(win.config["verify_dir"]) / "v"
        self.assertFalse((vdir / "T0001 大般若經.pdf").exists())

    def test_make_button_dispatches_to_verify_when_configured(self):
        # 设置「制作书籍=校验」→ 自制/重制 都走校验流程（regen_all 透传）
        win = self.win
        win.config.setdefault("xml2pdf", {})["verify_build"] = True
        called = []
        real = win._send_coll_to_verify
        win._send_coll_to_verify = lambda regen_all=False: called.append(regen_all)
        try:
            win._on_make_button(False)
            win._on_make_button(True)
        finally:
            win._send_coll_to_verify = real
            win.config["xml2pdf"]["verify_build"] = False
        self.assertEqual(called, [False, True])

    def test_send_missing_only_skips_existing(self):
        # 自制（regen_all=False）+ 复用关：只处理自制书目录里缺少的书
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        win.config.setdefault("xml2pdf", {})["verify_reuse"] = False
        base = Path(win.config["xml_to_ebooks_dir"])
        (base / "pdf").mkdir(parents=True, exist_ok=True)
        (base / "pdf" / "T0001.pdf").write_bytes(b"old")   # T0001 已有 → 跳过
        calls, restore_v = self._patch_verify()
        boxes, restore = self._patch_common()
        try:
            win._send_coll_to_verify(regen_all=False)
        finally:
            restore_v()
            restore()
            win.config["xml2pdf"]["verify_reuse"] = True
        self.assertEqual([c[0] for c in calls], ["T0002"])

    def test_open_window_passes_current_coll(self):
        # 「运行 xml2pdf 制作书籍」：把当前丛书 ids/out/preset 带给独立窗
        import subprocess
        win = self.win
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("验测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()
        calls = []
        real = subprocess.Popen
        subprocess.Popen = lambda argv, **k: calls.append((list(argv), k)) or None
        try:
            win._open_xml2pdf_window()
        finally:
            subprocess.Popen = real
        self.assertEqual(len(calls), 1)
        argv, kw = calls[0]
        self.assertEqual(argv[1:3], ["-m", "pycbeta.gui"])
        ids = Path(argv[argv.index("--ids-file") + 1])
        self.assertEqual(ids.read_text(encoding="utf-8").split(), ["T0001", "T0002"])
        self.assertEqual(Path(argv[argv.index("--out") + 1]).name, "v")
        # 校验根钉死到 {vdir}/验证
        _vr = Path(argv[argv.index("--verify-root") + 1])
        self.assertEqual(_vr.name, "验证")
        self.assertEqual(_vr.parent.name, "v")

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

    def test_import_docx_pass_covers_pdf(self):
        # docx通过即pdf通过：报告 [--] pdf已覆盖 + [OK]docx，即使另有格式[FAIL]
        #（整体False），pdf 仍随 docx 入库
        from cbeta_publish.books import xml2pdf_bridge as b
        win = self.win
        vdir = b.verify_coll_dir(win.config, "v")
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.pdf").write_bytes(b"PDF")
        (vdir / "T0001 大般若經.docx").write_bytes(b"DOCX")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "report.txt").write_text(
            "=== T01n0001.xml\n"
            "  [--]  pdf 已覆盖（已由 docx 校验）\n"
            "  [OK] (缺0/多0 ≤阈值10)\n  docx 【源】a\n  docx 【新】b\n"
            "  [FAIL] (缺3/多1 >阈值10)\n  epub 【源】c\n  epub 【新】d\n",
            encoding="utf-8")
        base = Path(win.config["xml_to_ebooks_dir"])
        res = self._do_import(win, ["T0001"], vdir, base)
        self.assertEqual((base / "pdf" / "T0001 大般若經.pdf").read_bytes(), b"PDF")
        self.assertEqual((base / "docx" / "T0001 大般若經.docx").read_bytes(), b"DOCX")
        self.assertEqual(len(res["ok"]), 1)
        self.assertIn("pdf", res["ok"][0])
        self.assertIn("docx", res["ok"][0])
        files = dict(res["ok_files"]["T0001"])
        self.assertTrue(Path(files["pdf"]).is_file())
        self.assertTrue(Path(files["docx"]).is_file())

    def test_import_no_baseline_undet_reason(self):
        # 无基线：[--] epub no baseline → 未判定并标注原因，不入库
        from cbeta_publish.books import xml2pdf_bridge as b
        win = self.win
        vdir = b.verify_coll_dir(win.config, "v")
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.epub").write_bytes(b"EPUB")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "report.txt").write_text(
            "=== T01n0001.xml\n  [--]  epub no baseline\n  [--]  docx no baseline\n",
            encoding="utf-8")
        base = Path(win.config["xml_to_ebooks_dir"])
        res = self._do_import(win, ["T0001"], vdir, base)
        self.assertEqual(res["ok"], [])
        self.assertEqual(res["undet"], ["T0001 未判定（epub无基线）"])
        self.assertFalse((base / "epub" / "T0001 大般若經.epub").exists())

    def test_import_summary_fail_label_with_numbers(self):
        # 新总结行：部分通过进 ok（"未入 epub 缺48/多97"）；全不过进 fail；
        # review 清单含报告路径与原因；通过项 move 保留带书名
        from cbeta_publish.books import xml2pdf_bridge as b
        win = self.win
        vdir = b.verify_coll_dir(win.config, "v")
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.docx").write_bytes(b"DOCX")
        (vdir / "T0001 大般若經.epub").write_bytes(b"EPUB")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        rp = vd / "report.txt"
        rp.write_text(
            "[T01n0001] 2 format: 1[docx=OK(0/0)], 2[epub=FAIL(48/97)]\n"
            "=== T01n0001.xml\n",
            encoding="utf-8")
        (vdir / "T0002 X.docx").write_bytes(b"D2")
        (vdir / "T0002 X.epub").write_bytes(b"E2")
        vd2 = vdir / "T0002 X（验证）"
        vd2.mkdir(parents=True, exist_ok=True)
        rp2 = vd2 / "report.txt"
        rp2.write_text(
            "[T02] 2 format: 1[docx=FAIL(1/2)], 2[epub=FAIL(48/97)]\n"
            "=== T02.xml\n",
            encoding="utf-8")
        base = Path(win.config["xml_to_ebooks_dir"])
        res = self._do_import(win, ["T0001", "T0002"], vdir, base)
        self.assertEqual((base / "docx" / "T0001 大般若經.docx").read_bytes(), b"DOCX")
        self.assertFalse((vdir / "T0001 大般若經.docx").exists())  # move 而非 copy
        self.assertFalse((base / "epub" / "T0001 大般若經.epub").exists())
        self.assertEqual(len(res["ok"]), 1)
        self.assertIn("epub 缺48/多97", res["ok"][0])
        self.assertEqual(res["fail"], ["T0002 校验未通过（epub 缺48/多97/docx 缺1/多2）"])
        by_work = {}
        for w, fmt, src, report, reason, mi, ex in res["review"]:
            by_work.setdefault(w, []).append((fmt, reason, mi, ex))
            self.assertTrue(Path(src).is_file())
        self.assertEqual(by_work["T0001"],
                         [("epub", "校验未通过（缺48/多97）", 48, 97)])
        self.assertEqual(by_work["T0002"],
                         [("epub", "校验未通过（缺48/多97）", 48, 97),
                          ("docx", "校验未通过（缺1/多2）", 1, 2)])
        self.assertEqual(res["review"][0][3], str(rp))

    def test_import_no_baseline_review_entry(self):
        # 未判定项同样进 review（无基线也可人工放行）
        from cbeta_publish.books import xml2pdf_bridge as b
        win = self.win
        vdir = b.verify_coll_dir(win.config, "v")
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.epub").write_bytes(b"EPUB")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "report.txt").write_text(
            "=== T01n0001.xml\n  [--]  epub no baseline\n", encoding="utf-8")
        base = Path(win.config["xml_to_ebooks_dir"])
        res = self._do_import(win, ["T0001"], vdir, base)
        self.assertEqual(len(res["review"]), 1)
        self.assertEqual(res["review"][0][:2], ("T0001", "epub"))
        self.assertEqual(res["review"][0][4], "无基线")

    def test_review_dialog_approves_checked(self):
        # 检验对话框：勾选→确定放行入库；取消→不动
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDialog, QListWidget
        win = self.win
        base = Path(win.config["xml_to_ebooks_dir"])
        base.mkdir(parents=True, exist_ok=True)
        src = base / "tmp_src.epub"
        src.write_bytes(b"EPUB")
        rp = base / "r.txt"
        rp.write_text("=== x\n  [--]  epub no baseline\n", encoding="utf-8")
        review = [("T0001", "epub", str(src), str(rp), "无基线", None, None)]
        real = QDialog.exec

        def fake_exec(self):
            for lw in self.findChildren(QListWidget):
                for i in range(lw.count()):
                    lw.item(i).setCheckState(Qt.Checked)
            return QDialog.Accepted

        QDialog.exec = fake_exec
        try:
            passed = win._review_failed_dialog(review, base)
        finally:
            QDialog.exec = real
        self.assertEqual(passed, [("T0001", "epub", str(base / "epub" / "tmp_src.epub"))])
        self.assertEqual((base / "epub" / "tmp_src.epub").read_bytes(), b"EPUB")
        self.assertFalse(src.exists())  # move 而非 copy

        QDialog.exec = lambda self: QDialog.Rejected
        try:
            self.assertEqual(win._review_failed_dialog(review, base), [])
        finally:
            QDialog.exec = real

    def test_review_dialog_deletes_unchecked_when_allowed(self):
        # allow_delete=True：未勾选的从校验目录删除；False：保留
        from PySide6.QtWidgets import QDialog
        win = self.win
        base = Path(win.config["xml_to_ebooks_dir"])
        base.mkdir(parents=True, exist_ok=True)
        for name in ("keep_src.epub", "drop_src.epub"):
            (base / name).write_bytes(b"EPUB")
        rp = base / "r.txt"
        rp.write_text("=== x\n  [--]  epub no baseline\n", encoding="utf-8")
        review = [("T1", "epub", str(base / "keep_src.epub"), str(rp), "无基线", None, None),
                  ("T2", "epub", str(base / "drop_src.epub"), str(rp), "无基线", None, None)]
        real = QDialog.exec

        def fake_exec(self):
            from PySide6.QtWidgets import QListWidget
            from PySide6.QtCore import Qt
            for lw in self.findChildren(QListWidget):
                lw.item(0).setCheckState(Qt.Checked)  # 只勾第一项
            return QDialog.Accepted

        QDialog.exec = fake_exec
        try:
            passed = win._review_failed_dialog(review, base, allow_delete=True)
        finally:
            QDialog.exec = real
        self.assertEqual(len(passed), 1)
        self.assertFalse((base / "drop_src.epub").exists())  # 未勾选已删除
        # 外部目录不删
        (base / "drop2.epub").write_bytes(b"EPUB")
        review2 = [("T3", "epub", str(base / "drop2.epub"), str(rp), "无基线", None, None)]

        def fake_exec_none(self):
            return QDialog.Accepted  # 全不勾

        QDialog.exec = fake_exec_none
        try:
            self.assertEqual(win._review_failed_dialog(review2, base, allow_delete=False), [])
        finally:
            QDialog.exec = real
        self.assertTrue((base / "drop2.epub").exists())

    def test_maybe_review_prompts_and_marks_manual(self):
        # 导入后询问：Yes→放行并标注人工；同 session 重跑不再问
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        base = Path(win.config["xml_to_ebooks_dir"])
        vdir = Path(win.config["verify_dir"])
        imp = {"ok": [], "fail": ["T0001 校验未通过（epub）"], "undet": [],
               "skip": [], "ok_files": {},
               "review": [("T0001", "epub", "S", "R", "校验未通过", None, None)]}
        boxes, restore = self._patch_common()
        real_dlg = win._review_failed_dialog
        win._wrap_box = lambda *a, **k: boxes.append(a) or QMessageBox.Yes
        win._review_failed_dialog = lambda review, b, allow_delete=False: [("T0001", "epub",
                                                        str(base / "epub" / "T0001.epub"))]
        try:
            win._maybe_review_failed(imp, vdir, base)
        finally:
            win._review_failed_dialog = real_dlg
            restore()
        self.assertTrue(boxes)  # 问过
        self.assertIn("T0001（epub）", imp["ok"])
        self.assertIn("T0001", imp.get("manual", set()))
        self.assertIn(("T0001", "epub"), win._manual_approved)
        self.assertIn("人工放行", win.detail.text())
        # 同 session 重跑：不再询问
        boxes2 = []
        win._wrap_box = lambda *a, **k: boxes2.append(a) or QMessageBox.Yes
        try:
            win._maybe_review_failed(imp, vdir, base)
        finally:
            restore()
        self.assertEqual(boxes2, [])

    def test_worker_summary_coverage_display(self):
        # 总结行驱动 worker 进度：docx过+pdf被覆盖+epub没过 → 部分通过（docx/pdf 过）
        from cbeta_publish.books.verify_worker import VerifyWorker
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b.verify_work

        def fake(work, fmts, out_dir, config, preset=None, stop=None):
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            rp = out / "r.txt"
            rp.write_text("[T1] 3 format: 1[docx=OK(0/0)], 2[pdf=1], "
                          "3[epub=FAIL(48/97)]\n", encoding="utf-8")
            return rp

        b.verify_work = fake
        msgs = []
        try:
            w = VerifyWorker(["T0001"], ["pdf", "docx", "epub"],
                             self.tmp / "o", self.win.config)
            w.progress.connect(lambda done, label, level: msgs.append(label))
            w.run()
        finally:
            b.verify_work = real
        self.assertTrue(any("部分通过" in m and "docx/pdf" in m and "epub" in m
                            for m in msgs), msgs)

    def test_worker_aggregates_same_work_variants(self):
        # 同一 work 的多个语义产物报告都要参加判定，不能只看最新一份。
        from cbeta_publish.books.verify_worker import VerifyWorker
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.tmp / "variant-aggr"
        first = out / "TX0011 上（验证）" / "report.txt"
        second = out / "TX0011 中下（验证）" / "report.txt"
        first.parent.mkdir(parents=True, exist_ok=True)
        second.parent.mkdir(parents=True, exist_ok=True)
        first.write_text("=== TX0011\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
        second.write_text("=== TX0011\n  [FAIL]  docx 缺3 多1\n", encoding="utf-8")
        real = b.verify_work
        b.verify_work = lambda *a, **k: first
        done = {}
        try:
            w = VerifyWorker(["TX0011"], ["docx"], out, self.win.config)
            w.finished_all.connect(
                lambda ok, tot, fl: done.update(ok=ok, tot=tot, fl=list(fl)))
            w.run()
        finally:
            b.verify_work = real
        self.assertEqual(done.get("ok"), 0)
        self.assertEqual(done.get("fl"), ["TX0011"])

    def test_show_results_links_imported_files(self):
        # 结果页：已入库条目每个格式文件可点开（file:// 链接到入库目标）
        win = self.win
        base = Path(win.config["xml_to_ebooks_dir"])
        imp = {"ok": ["T0001（docx/pdf）"], "fail": [], "undet": [], "skip": [],
               "ok_files": {"T0001": [("docx", str(base / "docx" / "T0001.docx")),
                                      ("pdf", str(base / "pdf" / "T0001.pdf"))]}}
        win._show_verify_results(imp, Path(win.config["verify_dir"]), base)
        txt = win.detail.text()
        self.assertIn("已入库 1 部", txt)
        self.assertIn("T0001.docx", txt)
        self.assertIn("T0001.pdf", txt)
        self.assertIn("href=", txt)

    def test_worker_base_exception_still_finishes(self):
        # verify_work 抛 SystemExit 等 BaseException 也必须发出 finished_all，
        # 否则主线程嵌套事件循环永不退出（界面挂死）
        from cbeta_publish.books.verify_worker import VerifyWorker
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b.verify_work

        def boom(*a, **k):
            raise SystemExit(2)

        b.verify_work = boom
        done = {}
        try:
            w = VerifyWorker(["T0001"], ["pdf"], self.tmp / "o", self.win.config)
            w.finished_all.connect(
                lambda ok, tot, fl: done.update(ok=ok, tot=tot, fl=list(fl)))
            w.run()
        finally:
            b.verify_work = real
        self.assertEqual(done.get("tot"), 1)
        self.assertEqual(done.get("fl"), ["T0001"])

    def test_send_clears_worker_ref(self):
        # 跑完不断开/不释放线程对象会导致野指针：_verify_worker 必须复位
        win = self.win
        boxes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        try:
            win._send_coll_to_verify(regen_all=True)
        finally:
            restore_v()
            restore()
        self.assertIsNone(win._verify_worker)

    def test_edit_preset_follows_current_preset(self):
        # 「调整…」面板内预设下拉默认选中 Publish 当前预设（而非 run.json 槽）
        import sys as _sys
        _cfg0 = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
        _real_x2p = ((_cfg0.get("xml2pdf") or {}).get("path") or "").strip()
        if _real_x2p and _real_x2p not in _sys.path:
            _sys.path.insert(0, _real_x2p)
        import pycbeta.gui.panel as _panel
        from PySide6.QtWidgets import QComboBox
        from cbeta_publish.books import xml2pdf_bridge as _b
        win = self.win
        # 在夹具的假预设目录里造一个预设并选中（Publish 当前预设）
        _pd = Path(win.config["xml2pdf"]["path"]) / "presets"
        _pd.mkdir(parents=True, exist_ok=True)
        (_pd / "跟随测.json").write_text('{"output": {}}', encoding="utf-8")
        _old_data = win.cb_preset.currentData()
        _old_preset = (win.config.get("xml2pdf") or {}).get("preset", "")
        win._refresh_preset_combo()
        _idx = win.cb_preset.findData("跟随测")
        self.assertGreaterEqual(_idx, 0)
        win.cb_preset.setCurrentIndex(_idx)
        _ensure_app().processEvents()
        self.assertEqual(win.config["xml2pdf"]["preset"], "跟随测")

        class _FakePanel:
            def __init__(self, w):
                self.cfg_preset_box = QComboBox()
                self.cfg_preset_box.addItem("（出厂默认）", "")
                _cn = w.cb_preset.currentData() or ""
                if _cn:
                    _cp = _b.resolve_preset(w.config, _cn)
                    if _cp is not None:
                        self.cfg_preset_box.addItem(_cn, str(_cp))
                self.updated = False

            def get_options(self):
                class _O:
                    formats = []
                return _O()

            def set_options(self, o):
                pass

            def _update_preset_buttons(self):
                self.updated = True

            def _refresh_theme_box(self, keep_value=None):
                self.theme_refreshed = True

            def _update_theme_button(self):
                self.theme_button_updated = True

        class _FakeDlg:
            last = None

            def __init__(self, base, parent=None):
                _FakeDlg.last = self
                self.panel = _FakePanel(parent)

            def exec(self):
                from PySide6.QtWidgets import QDialog
                return QDialog.Rejected  # 取消：只验证下拉选中，不改配置

            def get_preset(self, base=None):
                return None

        real = _panel.XmlOptionsDialog
        _panel.XmlOptionsDialog = _FakeDlg
        try:
            win._edit_preset()
        finally:
            _panel.XmlOptionsDialog = real
            # 恢复共享夹具的预设选择
            _ri = win.cb_preset.findData(_old_data)
            win.cb_preset.setCurrentIndex(_ri if _ri >= 0 else 0)
            win.config["xml2pdf"]["preset"] = _old_preset
        box = _FakeDlg.last.panel.cfg_preset_box
        self.assertEqual(box.currentText(), "跟随测")
        self.assertTrue(_FakeDlg.last.panel.updated)
        # 主题下拉须随预设选中重刷（否则停留在 run.json 槽的样式）
        self.assertTrue(getattr(_FakeDlg.last.panel, "theme_refreshed", False))
        self.assertTrue(getattr(_FakeDlg.last.panel, "theme_button_updated",
                                False))

    def test_open_window_aligns_preset_workroot(self):
        # 预设 source.cbeta_ebook 与 publish 工作根不一致 → 询问；Yes 则覆盖对齐
        import subprocess
        from PySide6.QtWidgets import QMessageBox
        from cbeta_publish.books import xml2pdf_bridge as _b
        win = self.win
        pd = Path(win.config["xml2pdf"]["path"]) / "presets"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "对齐测.json").write_text(
            json.dumps({"source": {"cbeta_ebook": "E:/old/root"}}), encoding="utf-8")
        _old_data = win.cb_preset.currentData()
        _old_preset = (win.config.get("xml2pdf") or {}).get("preset", "")
        win._refresh_preset_combo()
        _idx = win.cb_preset.findData("对齐测")
        self.assertGreaterEqual(_idx, 0)
        win.cb_preset.setCurrentIndex(_idx)
        _ensure_app().processEvents()
        real_popen = subprocess.Popen
        subprocess.Popen = lambda argv, **k: None
        real_q = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        try:
            win._open_xml2pdf_window()
        finally:
            subprocess.Popen = real_popen
            QMessageBox.question = real_q
            _ri = win.cb_preset.findData(_old_data)
            win.cb_preset.setCurrentIndex(_ri if _ri >= 0 else 0)
            win.config["xml2pdf"]["preset"] = _old_preset
        d = json.loads((pd / "对齐测.json").read_text(encoding="utf-8"))
        self.assertEqual(Path(d["source"]["cbeta_ebook"]).resolve(),
                         _b.xml_work_dir(win.config).resolve())

    def test_open_window_aligns_preset_verify_root(self):
        # 预设 source.verify_root 非空 → 询问；Yes 则清空（本次已用 --verify-root 钉死）
        import subprocess
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        pd = Path(win.config["xml2pdf"]["path"]) / "presets"
        pd.mkdir(parents=True, exist_ok=True)
        (pd / "校根测.json").write_text(
            json.dumps({"source": {"verify_root": "E:/other/验证"}}),
            encoding="utf-8")
        _old_data = win.cb_preset.currentData()
        _old_preset = (win.config.get("xml2pdf") or {}).get("preset", "")
        win._refresh_preset_combo()
        _idx = win.cb_preset.findData("校根测")
        self.assertGreaterEqual(_idx, 0)
        win.cb_preset.setCurrentIndex(_idx)
        _ensure_app().processEvents()
        real_popen = subprocess.Popen
        subprocess.Popen = lambda argv, **k: None
        real_q = QMessageBox.question
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        try:
            win._open_xml2pdf_window()
        finally:
            subprocess.Popen = real_popen
            QMessageBox.question = real_q
            _ri = win.cb_preset.findData(_old_data)
            win.cb_preset.setCurrentIndex(_ri if _ri >= 0 else 0)
            win.config["xml2pdf"]["preset"] = _old_preset
        d = json.loads((pd / "校根测.json").read_text(encoding="utf-8"))
        self.assertEqual(d.get("source", {}).get("verify_root", ""), "")

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
        from PySide6.QtWidgets import QFileDialog
        from cbeta_publish.books import xml2pdf_bridge as b
        vdir = self._mk_verify_tree()
        real_dir = QFileDialog.getExistingDirectory
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(vdir))
        boxes, restore = self._patch_common()
        try:
            self.win._import_verified()
        finally:
            QFileDialog.getExistingDirectory = real_dir
            restore()
        base = Path(self.win.config["xml_to_ebooks_dir"])
        self.assertEqual((base / "pdf" / "T0001 大般若經.pdf").read_bytes(), b"PDF")    # 通过 move 入库（L2 带书名）
        self.assertEqual((base / "docx" / "T0001 大般若經.docx").read_bytes(), b"DOCX")  # 多格式都入
        self.assertFalse((base / "epub" / "T0002 X.epub").exists())               # 未通过不入库
        self.assertTrue(any("入库 1 部" in x for f in self._finishes for x in f),
                        self._finishes)

    def test_import_partial_formats(self):
        # docx 通过、epub 未通过 → 只入 docx，epub 不入；不计失败
        from cbeta_publish.books import xml2pdf_bridge as b
        win = self.win
        vdir = b.verify_coll_dir(win.config, "v")
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.docx").write_bytes(b"DOCX")
        (vdir / "T0001 大般若經.epub").write_bytes(b"EPUB")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "report.txt").write_text(
            "=== T0001\n"
            "  [OK] (缺0/多0 ≤阈值10)\n  docx 【源】a\n  docx 【新】b\n"
            "  [FAIL] (缺3/多1 >阈值10)\n  epub 【源】c\n  epub 【新】d\n",
            encoding="utf-8")
        base = Path(win.config["xml_to_ebooks_dir"])
        res = self._do_import(win, ["T0001"], vdir, base)
        self.assertEqual((base / "docx" / "T0001 大般若經.docx").read_bytes(), b"DOCX")
        self.assertFalse((base / "epub" / "T0001 大般若經.epub").exists())
        self.assertEqual(len(res["ok"]), 1)
        self.assertEqual(res["fail"], [])
        self.assertIn("未入 epub", res["ok"][0])

    def test_import_json_scope_and_fail_label(self):
        # report.json：docx 过、epub 未过（差异含正文）→ 只入 docx；"未入"带范围
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        vdir = self.tmp / "vjson"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.docx").write_bytes(b"DOCX")
        (vdir / "T0001 大般若經.epub").write_bytes(b"EPUB")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "report.txt").write_text("=== T0001\n", encoding="utf-8")
        (vd / "report.json").write_text(json.dumps({
            "schema": 1,
            "fmts": {"docx": {"verdict": "pass", "missing": 0, "extra": 0},
                     "epub": {"verdict": "fail", "missing": 48, "extra": 97,
                              "diff_scope": "body"}}}, ensure_ascii=False),
            encoding="utf-8")
        base = self.tmp / "jlib"
        res = win._do_import_verified(["T0001"], vdir, base)
        self.assertEqual((base / "docx" / "T0001 大般若經.docx").read_bytes(),
                         b"DOCX")
        self.assertFalse((base / "epub" / "T0001 大般若經.epub").exists())
        self.assertEqual(res["fail"], [])
        self.assertTrue(any("未入 epub" in x for x in res["ok"]))
        self.assertTrue(any("含正文差异" in x for x in res["ok"]), res["ok"])

    def test_import_json_format_filter_skips_stray(self):
        # json 声明格式集只含 docx → 顶层残留 odt 不被捡入、也不误报缺产物
        win = self.win
        vdir = self.tmp / "vjson2"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "T0001 大般若經.docx").write_bytes(b"DOCX")
        (vdir / "T0001 大般若經.odt").write_bytes(b"ODT")
        vd = vdir / "T0001 大般若經（验证）"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "report.txt").write_text("=== T0001\n", encoding="utf-8")
        (vd / "report.json").write_text(json.dumps({
            "schema": 1,
            "fmts": {"docx": {"verdict": "pass"}}}, ensure_ascii=False),
            encoding="utf-8")
        base = self.tmp / "jlib2"
        res = win._do_import_verified(["T0001"], vdir, base)
        self.assertEqual((base / "docx" / "T0001 大般若經.docx").read_bytes(),
                         b"DOCX")
        self.assertFalse((base / "odt").exists())
        self.assertEqual(res["fail"], [])
        self.assertEqual(res["undet"], [])

    def test_worker_scope_in_progress_label(self):
        # report.json diff_scope=body → worker 进度行带「含正文差异」
        from cbeta_publish.books.verify_worker import VerifyWorker
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b.verify_work

        def fake(work, fmts, out_dir, config, preset=None, stop=None):
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            vd = out / f"{work} 大般若經（验证）"
            vd.mkdir(parents=True, exist_ok=True)
            rp = vd / "report.txt"
            rp.write_text("[T0001] 2 format: 1[docx=OK(0/0)], 2[epub=FAIL(48/97)]\n",
                          encoding="utf-8")
            (vd / "report.json").write_text(json.dumps({
                "schema": 1,
                "fmts": {"docx": {"verdict": "pass"},
                         "epub": {"verdict": "fail", "missing": 48,
                                  "extra": 97, "diff_scope": "body"}}},
                ensure_ascii=False), encoding="utf-8")
            return rp

        b.verify_work = fake
        msgs = []
        try:
            w = VerifyWorker(["T0001"], ["docx", "epub"],
                             self.tmp / "wscope", self.win.config)
            w.progress.connect(lambda done, label, level: msgs.append(label))
            w.run()
        finally:
            b.verify_work = real
        self.assertTrue(any("含正文差异" in m for m in msgs), msgs)

    def test_import_same_work_variants(self):
        # 同一 work 的多个语义产物各按自己的报告入库，不互相覆盖/误套。
        win = self.win
        vdir = self.tmp / "txv"
        vdir.mkdir(parents=True, exist_ok=True)
        names = ("TX0011 宗依論（上）.docx", "TX0011 宗依論（中、下）.docx")
        for name in names:
            (vdir / name).write_bytes(b"DOCX")
            report_dir = vdir / f"{name[:-len('.docx')]}（验证）"
            report_dir.mkdir(parents=True, exist_ok=True)
            (report_dir / "report.txt").write_text(
                "=== TX0011\n  [OK]  docx 缺0 多0\n", encoding="utf-8")
        base = self.tmp / "txlib"
        res = self._do_import(win, ["TX0011"], vdir, base)
        self.assertEqual(
            [(p.name, p.read_bytes()) for p in
             sorted((base / "docx").iterdir(), key=lambda p: p.name)],
            [(names[0], b"DOCX"), (names[1], b"DOCX")])
        self.assertEqual(len(res["ok"]), 2)
        self.assertEqual(res["fail"], [])
        self.assertEqual(res["undet"], [])
        self.assertEqual(len(res["ok_files"]["TX0011"]), 2)

    def _do_import(self, win, works, vdir, base):
        return win._do_import_verified(works, vdir, base)

    def test_show_verify_results_in_book_info_tab(self):
        # 逐本/逐格式结果（含部分通过）显示在「书籍信息」页签，含可点目录
        win = self.win
        imp = {"ok": ["T0001（docx）；未入 epub"],
               "fail": ["T0002 校验未通过（epub）"], "undet": [], "skip": []}
        win.tab_bottom.setCurrentIndex(1)
        win._show_verify_results(imp, Path(win.config["verify_dir"]),
                                 Path(win.config["xml_to_ebooks_dir"]))
        txt = win.detail.text()
        self.assertIn("未入 epub", txt)
        self.assertIn("验证输出目录", txt)
        self.assertIn("未入库", txt)
        self.assertIn("href=", txt)
        self.assertEqual(win.tab_bottom.currentIndex(), 0)

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
            self.assertEqual((base / "pdf" / "T0001 大般若經.pdf").read_bytes(), b"PDF")
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
        for key in ("（验证）", "[FAIL]", "{fmt}/{id 书名}", "手动选目录",
                    "转换后校验", "顶层"):
            self.assertIn(key, txt)

    def test_menu_has_rules_action(self):
        menus = [a for a in self.win.menuBar().actions()
                 if a.text().replace("&", "") == "制作书籍"]
        self.assertEqual(len(menus), 1)
        acts = [a.text() for a in menus[0].menu().actions()]
        self.assertIn("运行 xml2pdf 制作书籍…", acts)
        self.assertIn("导入说明…", acts)


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
