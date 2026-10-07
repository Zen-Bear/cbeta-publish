# -*- coding: utf-8 -*-
"""S7：批量更新素材 `_run_batch_update`（状态/报告/隔离/不自制合并）。"""
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


def _write_coll(dirp, name, works):
    p = dirp / f"{name}.json"
    p.write_text(json.dumps({"id": name, "name": name, "category": "custom",
                             "tags": [], "work_ids": works},
                            ensure_ascii=False), encoding="utf-8")
    return p


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    cdir = tmp / "collections" / "custom"
    cdir.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    _write_coll(cdir, "甲", ["T0001", "T0002"])
    _write_coll(cdir, "乙", ["T0003"])
    _write_coll(cdir, "空", [])
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["output_dir"] = str(tmp / "out")
    cfg["update_interval"] = "manual"
    cfg["xml2pdf"]["cbeta_ebook"] = str(tmp / "xml")
    cfg["official_library"] = {"root": ""}
    cfg["cbeta_ebooks_dir"] = str(tmp / "eb")
    cfg["_config_path"] = str(tmp / "app.json")
    cfg["default_formats"] = {"merge": ["pdf", "epub"],
                              "official": ["pdf", "epub"], "xml": ["pdf", "docx"]}
    win = MainWindow(cfg)
    win._load_collections()
    return win, tmp


class BatchUpdateTest(unittest.TestCase):
    def setUp(self):
        self.win, self.tmp = _make_window()
        self.win.chk_pdf.setChecked(True)
        self.win.chk_epub.setChecked(True)
        self.win.chk_docx.setChecked(False)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _selected(self):
        return [(p, d) for p, d in self.win._collections
                if (d.get("work_ids") or [])]

    def test_official_status_and_report(self):
        self.win.config["default_source"] = "official"
        self.win._prepare_official = lambda works, fmts, dest, policy="stale": (
            {}, ["T0001.pdf"])
        self.win._run_batch_update(self._selected(), "stale", "missing", True)
        rep = Path(self.win.config["output_dir"]) / "批量更新报告.txt"
        self.assertTrue(rep.is_file())
        text = rep.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("partial", text)
        self.assertIn("T0001.pdf", text)

    def test_xml_uses_ensure_and_no_merge(self):
        self.win.config["default_source"] = "xml"
        calls = []
        self.win._ensure_xml_batch = lambda works, fmts, title="", regen_all=False: (
            calls.append((list(works), list(fmts), regen_all)) or ({}, ["T0003.pdf"], False))
        self.win._run_batch_update(self._selected(), "stale", "all", False)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][2])   # regen_all True
        # 不合并：output_dir 下无合并产物
        out = Path(self.win.config["output_dir"])
        self.assertFalse(out.exists() and any(out.glob("*/")))

    def test_isolation_global_config_unchanged(self):
        self.win.config["default_source"] = "official"
        before = json.dumps(self.win.config, ensure_ascii=False, sort_keys=True)
        self.win._prepare_official = lambda works, fmts, dest, policy="stale": ({}, [])
        self.win._run_batch_update(self._selected(), "stale", "missing", False)
        after = json.dumps(self.win.config, ensure_ascii=False, sort_keys=True)
        self.assertEqual(before, after)

    def test_explicit_run_source_overrides_config(self):
        # 对话框来源优先于右栏：config=official 也能强制跑自制分支，反之亦然
        self.win.config["default_source"] = "official"
        calls = []
        self.win._ensure_xml_batch = lambda works, fmts, title="", regen_all=False: (
            calls.append(1) or ({}, [], False))
        self.win._run_batch_update(self._selected(), "stale", "missing", False,
                                   run_source="xml")
        self.assertEqual(len(calls), 1)

        self.win.config["default_source"] = "xml"
        prepped = []
        self.win._prepare_official = lambda works, fmts, dest, policy="stale": (
            prepped.append(1) or ({}, []))
        self.win._run_batch_update(self._selected(), "stale", "missing", False,
                                   run_source="official")
        self.assertEqual(len(prepped), 1)

    def test_report_uses_explicit_run_source(self):
        self.win.config["default_source"] = "xml"
        self.win._prepare_official = lambda works, fmts, dest, policy="stale": ({}, [])
        self.win._run_batch_update(self._selected(), "stale", "missing", True,
                                   run_source="official")
        rep = Path(self.win.config["output_dir"]) / "批量更新报告.txt"
        self.assertIn("来源：official", rep.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
