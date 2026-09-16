# -*- coding: utf-8 -*-
"""右栏「发布」分组框（框住格式+发布按钮）与部类树合并（般若部類 01）。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox, QLabel  # noqa: E402

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
    (tmp / "collections" / "custom").mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    (tmp / "collections" / "custom" / "測試叢書.json").write_text(json.dumps({
        "id": "t", "name": "測試叢書", "category": "custom", "tags": [],
        "work_ids": ["T0001", "T0002"]}, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class RightPanelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_publish_group_wraps_format_and_buttons(self):
        win = self.win
        box = win.findChild(QGroupBox, None)
        # 找到标题为「发布」的分组框
        groups = [g for g in win.findChildren(QGroupBox) if g.title() == "发布"]
        self.assertEqual(len(groups), 1, [g.title() for g in win.findChildren(QGroupBox)])
        g = groups[0]
        for w in (win.chk_pdf, win.chk_epub, win.btn_merge, win.btn_zip,
                  win.btn_export, win.btn_download):
            self.assertTrue(g.isAncestorOf(w), w)
        # 旧「发布:」标签已移除
        texts = [lb.text() for lb in g.findChildren(QLabel)]
        self.assertNotIn("发布:", texts)

    def test_source_preset_row(self):
        # 来源单选（官方/自制）+ 预设下拉在发布分组框内；切换写回全局
        import json
        win = self.win
        win.config["default_source"] = "official"
        win._sync_source_preset_ui()
        _ensure_app().processEvents()
        groups = [g for g in win.findChildren(QGroupBox) if g.title() == "发布"]
        g = groups[0]
        for w in (win.rb_official, win.rb_made, win.cb_preset, win.btn_preset_edit):
            self.assertTrue(g.isAncestorOf(w), w)
        self.assertEqual([win.rb_official.text(), win.rb_made.text()], ["官方", "自制"])
        # 默认 official：预设行置灰
        self.assertTrue(win.rb_official.isChecked())
        self.assertFalse(win.cb_preset.isEnabled())
        # 切自制：写回配置并落盘，预设行启用
        win.rb_made.setChecked(True)
        win.src_group.buttonClicked.emit(win.rb_made)
        _ensure_app().processEvents()
        self.assertEqual(win.config["default_source"], "xml")
        disk = json.loads(Path(win._config_path).read_text(encoding="utf-8"))
        self.assertEqual(disk["default_source"], "xml")
        self.assertTrue(win.cb_preset.isEnabled())
        # 预设下拉：首项出厂默认 + 预设目录合法项
        self.assertEqual(win.cb_preset.itemData(0), "")
        # 切回官方
        win.rb_official.setChecked(True)
        win.src_group.buttonClicked.emit(win.rb_official)
        _ensure_app().processEvents()
        self.assertEqual(win.config["default_source"], "official")
        self.assertFalse(win.cb_preset.isEnabled())

    def test_preset_dialog_opens(self):
        # 上游 XmlOptionsDialog 可实例化（调整入口不断链）
        import sys
        sys.path.insert(0, "E:/dev/cbeta/xml2pdf")
        from pycbeta.gui.panel import XmlOptionsDialog
        from cbeta_publish.books import xml2pdf_bridge as b
        presets = b.load_preset_dict("E:/dev/cbeta/xml2pdf/run.json", {})
        self.assertIsInstance(presets, dict)
        dlg = XmlOptionsDialog(presets or None, self.win)
        try:
            self.assertIsNotNone(dlg.panel)
        finally:
            dlg.close()

    def test_download_button_label(self):
        self.assertEqual(self.win.btn_download.text(), "下载/更新")

    def test_bulei_filter_default_shows_all(self):
        # 部类过滤下拉框默认应显示「全部部类」（可编辑 combo 曾被 clear 成 currentIndex=-1）
        win = self.win
        win.nav_combo.setCurrentText("部类")
        _ensure_app().processEvents()
        b = win.bulei_filter
        self.assertEqual(b.currentIndex(), 0)
        self.assertEqual(b.currentText(), "全部部类")
        self.assertEqual(b.itemText(0), "全部部类")
        self.assertEqual(b.lineEdit().text(), "全部部类")

    def test_search_has_label(self):
        win = self.win
        labels = [lb.text() for lb in win.findChildren(QLabel)]
        self.assertIn("搜索：", labels)

    def _nav(self, mode, n=8):
        self.win.nav_combo.setCurrentText(mode)
        for _ in range(n):
            _ensure_app().processEvents()

    def test_tripitaka_secondary_filter(self):
        win = self.win
        self._nav("三藏")
        f = win.tripitaka_filter
        self.assertEqual(f.itemText(0), "全部部类")
        self.assertGreater(f.count(), 1)
        before = win.tree.topLevelItemCount()
        f.setCurrentIndex(1)
        for _ in range(10):
            _ensure_app().processEvents()
        self.assertEqual(win.tree.topLevelItemCount(), 1)
        top = win.tree.topLevelItem(0)
        self.assertGreater(top.childCount(), 0)
        self.assertIn(f.currentText(), top.child(0).text(0))
        f.setCurrentIndex(0)
        for _ in range(10):
            _ensure_app().processEvents()
        self.assertEqual(win.tree.topLevelItemCount(), before)

    def test_vol_secondary_filter(self):
        win = self.win
        self._nav("刊本")
        f = win.vol_filter
        # 过滤项 = 刊本（一级目录本身）
        self.assertEqual(f.itemText(0), "全部刊本")
        self.assertGreater(f.count(), 1)
        before = win.tree.topLevelItemCount()
        f.setCurrentIndex(1)
        for _ in range(10):
            _ensure_app().processEvents()
        self.assertEqual(win.tree.topLevelItemCount(), 1)
        self.assertIn(f.currentText(), win.tree.topLevelItem(0).text(0))
        f.setCurrentIndex(0)
        for _ in range(10):
            _ensure_app().processEvents()
        self.assertEqual(win.tree.topLevelItemCount(), before)

    def test_stroke_label_strips_suffix(self):
        # 笔画分组标题「1畫(stroke)」不应把 (stroke) 显示出来
        win = self.win
        self.assertEqual(win._stroke_label("1畫(stroke)"), "1畫")
        self.assertEqual(win._stroke_label("26畫 (stroke)"), "26畫")
        self.assertEqual(win._stroke_label("1畫"), "1畫")
        self._nav("作者")
        win.author_radios["笔画排序"].setChecked(True)
        for _ in range(10):
            _ensure_app().processEvents()
        tops = [win.tree.topLevelItem(i).text(0) for i in range(win.tree.topLevelItemCount())]
        self.assertTrue(tops)
        self.assertFalse([t for t in tops if "stroke" in t.lower()], tops)

    def test_search_case_insensitive(self):
        win = self.win
        self._nav("刊本")
        counts = []
        for kw in ("T0220", "t0220"):
            win.search.setText(kw)
            for _ in range(10):
                _ensure_app().processEvents()
            counts.append(len(win._search_results))
        self.assertGreater(counts[0], 0, "T0220 无结果")
        self.assertEqual(counts[0], counts[1], "大小写结果不一致")
        win.search.clear()
        for _ in range(4):
            _ensure_app().processEvents()

    def test_author_sort_radios(self):
        from PySide6.QtWidgets import QRadioButton
        win = self.win
        labels = [r.text() for r in win.findChildren(QRadioButton)]
        for t in ("拼音排序", "笔画排序", "朝代排序"):
            self.assertIn(t, labels)
        self.assertEqual(win._author_sort_mode(), "拼音排序")
        win.author_radios["朝代排序"].setChecked(True)
        for _ in range(6):
            _ensure_app().processEvents()
        self.assertEqual(win._author_sort_mode(), "朝代排序")

    def test_coll_tree_lists_work_titles(self):
        import re
        win = self.win
        self._nav("丛书")
        self.assertGreater(win.tree.topLevelItemCount(), 0)
        node = win.tree.topLevelItem(0)
        self.assertGreater(node.childCount(), 0, "丛书树未列出经书")
        for i in range(node.childCount()):
            txt = node.child(i).text(0)
            self.assertTrue(txt.strip())
            self.assertRegex(txt, r"^[A-Z]+\d", txt)

    def test_search_works_in_all_views(self):
        win = self.win
        cases = [("部类", "般若"), ("三藏", "阿含"), ("刊本", "T0001"),
                 ("朝代", "東漢"), ("丛书", "測試")]
        for mode, kw in cases:
            self._nav(mode)
            win.search.setText(kw)
            for _ in range(10):
                _ensure_app().processEvents()
            self.assertGreater(len(win._search_results), 0, f"{mode} 搜索 {kw!r} 无结果")
        win.search.clear()
        for _ in range(4):
            _ensure_app().processEvents()

    def test_bulei_tree_has_banruo_01(self):
        # 部类树：般若部類 下应有 01（由 bulei.txt 补入）
        win = self.win
        win.nav_combo.setCurrentText("部类")
        _ensure_app().processEvents()
        top = None
        for i in range(win.tree.topLevelItemCount()):
            it = win.tree.topLevelItem(i)
            if "般若部類" in it.text(0):
                top = it
                break
        self.assertIsNotNone(top, "未找到般若部類")
        kids = [top.child(j).text(0) for j in range(top.childCount())]
        self.assertTrue(any(k.startswith("01") for k in kids), kids)
        self.assertTrue(any(k.startswith("09") for k in kids), kids)
        self.assertEqual([k.split()[0] for k in kids],
                         ["%02d" % i for i in range(1, 14)])


if __name__ == "__main__":
    unittest.main()
