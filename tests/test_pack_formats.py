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
    cfg.setdefault("xml2pdf", {})["cbeta_ebook"] = str(tmp / "xml")  # 隔离：无真实 XML 源
    cfg["_config_path"] = str(tmp / "app.json")
    # 打包分册默认 none（避免 ask 弹框）；分册测试自行覆盖。
    # 用缺省模板 {coll}.{nn}.{seg}：不分册展开即丛书名，ZIP 名与旧一致。
    cfg.setdefault("merge", {})["mode"] = "none"
    cfg["merge"]["name_template"] = "{coll}.{nn}.{seg}"
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
        stem = self.win._pack_display_stem("T0001")
        self.assertEqual(names, [f"{stem}/T0001-toc.txt", f"{stem}/T0001.txt"])
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
        stem = self.win._pack_display_stem("T0001")
        self.assertEqual((target / stem / "T0001.txt").read_text(encoding="utf-8"), "經文")
        self.assertTrue((target / stem / "T0001-toc.txt").is_file())
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


class PackDisplayNameTest(unittest.TestCase):
    """打包显示名：与合并书名书签同款（title_of），取不到回退裸 id；
    包内重名自动 _2/_3；缓存键不动。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_display_stem_and_fallback(self):
        win = self.win
        stem = win._pack_display_stem("T0001")
        self.assertTrue(stem.startswith("T0001"))
        self.assertNotEqual(stem, "T0001")  # 真实目錄有书名
        self.assertEqual(win._pack_display_stem("TX9Z9"), "TX9Z9")  # 查不到回退裸 id

    def test_unique_name_guard(self):
        from cbeta_publish.gui.main_window import MainWindow
        used = set()
        self.assertEqual(MainWindow._pack_unique_name(used, "A.pdf"), "A.pdf")
        self.assertEqual(MainWindow._pack_unique_name(used, "A.pdf"), "A_2.pdf")
        self.assertEqual(MainWindow._pack_unique_name(used, "A.pdf"), "A_3.pdf")
        self.assertEqual(MainWindow._pack_unique_name(used, "D"), "D")
        self.assertEqual(MainWindow._pack_unique_name(used, "D"), "D_2")

    def test_zip_single_file_uses_display_name(self):
        import zipfile
        win = self.win
        win.config["default_source"] = "official"
        win.config["cbeta_ebooks_dir"] = str(self.tmp / "eb")
        eb = self.tmp / "eb" / "pdf"
        eb.mkdir(parents=True, exist_ok=True)
        (eb / "T0001.pdf").write_bytes(b"PDF")
        col = Path(win.config["collections_dir"]) / "custom" / "名单.json"
        col.write_text(json.dumps({"id": "m", "name": "名单", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("名单.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()
        out = self.tmp / "zout1"
        out.mkdir(exist_ok=True)
        real_choose = win._choose_pack_fmts
        real_dir = QFileDialog.getExistingDirectory
        real_prog = win._make_progress
        real_prompt = win._prompt_save_collection
        real_box = win._wrap_box
        win._choose_pack_fmts = lambda *a, **k: ["pdf"]
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(out))
        win._make_progress = lambda title, total: (None, lambda *a, **k: True, {"finish": lambda *a, **k: None})
        win._prompt_save_collection = lambda *a, **k: None
        win._wrap_box = lambda *a, **k: None
        try:
            win._zip()
        finally:
            win._choose_pack_fmts = real_choose
            QFileDialog.getExistingDirectory = real_dir
            win._make_progress = real_prog
            win._prompt_save_collection = real_prompt
            win._wrap_box = real_box
        stem = win._pack_display_stem("T0001")
        with zipfile.ZipFile(out / "名单_pdf.zip") as z:
            self.assertEqual(z.namelist(), [f"{stem}.pdf"])

    def test_export_single_file_uses_display_name(self):
        win = self.win
        win.config["default_source"] = "official"
        win.config["cbeta_ebooks_dir"] = str(self.tmp / "eb")
        eb = self.tmp / "eb" / "pdf"
        eb.mkdir(parents=True, exist_ok=True)
        (eb / "T0001.pdf").write_bytes(b"PDF")
        col = Path(win.config["collections_dir"]) / "custom" / "名单.json"
        col.write_text(json.dumps({"id": "m", "name": "名单", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("名单.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()
        target = self.tmp / "xout1"
        target.mkdir(exist_ok=True)
        real_choose = win._choose_pack_fmts
        real_dir = QFileDialog.getExistingDirectory
        real_prog = win._make_progress
        real_prompt = win._prompt_save_collection
        real_box = win._wrap_box
        win._choose_pack_fmts = lambda *a, **k: ["pdf"]
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(target))
        win._make_progress = lambda title, total: (None, lambda *a, **k: True, {"finish": lambda *a, **k: None})
        win._prompt_save_collection = lambda *a, **k: None
        win._wrap_box = lambda *a, **k: None
        try:
            win._export()
        finally:
            win._choose_pack_fmts = real_choose
            QFileDialog.getExistingDirectory = real_dir
            win._make_progress = real_prog
            win._prompt_save_collection = real_prompt
            win._wrap_box = real_box
        stem = win._pack_display_stem("T0001")
        self.assertTrue((target / f"{stem}.pdf").is_file())
        # 缓存键不动：原文件仍在
        self.assertTrue((eb / "T0001.pdf").is_file())


class PackMissingCountsTest(unittest.TestCase):
    """ZIP/导出缺书确认：按格式分别显示缺数，不列文件名。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        win = cls.win
        win.config["default_source"] = "official"
        win.config["cbeta_ebooks_dir"] = str(cls.tmp / "eb")
        col = Path(win.config["collections_dir"]) / "custom" / "缺测.json"
        col.write_text(json.dumps({"id": "q", "name": "缺测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001", "T0002"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        eb = cls.tmp / "eb" / "pdf"
        eb.mkdir(parents=True, exist_ok=True)
        (eb / "T0001.pdf").write_bytes(b"PDF")  # 仅此一部有货

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        win = self.win
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("缺测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    def test_missing_by_fmt(self):
        from cbeta_publish.gui.main_window import MainWindow
        self.assertEqual(MainWindow._missing_by_fmt(
            ["T0001.pdf", "T0002.pdf", "T0002.epub"]),
            ["pdf 缺 2 部", "epub 缺 1 部"])
        self.assertEqual(MainWindow._missing_by_fmt([]), [])

    def _capture_question(self, fn):
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        real_choose = win._choose_pack_fmts
        real_box = win._wrap_box
        real_q = QMessageBox.question
        real_dir = QFileDialog.getExistingDirectory
        texts = []
        win._choose_pack_fmts = lambda *a, **k: ["pdf", "epub"]
        win._wrap_box = lambda *a, **k: None
        QMessageBox.question = staticmethod(
            lambda *a, **k: texts.append(a[2]) or QMessageBox.No)
        # 选「否」后继续走：在目录选择处空返回中止（只取弹窗文本，不真打）
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
        try:
            fn()
        finally:
            win._choose_pack_fmts = real_choose
            win._wrap_box = real_box
            QMessageBox.question = real_q
            QFileDialog.getExistingDirectory = real_dir
        return texts

    def test_zip_question_counts_per_fmt(self):
        win = self.win
        eb = self.tmp / "eb" / "pdf"
        eb.mkdir(parents=True, exist_ok=True)
        (eb / "T0001.pdf").write_bytes(b"PDF")  # 仅此一部有货
        texts = self._capture_question(win._zip)
        self.assertTrue(texts)
        self.assertIn("pdf 缺 1 部", texts[0])
        self.assertIn("epub 缺 2 部", texts[0])
        self.assertNotIn("T0001", texts[0])
        self.assertNotIn("T0002", texts[0])

    def test_export_question_counts_per_fmt(self):
        texts = self._capture_question(self.win._export)
        self.assertTrue(texts)
        self.assertIn("pdf 缺 1 部", texts[0])
        self.assertIn("epub 缺 2 部", texts[0])


class PackMissingSkipTest(unittest.TestCase):
    """ZIP/导出缺书选「否」= 跳过缺书继续（与合并一致）；选「取消」= 不打。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        win = cls.win
        win.config["default_source"] = "official"
        win.config["cbeta_ebooks_dir"] = str(cls.tmp / "eb")
        col = Path(win.config["collections_dir"]) / "custom" / "跳测.json"
        col.write_text(json.dumps({"id": "t", "name": "跳测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001", "T0002"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        eb = cls.tmp / "eb" / "pdf"
        eb.mkdir(parents=True, exist_ok=True)
        (eb / "T0001.pdf").write_bytes(b"PDF")  # T0002 缺货
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("跳测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, fn, answer, outdir, dl=None):
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        real_choose = win._choose_pack_fmts
        real_dir = QFileDialog.getExistingDirectory
        real_prog = win._make_progress
        real_prompt = win._prompt_save_collection
        real_box = win._wrap_box
        real_q = QMessageBox.question
        real_dl = win._download_missing
        boxes = []
        win._choose_pack_fmts = lambda *a, **k: ["pdf"]
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(outdir))
        win._make_progress = lambda title, total: (None, lambda *a, **k: True, {"finish": lambda *a, **k: None})
        win._prompt_save_collection = lambda *a, **k: None
        win._wrap_box = lambda *a, **k: boxes.append(a) or None
        if dl is not None:
            win._download_missing = dl
        if callable(answer):
            QMessageBox.question = staticmethod(lambda *a, **k: answer(*a))
        else:
            QMessageBox.question = staticmethod(lambda *a, **k: answer)
        try:
            fn()
        finally:
            win._choose_pack_fmts = real_choose
            QFileDialog.getExistingDirectory = real_dir
            win._make_progress = real_prog
            win._prompt_save_collection = real_prompt
            win._wrap_box = real_box
            QMessageBox.question = real_q
            win._download_missing = real_dl
        return boxes

    def test_zip_no_packs_present(self):
        from PySide6.QtWidgets import QMessageBox
        out = self.tmp / "zskip"
        out.mkdir(exist_ok=True)
        boxes = self._run(self.win._zip, QMessageBox.No, out)
        self.assertFalse([a for a in boxes if "未全部下载" in str(a)], boxes)
        zpath = out / "跳测_pdf.zip"
        self.assertTrue(zpath.is_file())
        stem1 = self.win._pack_display_stem("T0001")
        with zipfile.ZipFile(zpath) as z:
            self.assertEqual(z.namelist(), [f"{stem1}.pdf"])  # 缺的 T0002 不在包内

    def test_zip_download_then_continue(self):
        # 选「是」下载后仍缺 → 弹「是否继续」选「是」→ 照常打包
        from PySide6.QtWidgets import QMessageBox
        out = self.tmp / "zdlcont"
        out.mkdir(exist_ok=True)
        seen = []
        def ans(*_a):
            seen.append(1)
            return QMessageBox.Yes   # 第一次=先下载，第二次=继续
        boxes = self._run(self.win._zip, ans, out, dl=lambda *a, **k: None)
        self.assertTrue((out / "跳测_pdf.zip").is_file())
        self.assertFalse([a for a in boxes if "已取消打包" in str(a)], boxes)
        self.assertEqual(len(seen), 2)   # 先下载 + 是否继续

    def test_zip_download_then_decline(self):
        # 下载后仍缺 → 继续问选「否」→ 取消打包
        from PySide6.QtWidgets import QMessageBox
        out = self.tmp / "zdldecline"
        out.mkdir(exist_ok=True)
        state = {"n": 0}
        def ans(*_a):
            state["n"] += 1
            return QMessageBox.Yes if state["n"] == 1 else QMessageBox.No
        boxes = self._run(self.win._zip, ans, out, dl=lambda *a, **k: None)
        self.assertFalse((out / "跳测_pdf.zip").exists())
        self.assertTrue([a for a in boxes if "已取消打包" in str(a)], boxes)

    def test_export_download_then_continue(self):
        from PySide6.QtWidgets import QMessageBox
        target = self.tmp / "xdlcont"
        target.mkdir(exist_ok=True)
        self._run(self.win._export, lambda *a: QMessageBox.Yes, target,
                  dl=lambda *a, **k: None)
        stem1 = self.win._pack_display_stem("T0001")
        self.assertTrue((target / f"{stem1}.pdf").is_file())

    def test_zip_cancel_aborts(self):
        from PySide6.QtWidgets import QMessageBox
        out = self.tmp / "zcancel"
        out.mkdir(exist_ok=True)
        self._run(self.win._zip, QMessageBox.Cancel, out)
        self.assertEqual(list(out.iterdir()), [])  # 无产物

    def test_export_no_exports_present(self):
        from PySide6.QtWidgets import QMessageBox
        target = self.tmp / "xskip"
        target.mkdir(exist_ok=True)
        boxes = self._run(self.win._export, QMessageBox.No, target)
        self.assertFalse([a for a in boxes if "未全部下载" in str(a)], boxes)
        stem1 = self.win._pack_display_stem("T0001")
        self.assertTrue((target / f"{stem1}.pdf").is_file())
        self.assertEqual(len(list(target.iterdir())), 1)  # 只有有货的一部

    def test_export_cancel_aborts(self):
        from PySide6.QtWidgets import QMessageBox
        target = self.tmp / "xcancel"
        target.mkdir(exist_ok=True)
        self._run(self.win._export, QMessageBox.Cancel, target)
        self.assertEqual(list(target.iterdir()), [])  # 无产物


class PackStalePromptTest(unittest.TestCase):
    """官方书源 XML 较新（即使产物已存在）也提示「未下载/需更新」（S3 单部接入）。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        win = cls.win
        win.config["default_source"] = "official"
        win.config["cbeta_ebooks_dir"] = str(cls.tmp / "eb")
        col = Path(win.config["collections_dir"]) / "custom" / "过期测.json"
        col.write_text(json.dumps({"id": "s", "name": "过期测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("过期测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _capture_question(self, fn):
        from PySide6.QtWidgets import QMessageBox
        win = self.win
        real_choose = win._choose_pack_fmts
        real_box = win._wrap_box
        real_q = QMessageBox.question
        real_dir = QFileDialog.getExistingDirectory
        texts = []
        win._choose_pack_fmts = lambda *a, **k: ["pdf"]
        win._wrap_box = lambda *a, **k: None
        QMessageBox.question = staticmethod(
            lambda *a, **k: texts.append(a[2]) or QMessageBox.No)
        QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
        try:
            fn()
        finally:
            win._choose_pack_fmts = real_choose
            win._wrap_box = real_box
            QMessageBox.question = real_q
            QFileDialog.getExistingDirectory = real_dir
        return texts

    def test_source_newer_triggers_prompt(self):
        eb = self.tmp / "eb" / "pdf"
        eb.mkdir(parents=True, exist_ok=True)
        p = eb / "T0001.pdf"
        p.write_bytes(b"PDF")
        os.utime(p, (1000.0, 1000.0))
        xroot = Path(self.win.config["xml2pdf"]["cbeta_ebook"])
        d = xroot / "T0001 經"
        d.mkdir(parents=True, exist_ok=True)
        xf = d / "T0001.xml"
        xf.write_text("<x/>", encoding="utf-8")
        os.utime(xf, (2000.0, 2000.0))
        texts = self._capture_question(self.win._zip)
        self.assertTrue(texts)
        self.assertIn("需更新", texts[0])
        self.assertIn("pdf 缺 1 部", texts[0])


if __name__ == "__main__":
    unittest.main()
