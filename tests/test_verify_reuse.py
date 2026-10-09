# -*- coding: utf-8 -*-
"""校验复用：通过记录库 + 指纹新鲜度跳过 + 开关 + 缓存页。"""
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


class VerifyCacheTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.db = self.dir / "records.json"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_roundtrip_and_freshness(self):
        from cbeta_publish.books import verify_cache as vc
        self.assertFalse(vc.is_fresh(self.db, "T0001", "pdf", "fp1"))
        self.assertTrue(vc.record_pass(self.db, "T0001", "pdf", "fp1"))
        self.assertTrue(vc.is_fresh(self.db, "T0001", "pdf", "fp1"))
        self.assertFalse(vc.is_fresh(self.db, "T0001", "pdf", "fp2"))  # 指纹变了
        self.assertFalse(vc.is_fresh(self.db, "T0001", "pdf", ""))      # 空指纹
        self.assertFalse(vc.is_fresh(self.db, "T0001", "epub", "fp1"))  # 格式隔离
        st = vc.stats(self.db)
        self.assertEqual((st["works"], st["entries"]), (1, 1))

    def test_drop_and_clear(self):
        from cbeta_publish.books import verify_cache as vc
        vc.record_pass(self.db, "T0001", "pdf", "a")
        vc.record_pass(self.db, "T0001", "docx", "b")
        vc.record_pass(self.db, "T0002", "pdf", "c")
        self.assertTrue(vc.drop(self.db, "T0001", "pdf"))
        self.assertFalse(vc.is_fresh(self.db, "T0001", "pdf", "a"))
        self.assertTrue(vc.is_fresh(self.db, "T0001", "docx", "b"))
        self.assertTrue(vc.drop(self.db, "T0002"))   # 整部删
        self.assertEqual(vc.stats(self.db)["entries"], 1)
        self.assertTrue(vc.clear(self.db))
        self.assertEqual(vc.stats(self.db), {"works": 0, "entries": 0})

    def test_corrupt_file_reads_empty(self):
        from cbeta_publish.books import verify_cache as vc
        self.db.write_text("{not json", encoding="utf-8")
        self.assertEqual(vc.stats(self.db), {"works": 0, "entries": 0})
        self.assertIsNone(vc.get(self.db, "T0001", "pdf"))
        # 损坏后仍可覆盖写回
        self.assertTrue(vc.record_pass(self.db, "T0001", "pdf", "fp"))
        self.assertTrue(vc.is_fresh(self.db, "T0001", "pdf", "fp"))

    def test_empty_fingerprint_rejected(self):
        from cbeta_publish.books import verify_cache as vc
        self.assertFalse(vc.record_pass(self.db, "T0001", "pdf", ""))
        self.assertFalse(self.db.exists())

    def test_input_sets_model(self):
        # schema v2：同 (work,fmt) 多输入集并存；新鲜要求 inputs 有序相等＋指纹一致
        from cbeta_publish.books import verify_cache as vc
        self.assertTrue(vc.record_pass(self.db, "TX0011", "docx", "fp-a",
                                       {"inputs": ["A.xml", "B.xml"],
                                        "accept": "strict"}))
        self.assertTrue(vc.is_fresh(self.db, "TX0011", "docx", "fp-a",
                                    ["A.xml", "B.xml"]))
        self.assertFalse(vc.is_fresh(self.db, "TX0011", "docx", "fp-a",
                                     ["B.xml", "A.xml"]))   # 顺序不同
        self.assertFalse(vc.is_fresh(self.db, "TX0011", "docx", "fp-a",
                                     ["A.xml"]))            # 集合不同
        self.assertFalse(vc.is_fresh(self.db, "TX0011", "docx", "fp-b",
                                     ["A.xml", "B.xml"]))   # 指纹不同
        # 同 inputs 覆盖，不同 inputs 追加
        self.assertTrue(vc.record_pass(self.db, "TX0011", "docx", "fp-a2",
                                       {"inputs": ["A.xml", "B.xml"],
                                        "accept": "notes_only"}))
        self.assertTrue(vc.is_fresh(self.db, "TX0011", "docx", "fp-a2",
                                    ["A.xml", "B.xml"]))
        self.assertTrue(vc.record_pass(self.db, "TX0011", "docx", "fp-c",
                                       {"inputs": ["A.xml"]}))
        self.assertTrue(vc.is_fresh(self.db, "TX0011", "docx", "fp-c", ["A.xml"]))
        self.assertTrue(vc.is_fresh(self.db, "TX0011", "docx", "fp-a2",
                                    ["A.xml", "B.xml"]))
        e = vc.get(self.db, "TX0011", "docx")
        self.assertEqual(len(e["sets"]), 2)
        self.assertEqual(vc.stats(self.db)["entries"], 1)

    def test_records_path_default(self):
        from cbeta_publish.books import verify_cache as vc
        p = vc.records_path({})
        self.assertEqual(p.name, "verify_records.json")

    def test_juan_isolation(self):
        # 同 (work,fmt) 整本与子集、不同子集互不命中；集身份=(inputs,juan)
        from cbeta_publish.books import verify_cache as vc
        vc.record_pass(self.db, "T0349", "pdf", "fpw", {"inputs": ["S.xml"]})
        self.assertTrue(vc.is_fresh(self.db, "T0349", "pdf", "fpw", ["S.xml"]))
        self.assertFalse(vc.is_fresh(self.db, "T0349", "pdf", "fpw", ["S.xml"],
                                     juan="2-3"))
        vc.record_pass(self.db, "T0349", "pdf", "fps",
                       {"inputs": ["S.xml"], "juan": "2-3"})
        self.assertTrue(vc.is_fresh(self.db, "T0349", "pdf", "fps", ["S.xml"],
                                    juan="2-3"))
        self.assertFalse(vc.is_fresh(self.db, "T0349", "pdf", "fps", ["S.xml"],
                                     juan="5"))
        self.assertTrue(vc.is_fresh(self.db, "T0349", "pdf", "fpw", ["S.xml"]))
        e = vc.get(self.db, "T0349", "pdf")
        self.assertEqual(len(e["sets"]), 2)   # 同 inputs 不同 juan → 两集


