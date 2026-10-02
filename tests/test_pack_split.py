# -*- coding: utf-8 -*-
"""ZIP/导出 按分册模式（volume/catalog/manual/ask）；none 保持单文件/平铺。"""
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None
WORKS = ["T0001", "T0002", "T0003"]


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window(name_template="{coll}.{nn}.{seg}"):
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    col = tmp / "collections" / "custom"
    col.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    (col / "测.json").write_text(json.dumps(
        {"id": "c", "name": "测", "category": "custom", "tags": [],
         "work_ids": list(WORKS)}, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["cbeta_ebooks_dir"] = str(tmp / "eb")
    cfg["update_interval"] = "manual"
    cfg["default_source"] = "official"
    cfg["_config_path"] = str(tmp / "app.json")
    cfg["merge"] = {"mode": "none", "depth": 2, "name_template": name_template}
    win = MainWindow(cfg)
    for w in WORKS:
        d = tmp / "eb" / "pdf"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{w}.pdf").write_bytes(b"P")
    for i in range(win.coll_combo.count()):
        if str(win.coll_combo.itemData(i)).endswith("测.json"):
            win.coll_combo.setCurrentIndex(i)
            break
    _ensure_app().processEvents()
    return win, tmp


class _Patch:
    def __init__(self, win, fmts, outdir):
        self.win = win
        self.fmts = fmts
        self.outdir = outdir
        self.boxes = []

    def __enter__(self):
        w = self.win
        self._rc = w._choose_pack_fmts
        self._rd = QFileDialog.getExistingDirectory
        self._rp = w._make_progress
        self._rs = w._prompt_save_collection
        self._rb = w._wrap_box
        self._rq = QMessageBox.question
        w._choose_pack_fmts = lambda *a, **k: self.fmts
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(self.outdir))
        w._make_progress = lambda t, n: (None, lambda *a, **k: True,
                                         {"finish": lambda *a, **k: None})
        w._prompt_save_collection = lambda *a, **k: None
        w._wrap_box = lambda *a, **k: self.boxes.append(a) or None
        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)   # 缺书→跳过继续
        return w

    def __exit__(self, *a):
        w = self.win
        w._choose_pack_fmts = self._rc
        QFileDialog.getExistingDirectory = self._rd
        w._make_progress = self._rp
        w._prompt_save_collection = self._rs
        w._wrap_box = self._rb
        QMessageBox.question = self._rq


class PackSplitTest(unittest.TestCase):
    def test_none_single_zip(self):
        win, tmp = _make_window()
        try:
            out = tmp / "z"
            out.mkdir()
            with _Patch(win, ["pdf"], out):
                win._zip()
            zips = list(out.glob("*.zip"))
            self.assertEqual([p.name for p in zips], ["测_pdf.zip"])   # none 用原名
            with zipfile.ZipFile(zips[0]) as z:
                self.assertEqual(len(z.namelist()), 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_none_zip_follows_template_vars(self):
        # 不分册 ZIP 也走模板：{source}/{date8} 可用（默认模板仍等于丛书名）
        win, tmp = _make_window(name_template="{coll}.{source}.{date8}")
        try:
            out = tmp / "z"
            out.mkdir()
            with _Patch(win, ["pdf"], out):
                win._zip()
            zips = [p.name for p in out.glob("*.zip")]
            self.assertEqual(len(zips), 1)
            self.assertRegex(zips[0], r"^测\.官方\.\d{8}_pdf\.zip$")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_manual_split_zips(self):
        win, tmp = _make_window()
        try:
            win._coll_dict(win.coll_combo.currentData())["manual_volumes"] = [
                {"title": "甲", "work_ids": ["T0001"]},
                {"title": "乙", "work_ids": ["T0002", "T0003"]},
            ]
            win.config["merge"]["mode"] = "manual"
            out = tmp / "z"
            out.mkdir()
            with _Patch(win, ["pdf"], out):
                win._zip()
            zips = sorted(p.name for p in out.glob("*.zip"))
            self.assertEqual(len(zips), 2)
            self.assertTrue(any("第1册" in n for n in zips), zips)
            self.assertTrue(any("第2册" in n for n in zips), zips)
            for n in zips:
                with zipfile.ZipFile(out / n) as z:
                    self.assertGreaterEqual(len(z.namelist()), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_catalog_split_matches_groups(self):
        win, tmp = _make_window()
        try:
            win.config["merge"]["mode"] = "catalog"
            win.config["merge"]["depth"] = 1
            d = win._coll_dict(win.coll_combo.currentData())
            groups = [g for g in win._group_works(d, WORKS, WORKS, WORKS,
                                                  mode="catalog", depth=1)
                      if g["works"]]
            out = tmp / "z"
            out.mkdir()
            with _Patch(win, ["pdf"], out):
                win._zip()
            zips = list(out.glob("*.zip"))
            self.assertEqual(len(zips), len(groups))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_export_split_dirs(self):
        win, tmp = _make_window()
        try:
            win._coll_dict(win.coll_combo.currentData())["manual_volumes"] = [
                {"title": "", "work_ids": ["T0001"]},
                {"title": "", "work_ids": ["T0002", "T0003"]},
            ]
            win.config["merge"]["mode"] = "manual"
            target = tmp / "x"
            target.mkdir()
            with _Patch(win, ["pdf"], target):
                win._export()
            dirs = sorted(p.name for p in target.iterdir() if p.is_dir())
            self.assertEqual(len(dirs), 2)
            for n in dirs:
                self.assertTrue(n.endswith("_pdf"), n)
                self.assertTrue(all(p.suffix == ".pdf" for p in (target / n).iterdir()))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_group_skipped(self):
        win, tmp = _make_window()
        try:
            win._coll_dict(win.coll_combo.currentData())["manual_volumes"] = [
                {"title": "甲", "work_ids": ["T0001", "T0003"]},
                {"title": "乙", "work_ids": ["T0002"]},
            ]
            win.config["merge"]["mode"] = "manual"
            (tmp / "eb" / "pdf" / "T0002.pdf").unlink()   # 乙组缺文件
            out = tmp / "z"
            out.mkdir()
            with _Patch(win, ["pdf"], out):
                win._zip()
            zips = list(out.glob("*.zip"))
            self.assertEqual(len(zips), 1)                # 乙组空 → 跳过
            self.assertIn("第1册", zips[0].name)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ask_dialog_mode_applied(self):
        from types import SimpleNamespace
        win, tmp = _make_window()
        try:
            win.config["merge"]["mode"] = "ask"
            win._coll_dict(win.coll_combo.currentData())["manual_volumes"] = [
                {"title": "", "work_ids": ["T0001"]},
                {"title": "", "work_ids": ["T0002", "T0003"]},
            ]

            class _D:
                def __init__(self, *a, **k): pass
                def setWindowTitle(self, *a): pass
                def _refresh(self): pass
                def exec(self): return 1               # Accepted
                def chosen(self): return ("manual", 2)
                def template(self): return "{coll}.{nn}.{seg}"

            import cbeta_publish.gui.merge_dialog as md
            real = md.MergeDialog
            md.MergeDialog = _D
            out = tmp / "z"
            out.mkdir()
            try:
                with _Patch(win, ["pdf"], out):
                    win._zip()
            finally:
                md.MergeDialog = real
            self.assertEqual(len(list(out.glob("*.zip"))), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
