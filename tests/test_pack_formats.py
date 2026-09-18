# -*- coding: utf-8 -*-
"""打包格式（ZIP/导出）：官方 7 种、自制仅 pdf/epub；目录型（html/docx/odt/txt/txt_notes）只打包不合并。"""
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

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


class PackAvailTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_official_lists_seven(self):
        from cbeta_publish.books import official_ebook_source as oes
        self.win.config["default_source"] = "official"
        self.assertEqual(self.win._pack_avail_fmts(), list(oes.PACK_FORMATS))
        self.assertEqual(len(oes.PACK_FORMATS), 7)

    def test_xml_lists_three(self):
        self.win.config["default_source"] = "xml"
        try:
            self.assertEqual(self.win._pack_avail_fmts(), ["pdf", "epub", "docx"])
        finally:
            self.win.config["default_source"] = "official"

    def test_pack_hint_is_right_aligned(self):
        win = self.win
        self.assertEqual(win.lbl_pack_hint.text(), "（其它格式用ZIP/导出）")
        lay = win.chk_pdf.parentWidget().layout()
        items = [lay.itemAt(i) for i in range(lay.count())]
        hint_at = next(i for i, it in enumerate(items) if it.widget() is win.lbl_pack_hint)
        stretch_at = next(i for i, it in enumerate(items) if it.spacerItem() is not None)
        self.assertGreater(hint_at, stretch_at)   # 提示在 stretch 之后 = 靠右

    def test_format_checkbox_tooltips(self):
        win = self.win
        for cb in (win.chk_pdf, win.chk_epub, win.chk_docx):
            self.assertTrue(cb.toolTip())
        self.assertIn("不参与合并", win.chk_docx.toolTip())

    def test_docx_icons_exist_and_differ(self):
        d = Path(__file__).resolve().parents[1] / "cbeta_publish" / "gui" / "theme" / "icons"
        c = (d / "docx.png").read_bytes()
        g = (d / "docx_gray.png").read_bytes()
        self.assertTrue(c and g and c != g)   # 有=蓝、无=灰，两图不同


class PackDirFormatTest(unittest.TestCase):
    """目录型只打包：ZIP 按 部/相对路径 写入；导出整树拷贝。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        win = cls.win
        win.config["default_source"] = "official"
        win.config["cbeta_ebooks_dir"] = str(cls.tmp / "eb")
        col = Path(win.config["collections_dir"]) / "custom" / "包测.json"
        col.write_text(json.dumps({"id": "p", "name": "包测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("包测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()
        # 目录型产物固件：txt 解压后目录
        d = cls.tmp / "eb" / "txt" / "T0001"
        d.mkdir(parents=True)
        (d / "T0001.txt").write_text("經文", encoding="utf-8")
        (d / "T0001-toc.txt").write_text("目次", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _patch_all(self, fmts, outdir):
        win = self.win
        real_choose = win._choose_pack_fmts
        real_dir = QFileDialog.getExistingDirectory
        real_prog = win._make_progress
        real_prompt = win._prompt_save_collection
        real_box = win._wrap_box
        win._choose_pack_fmts = lambda *a, **k: fmts
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(outdir))
        win._make_progress = lambda title, total: (None, lambda *a, **k: True, {"finish": lambda *a, **k: None})
        win._prompt_save_collection = lambda *a, **k: None
        win._wrap_box = lambda *a, **k: None
        def restore():
            win._choose_pack_fmts = real_choose
            QFileDialog.getExistingDirectory = real_dir
            win._make_progress = real_prog
            win._prompt_save_collection = real_prompt
            win._wrap_box = real_box
        return restore

    def test_zip_packs_dir_tree(self):
        out = self.tmp / "zout"
        out.mkdir()
        restore = self._patch_all(["txt"], out)
        self.win.tab_bottom.setCurrentIndex(0)
        try:
            self.win._zip()
        finally:
            restore()
        zpath = out / "包测_txt.zip"
        self.assertTrue(zpath.is_file())
        with zipfile.ZipFile(zpath) as z:
            names = sorted(z.namelist())
        self.assertEqual(names, ["T0001/T0001-toc.txt", "T0001/T0001.txt"])
        self.assertEqual(self.win.tab_bottom.currentIndex(), 1)   # 切到丛书信息页

    def test_export_copies_dir_tree(self):
        target = self.tmp / "xout"
        target.mkdir()
        restore = self._patch_all(["txt"], target)
        self.win.tab_bottom.setCurrentIndex(0)
        try:
            self.win._export()
        finally:
            restore()
        self.assertEqual((target / "T0001" / "T0001.txt").read_text(encoding="utf-8"), "經文")
        self.assertTrue((target / "T0001" / "T0001-toc.txt").is_file())
        self.assertEqual(self.win.tab_bottom.currentIndex(), 1)   # 切到丛书信息页

    def test_cancel_chooses_nothing(self):
        win = self.win
        real_choose = win._choose_pack_fmts
        real_dir = QFileDialog.getExistingDirectory
        win._choose_pack_fmts = lambda *a, **k: None
        QFileDialog.getExistingDirectory = staticmethod(
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not prompt")))
        try:
            win._zip()
            win._export()
        finally:
            win._choose_pack_fmts = real_choose
            QFileDialog.getExistingDirectory = real_dir


if __name__ == "__main__":
    unittest.main()