class FingerprintProbeTest(unittest.TestCase):
    def _real_cfg(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        root = b.PROJECT_ROOT.parent / "xml2pdf"
        if not (root / "pycbeta" / "verify.py").is_file():
            self.skipTest("no real xml2pdf sibling repo")
        return {"xml2pdf": {"path": str(root)}}

    def test_unavailable_upstream_gives_none(self):
        # 上游不可导入 → 探测 False、指纹 None（安全降级为重验）
        import sys
        import cbeta_publish.books.xml2pdf_bridge as b
        saved = {k: sys.modules.pop(k) for k in
                 [k for k in sys.modules if k == "pycbeta" or k.startswith("pycbeta.")]}
        sys.modules["pycbeta"] = None   # 阻断 `from pycbeta import verify`
        try:
            cfg = {"xml2pdf": {"path": "Z:/no/such/dir"}}
            self.assertFalse(b.verify_fingerprint_available(cfg))
            self.assertIsNone(b.verify_fingerprint("T0001", "pdf", cfg))
        finally:
            sys.modules.pop("pycbeta", None)
            sys.modules.update(saved)

    def test_real_upstream_probe(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        cfg = self._real_cfg()
        self.assertTrue(b.verify_fingerprint_available(cfg))
        # 无 XML 可定位 → None，且无副作用（不下载不写盘）
        tmp = Path(tempfile.mkdtemp())
        try:
            cfg["xml2pdf"] = dict(cfg["xml2pdf"], cbeta_ebook=str(tmp))
            self.assertIsNone(b.verify_fingerprint("T0001", "pdf", cfg))
            self.assertEqual(list(tmp.iterdir()), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_juan_label_and_segments(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        cfg = self._real_cfg()
        self.assertEqual(b.juan_label(cfg, "2-3"), "2-3")
        self.assertEqual(b.juan_label(cfg, "34-36,40"), "34-36、40")
        self.assertEqual(b.juan_label(cfg, "34-36、40"), "34-36、40")
        self.assertEqual(b.juan_segments(cfg, "34-36,40"), [(34, 36), (40, 40)])
        self.assertIsNone(b.juan_segments(cfg, ""))


class VerifyReuseFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        win = cls.win
        win.config["verify_dir"] = str(cls.tmp / "vf")
        win.config["xml_to_ebooks_dir"] = str(cls.tmp / "xb")
        (cls.tmp / "x2p").mkdir()
        win.config["xml2pdf"]["path"] = str(cls.tmp / "x2p")
        win.config["xml2pdf"]["preset"] = ""
        (cls.tmp / "xe-empty").mkdir()
        win.config["xml2pdf"]["cbeta_ebook"] = str(cls.tmp / "xe-empty")
        col = Path(win.config["collections_dir"]) / "custom" / "复用测.json"
        col.write_text(json.dumps({"id": "r", "name": "复用测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001", "T0002"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("复用测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        shutil.rmtree(b.verify_coll_dir(self.win.config, "r"), ignore_errors=True)
        shutil.rmtree(Path(self.win.config["xml_to_ebooks_dir"]), ignore_errors=True)
        self.win.chk_pdf.setChecked(True)
        self.win.chk_epub.setChecked(False)
        self.win.chk_docx.setChecked(False)
        self._saved_fp = b.verify_fingerprint
        self._saved_avail = b.verify_fingerprint_available

    def tearDown(self):
        from cbeta_publish.books import xml2pdf_bridge as b
        b.verify_fingerprint = self._saved_fp
        b.verify_fingerprint_available = self._saved_avail

    def _patch_common(self):
        win = self.win
        real_box, real_prog = win._wrap_box, win._make_progress
        boxes, finishes = [], []
        win._wrap_box = lambda *a, **k: boxes.append(a) or None
        win._make_progress = lambda t, n: (
            None, (lambda *a, **k: True),
            {"finish": lambda lines=None, *a, **k: finishes.append(lines)})
        return boxes, finishes, lambda: (
            setattr(win, "_wrap_box", real_box),
            setattr(win, "_make_progress", real_prog))

    def _patch_verify(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b.verify_work
        calls = []

        def fake(work, fmts, out_dir, config, preset=None, stop=None, juan=None):
            calls.append(work)
            out = Path(out_dir)
            out.mkdir(parents=True, exist_ok=True)
            (out / f"{work} 大般若經.pdf").write_bytes(b"PDF")
            vd = out / f"{work} 大般若經（验证）"
            vd.mkdir(parents=True, exist_ok=True)
            (vd / "report.txt").write_text(
                "=== T0001\n  [OK]  pdf 缺0 多0\n", encoding="utf-8")
            return vd / "report.txt"
        b.verify_work = fake
        return calls, lambda: setattr(b, "verify_work", real)

    def _records_path(self):
        from cbeta_publish.books import verify_cache as vc
        return vc.records_path(self.win.config)

    def _stub_fingerprint(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        b.verify_fingerprint_available = lambda config: True
        b.verify_fingerprint = lambda w, f, config, preset=None, xml_files=None, juan=None: f"fp-{w}-{f}"

    def test_all_fresh_skips_everything(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        from cbeta_publish.books import verify_cache as vc
        win = self.win
        self._stub_fingerprint()
        base = Path(win.config["xml_to_ebooks_dir"])
        (base / "pdf").mkdir(parents=True)
        for w in ("T0001", "T0002"):
            (base / "pdf" / f"{w}.pdf").write_bytes(b"x")
            vc.record_pass(self._records_path(), w, "pdf", f"fp-{w}-pdf")
        boxes, finishes, restore = self._patch_common()
        try:
            win._send_coll_to_verify()
        finally:
            restore()
        self.assertIn("无需重验", win.detail.text())
        self.assertIsNone(win._verify_worker)

    def test_stale_only_verifies_stale(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        from cbeta_publish.books import verify_cache as vc
        win = self.win
        self._stub_fingerprint()
        base = Path(win.config["xml_to_ebooks_dir"])
        (base / "pdf").mkdir(parents=True)
        for w in ("T0001", "T0002"):
            (base / "pdf" / f"{w}.pdf").write_bytes(b"x")
        # T0001 记录过期（指纹对不上），T0002 新鲜
        vc.record_pass(self._records_path(), "T0001", "pdf", "fp-OLD")
        vc.record_pass(self._records_path(), "T0002", "pdf", "fp-T0002-pdf")
        boxes, finishes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        try:
            win._send_coll_to_verify()
        finally:
            restore_v()
            restore()
        self.assertEqual(calls, ["T0001"])   # 只验过期那部
        flat = [str(x) for f in finishes for x in (f or [])]
        self.assertTrue(any("跳过已通过 1 部" in x for x in flat), flat)
        # 通过后记录被刷新为新指纹
        self.assertTrue(vc.is_fresh(self._records_path(), "T0001", "pdf",
                                    "fp-T0001-pdf"))

    def test_upstream_import_skips_verify(self):
        # 上游报告目录有匹配 pass 报告 → 记库并跳过，不调 verify_work
        import cbeta_publish.books.xml2pdf_bridge as b
        from cbeta_publish.books import verify_cache as vc
        win = self.win
        self._stub_fingerprint()
        vc.drop(self._records_path(), "T0001")
        vc.drop(self._records_path(), "T0002")
        _old_ebook = win.config["xml2pdf"].get("cbeta_ebook")
        _old_rdir = win.config["xml2pdf"].get("verify_reports_dir")
        xe = self.tmp / "xe"
        (xe / "T0001 X").mkdir(parents=True)
        (xe / "T0001 X" / "S.xml").write_text("<x/>", encoding="utf-8")
        win.config["xml2pdf"]["cbeta_ebook"] = str(xe)
        upv = self.tmp / "upv"
        vd = upv / "T0001 X（验证）"
        vd.mkdir(parents=True)
        (vd / "report.json").write_text(json.dumps({
            "schema": 1,
            "work": "T0001",
            "fmts": {"pdf": {"verdict": "pass",
                             "fingerprint": "fp-T0001-pdf",
                             "formal_outputs": ["a.pdf"]}},
            "inputs": {"xml_files": [{"name": "S.xml"}]}}), encoding="utf-8")
        (vd / "report.txt").write_text("=== T0001\n  [OK]  pdf 缺0 多0\n",
                                       encoding="utf-8")
        win.config["xml2pdf"]["verify_reports_dir"] = str(upv)
        base = Path(win.config["xml_to_ebooks_dir"])
        (base / "pdf").mkdir(parents=True)
        (base / "pdf" / "T0001.pdf").write_bytes(b"x")
        (base / "pdf" / "T0002.pdf").write_bytes(b"x")
        real_find = b.find_upstream_reports
        b.find_upstream_reports = lambda config, rdir: [
            {"id": "T0001", "title": "T0001 X", "dir": str(vd),
             "report_json": str(vd / "report.json"),
             "report_txt": str(vd / "report.txt")}]
        boxes, finishes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        try:
            win._send_coll_to_verify()
        finally:
            restore_v()
            restore()
            b.find_upstream_reports = real_find
            if _old_ebook is None:
                win.config["xml2pdf"].pop("cbeta_ebook", None)
            else:
                win.config["xml2pdf"]["cbeta_ebook"] = _old_ebook
            if _old_rdir is None:
                win.config["xml2pdf"].pop("verify_reports_dir", None)
            else:
                win.config["xml2pdf"]["verify_reports_dir"] = _old_rdir
        self.assertEqual(calls, ["T0002"])   # T0001 由上游导入跳过
        flat = [str(x) for f in finishes for x in (f or [])]
        self.assertTrue(any("上游导入 1 条" in x for x in flat), flat)
        e = vc.get(self._records_path(), "T0001", "pdf")
        self.assertEqual(e["accept"], "strict")
        self.assertEqual(e["sets"][0]["inputs"], ["S.xml"])
        self.assertEqual(e["sets"][0]["fingerprint"], "fp-T0001-pdf")

    def test_subset_not_reused_from_whole_record(self):
        # 卷条目（work:卷）不被整本记录复用：label 不等 → 重验
        import cbeta_publish.books.xml2pdf_bridge as b
        from cbeta_publish.books import verify_cache as vc
        win = self.win
        self._stub_fingerprint()
        d = win._coll_dict(win.coll_combo.currentData())
        _old = list(d.get("work_ids") or [])
        d["work_ids"] = ["T0001:2-3", "T0002"]
        base = Path(win.config["xml_to_ebooks_dir"])
        (base / "pdf").mkdir(parents=True, exist_ok=True)
        for w in ("T0001", "T0002"):
            (base / "pdf" / f"{w}.pdf").write_bytes(b"x")
        vc.record_pass(self._records_path(), "T0001", "pdf", "fp-T0001-pdf")
        vc.record_pass(self._records_path(), "T0002", "pdf", "fp-T0002-pdf")
        boxes, finishes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        try:
            win._send_coll_to_verify()
        finally:
            restore_v()
            restore()
            d["work_ids"] = _old
        self.assertEqual(calls, ["T0001"])   # 子集不复用整本记录

    def test_toggle_off_verifies_all(self):
        # 开关关闭：回退旧行为（重制即全部重验），即使记录新鲜
        import cbeta_publish.books.xml2pdf_bridge as b
        from cbeta_publish.books import verify_cache as vc
        win = self.win
        self._stub_fingerprint()
        base = Path(win.config["xml_to_ebooks_dir"])
        (base / "pdf").mkdir(parents=True)
        for w in ("T0001", "T0002"):
            (base / "pdf" / f"{w}.pdf").write_bytes(b"x")
            vc.record_pass(self._records_path(), w, "pdf", f"fp-{w}-pdf")
        win.config.setdefault("xml2pdf", {})["verify_reuse"] = False
        boxes, finishes, restore = self._patch_common()
        calls, restore_v = self._patch_verify()
        try:
            win._send_coll_to_verify(regen_all=True)
        finally:
            restore_v()
            restore()
            win.config["xml2pdf"]["verify_reuse"] = True
        self.assertEqual(sorted(calls), ["T0001", "T0002"])


class VerifyReuseSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def _dlg(self):
        from cbeta_publish.gui.settings_dialog import SettingsDialog, DEFAULT_CONFIG
        import copy
        return SettingsDialog(copy.deepcopy(DEFAULT_CONFIG), None)

    def test_reuse_default_on_and_roundtrip(self):
        dlg = self._dlg()
        try:
            self.assertTrue(dlg.chk_verify_reuse.isChecked())
            dlg.chk_verify_reuse.setChecked(False)
            self.assertFalse(dlg._collect()["xml2pdf"]["verify_reuse"])
            dlg.chk_verify_reuse.setChecked(True)
            self.assertTrue(dlg._collect()["xml2pdf"]["verify_reuse"])
        finally:
            dlg.close()

    def test_cache_records_row(self):
        import cbeta_publish.books.verify_cache as vc
        tmp = Path(tempfile.mkdtemp())
        try:
            real = vc.records_path
            vc.records_path = lambda cfg=None: tmp / "records.json"
            try:
                dlg = self._dlg()
                try:
                    vc.record_pass(tmp / "records.json", "T1", "pdf", "fp")
                    dlg._refresh_cache_stats()
                    self.assertIn("1 条", dlg._verify_records_lbl.text())
                finally:
                    dlg.close()
            finally:
                vc.records_path = real
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
