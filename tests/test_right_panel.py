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
        for w in (win.chk_pdf, win.chk_epub, win.chk_docx, win.btn_merge, win.btn_zip,
                  win.btn_export, win.btn_download):
            self.assertTrue(g.isAncestorOf(w), w)
        # 旧「发布:」标签已移除
        texts = [lb.text() for lb in g.findChildren(QLabel)]
        self.assertNotIn("发布:", texts)

    def test_source_preset_row(self):
        # 来源单选（官方/自制）+ 预设下拉在发布分组框内；切换写回全局
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

    def test_make_buttons_switch_with_source(self):
        # 来源=自制 → 显示「自制/重制」，隐藏「下载/更新」；来源=官方反之
        win = self.win
        win.config["default_source"] = "official"
        win._sync_source_preset_ui()
        _ensure_app().processEvents()
        self.assertTrue(win.btn_download.isVisibleTo(win))
        self.assertFalse(win.btn_make.isVisibleTo(win))
        self.assertFalse(win.btn_remake.isVisibleTo(win))
        win.config["default_source"] = "xml"
        win._sync_source_preset_ui()
        _ensure_app().processEvents()
        self.assertFalse(win.btn_download.isVisibleTo(win))
        self.assertTrue(win.btn_make.isVisibleTo(win))
        self.assertTrue(win.btn_remake.isVisibleTo(win))
        self.assertEqual([win.btn_make.text(), win.btn_remake.text()], ["自制", "重制"])
        self.assertFalse(hasattr(win, "btn_verify"))    # 「校验重制」按钮已取消
        self.assertIn("缺失", win.btn_make.toolTip())
        self.assertIn("重新生成", win.btn_remake.toolTip())
        # 预设下拉 + 调整 紧跟「自制」单选右侧（同一行）
        sh = win.rb_made.parent().layout()
        self.assertGreater(sh.indexOf(win.cb_preset), sh.indexOf(win.rb_made))
        self.assertGreater(sh.indexOf(win.btn_preset_edit), sh.indexOf(win.cb_preset))

    def test_make_button_generates_missing_only(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        tmp = self.tmp / "mk"
        (tmp / "presets").mkdir(parents=True, exist_ok=True)
        win.config.setdefault("xml2pdf", {}).update({"path": str(tmp), "preset": "",
                                                     "verify_build": False})
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(self.tmp / "mk_out")
        col = Path(win.config["collections_dir"]) / "custom" / "mk.json"
        col.write_text(json.dumps({"id": "mk", "name": "mk", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("mk.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(False)
        calls = []
        real = b.convert

        def fake(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append(str(out))
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"x")
            return Path(out)
        b.convert = fake
        try:
            win._on_make_button(False)          # 自制 = 仅缺
            _ensure_app().processEvents()
        finally:
            b.convert = real
        self.assertEqual(len(calls), 1)
        calls.clear()
        b.convert = fake
        try:
            win._on_make_button(False)          # 再次「自制」= 已有 → 复用，不重生成
            _ensure_app().processEvents()
        finally:
            b.convert = real
        self.assertEqual(len(calls), 0)          # 复用关键回归
        calls.clear()
        b.convert = fake
        try:
            win._on_make_button(True)           # 重制 = 全部
            _ensure_app().processEvents()
        finally:
            b.convert = real
        self.assertEqual(len(calls), 1)          # 已有产物也重新生成
        col.unlink(missing_ok=True)

    def test_tree_colors(self):
        # 目录树：选中/悬停浅蓝样式；书叶文字黑色，分组节点不变
        from PySide6.QtCore import Qt
        win = self.win
        qss = win.tree.styleSheet()
        self.assertIn("#bbdefb", qss)          # 选中（与中栏列表一致）
        self.assertIn("#fff3c4", qss)          # 悬停（与中栏列表一致）
        self.assertIn("#90caf9", qss)          # 选中+悬停
        win.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        ed = win.tree.topLevelItem(0)          # 刊本（分组节点）
        self.assertEqual(ed.foreground(0).style(), Qt.NoBrush)   # 未設色→走主题色
        vol = next((ed.child(i) for i in range(ed.childCount())
                    if ed.child(i).childCount()), None)
        self.assertIsNotNone(vol)
        self.assertEqual(vol.foreground(0).style(), Qt.NoBrush)  # 册（分组）也不变
        leaf = vol.child(0)                                       # 经（书叶）
        self.assertEqual(leaf.foreground(0).color().name(), "#000000")

    def test_nav_is_radio_bar(self):
        # 左栏「视图」由下拉改为单选（接口仿 QComboBox，调用方不变）
        from cbeta_publish.gui.main_window import _RadioBar
        win = self.win
        self.assertIsInstance(win.nav_combo, _RadioBar)
        self.assertEqual([b.text() for b in win.nav_combo._btns],
                         ["部类", "三藏", "刊本", "朝代", "作者", "丛书"])
        self.assertEqual(win.nav_combo.currentText(), win.nav_combo.currentText())
        seen = []
        win.nav_combo.currentTextChanged.connect(lambda m: seen.append(m))
        win.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        self.assertEqual(win.nav_combo.currentText(), "刊本")
        self.assertEqual(seen, ["刊本"])
        # blockSignals 时不发信号（既有测试用法）
        seen.clear()
        win.nav_combo.blockSignals(True)
        win.nav_combo.setCurrentText("部类")
        win.nav_combo.blockSignals(False)
        self.assertEqual(seen, [])
        self.assertEqual(win.nav_combo.currentText(), "部类")

    def test_ebook_path_follows_source(self):
        # 右栏「已有」标志随来源：官方→cbeta_ebooks；自制→xml_to_ebooks_dir
        import tempfile
        from pathlib import Path as _P
        win = self.win
        xb = _P(tempfile.mkdtemp())
        win.config["xml_to_ebooks_dir"] = str(xb)
        win.config["default_source"] = "xml"
        self.assertIsNone(win._ebook_path("T0099", "pdf"))     # 无文件
        (xb / "pdf").mkdir(parents=True, exist_ok=True)
        (xb / "pdf" / "T0099.pdf").write_bytes(b"x")
        self.assertEqual(win._ebook_path("T0099", "pdf"), xb / "pdf" / "T0099.pdf")
        (xb / "pdf" / "T0099.pdf").unlink()
        (xb / "pdf" / "T0099 中論.pdf").write_bytes(b"x")    # 同目录异名也认（通配）
        self.assertEqual(win._ebook_path("T0099", "pdf"), xb / "pdf" / "T0099 中論.pdf")
        win.config["default_source"] = "official"
        p = win._ebook_path("T0099", "pdf")                     # 官方目录（可能不存在→None）
        if p is not None:
            self.assertNotEqual(str(p).startswith(str(xb)), True)
        win.config["default_source"] = "xml"

    def test_open_ebook_rules(self):
        # 双击书名：先 PDF 再 epub，都没有则无反应；双击图标：只开该格式
        import tempfile
        from pathlib import Path as _P
        from PySide6.QtGui import QDesktopServices
        win = self.win
        opened = []
        real = QDesktopServices.openUrl
        QDesktopServices.openUrl = staticmethod(lambda url: opened.append(url.toLocalFile()))
        xb = _P(tempfile.mkdtemp())
        win.config["xml_to_ebooks_dir"] = str(xb)
        win.config["default_source"] = "xml"
        try:
            # 无文件：双击书名无反应（返回 False，不打开）
            self.assertFalse(win._open_ebook("T0200", "pdf"))
            self.assertEqual(opened, [])
            # 只有 epub：双击书名打开 epub；双击 pdf 图标无反应
            (xb / "epub").mkdir(parents=True, exist_ok=True)
            (xb / "epub" / "T0200.epub").write_bytes(b"x")
            self.assertFalse(win._open_ebook("T0200", "pdf", only_prefer=True))
            self.assertEqual(opened, [])
            self.assertTrue(win._open_ebook("T0200", "pdf"))
            self.assertTrue(opened[-1].endswith("T0200.epub"))
            # pdf + epub 都有：双击书名优先 pdf；图标各自打开
            (xb / "pdf").mkdir(parents=True, exist_ok=True)
            (xb / "pdf" / "T0200.pdf").write_bytes(b"x")
            self.assertTrue(win._open_ebook("T0200", "pdf"))
            self.assertTrue(opened[-1].endswith("T0200.pdf"))
            self.assertTrue(win._open_ebook("T0200", "epub", only_prefer=True))
            self.assertTrue(opened[-1].endswith("T0200.epub"))
        finally:
            QDesktopServices.openUrl = real
            win.config["default_source"] = "official"

    def test_transient_preset_from_adjust(self):
        # 「调整…」确定即临时生效（不保存）：自制用临时预设、强制重生成、原预设不变
        import json as _json
        import tempfile
        from pathlib import Path as _P
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        root = _P(tempfile.mkdtemp())
        (root / "presets").mkdir(parents=True)
        (root / "presets" / "a5.json").write_text('{"default_page": "a5"}', encoding="utf-8")
        win.config["xml2pdf"]["path"] = str(root)
        win.config["xml2pdf"]["preset"] = "a5"
        win.config["xml2pdf"]["verify_build"] = False
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(root / "out")
        (root / "out" / "pdf").mkdir(parents=True)
        # 已有产物（旧预设生成）→ 一般情况下"仅缺"会跳过
        (root / "out" / "pdf" / "T0001.pdf").write_bytes(b"old")
        # 拟「调整…」结果：纸张 A4
        win._set_transient_preset({"default_page": "a4"})
        self.assertIsNotNone(win._tmp_preset)
        self.assertIn("本次", win.lbl_preset.text())
        self.assertEqual(win._run_preset(), win._tmp_preset)
        self.assertEqual(_json.loads(win._tmp_preset.read_text(encoding="utf-8")),
                         {"default_page": "a4"})
        self.assertEqual(_json.loads((root / "presets" / "a5.json").read_text(encoding="utf-8")),
                         {"default_page": "a5"})          # 原预设未变
        # 「自制」→ 用临时预设，且强制重新生成（否则旧产物被跳过）
        col = _P(win.config["collections_dir"]) / "custom" / "tr.json"
        col.write_text(_json.dumps({"id": "tr", "name": "tr", "category": "custom",
                                    "tags": [], "work_ids": ["T0001"]}, ensure_ascii=False),
                       encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("tr.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        _ensure_app().processEvents()
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(False)
        win.chk_docx.setChecked(False)
        win._wrap_box = lambda *a, **k: 0
        calls = []
        real = b.convert

        def fake(wk, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append(preset)
            _P(out).parent.mkdir(parents=True, exist_ok=True)
            _P(out).write_bytes(b"new")
            return _P(out)
        b.convert = fake
        try:
            win._on_make_button(False)
            _ensure_app().processEvents()
        finally:
            b.convert = real
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], win._tmp_preset)              # 用的是临时预设
        self.assertEqual((root / "out" / "pdf" / "T0001.pdf").read_bytes(), b"new")
        # 改选预设 → 放弃临时预设（临时文件删除、标签复原）
        tmp_path = win._tmp_preset
        win.cb_preset.setCurrentIndex(0)
        win._on_preset_changed()
        self.assertIsNone(win._tmp_preset)
        self.assertFalse(_P(tmp_path).exists())
        self.assertNotIn("本次", win.lbl_preset.text())

    def test_checked_fmts_and_no_option_switches(self):
        # 右栏勾选 → -f；convert 只传 -i/-f/-o/--config/--cbeta-ebook
        # （engine/vertical/font_lang 由 xml2pdf 配置回退，无需开关）
        import tempfile
        from pathlib import Path as _P
        import cbeta_publish.books.xml2pdf_bridge as b
        win = self.win
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(True)
        win.chk_docx.setChecked(True)
        self.assertEqual(win._checked_fmts(), ["pdf", "epub", "docx"])
        win.chk_docx.setChecked(False)
        self.assertEqual(win._checked_fmts(), ["pdf", "epub"])
        win.chk_epub.setChecked(False)
        self.assertEqual(win._checked_fmts(), ["pdf"])
        win.chk_pdf.setChecked(False)
        win.chk_epub.setChecked(True)
        self.assertEqual(win._checked_fmts(), ["epub"])
        win.chk_pdf.setChecked(True)
        argv = []
        real = b._run_cli
        b._run_cli = lambda a: (argv.extend(a) or 0)
        try:
            b.convert("T0001", None, _P(tempfile.mkdtemp()) / "T0001.pdf",
                      win.config, fmt="pdf", preset=None)
        finally:
            b._run_cli = real
        for f in ("--engine", "--vertical", "--font-lang", "--page", "--t2s"):
            self.assertNotIn(f, argv)
        self.assertEqual(argv[:6], ["-i", "T0001", "-f", "pdf", "-o", argv[5]])
        self.assertIn("--cbeta-ebook", argv)

    def test_preset_dialog_opens(self):
        # 上游 XmlOptionsDialog 可实例化（调整入口不断链）
        # 注意：xml2pdf 可能处于编辑中间态，此跨仓检查失败时跳过（不阻断 publish）
        import sys
        sys.path.insert(0, "E:/dev/cbeta/xml2pdf")
        from cbeta_publish.books import xml2pdf_bridge as b
        presets = b.load_preset_dict("E:/dev/cbeta/xml2pdf/run.json", {})
        self.assertIsInstance(presets, dict)
        try:
            from pycbeta.gui.panel import XmlOptionsDialog
            dlg = XmlOptionsDialog(presets or None, self.win)
        except Exception as e:
            self.skipTest(f"上游 XmlOptionsDialog 暂不可用：{e}")
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

    def test_author_canonical_name(self):
        from cbeta_publish.gui.main_window import author_canonical_name as canon
        self.assertEqual(canon("釋窺基"), "窺基")
        self.assertEqual(canon("沙門釋玄奘"), "玄奘")
        self.assertEqual(canon("比丘尼釋勝鬘"), "勝鬘")
        self.assertEqual(canon("比丘道安"), "道安")
        self.assertEqual(canon("窺基"), "窺基")
        self.assertEqual(canon("王日休"), "王日休")
        self.assertEqual(canon(""), "")

    def test_merge_author_nodes(self):
        from cbeta_publish.gui.main_window import merge_author_nodes as merge
        k1 = {"title": "窺基", "key": "k1",
              "children": [{"key": "T0001"}, {"key": "T0002"}]}
        k2 = {"title": "釋窺基", "key": "k2",
              "children": [{"key": "T0003"}]}
        other = {"title": "王日休", "key": "w",
                 "children": [{"key": "T0004"}]}
        pairs = merge([k1, k2, other])
        by_title = {m["title"]: (h, m) for h, m in pairs}
        self.assertEqual(set(by_title), {"窺基", "王日休"})
        home, merged = by_title["窺基"]
        self.assertIs(home, k1)   # 部数多者在原位
        self.assertEqual([c["key"] for c in merged["children"]],
                         ["T0001", "T0002", "T0003"])
        self.assertEqual(merged["_merged_from"], ["釋窺基"])
        # 单例原样（同一对象），源数据不动，反复调用不重复计数
        self.assertIs(by_title["王日休"][1], other)
        self.assertEqual([c["key"] for c in k1["children"]], ["T0001", "T0002"])
        self.assertEqual([c["key"] for c in k2["children"]], ["T0003"])
        again = merge([k1, k2, other])
        self.assertEqual([c["key"] for c in again[0][1]["children"]],
                         ["T0001", "T0002", "T0003"])

    def _fake_strokes(self):
        def au(title, keys):
            return {"title": title, "key": title,
                    "children": [{"key": k, "title": f"{k} 經"} for k in keys]}
        return [
            {"title": "16畫(stroke)", "children": [
                {"title": "窺", "children": [
                    au("窺基", ["T0001", "T0002"])]},
            ]},
            {"title": "20畫(stroke)", "children": [
                {"title": "釋", "children": [
                    au("釋窺基", ["T0003"])]},
            ]},
        ]

    def _author_texts(self, win):
        out = []

        def walk(it, depth=0):
            out.append("  " * depth + it.text(0))
            for i in range(it.childCount()):
                walk(it.child(i), depth + 1)
        for i in range(win.tree.topLevelItemCount()):
            walk(win.tree.topLevelItem(i))
        return out

    def test_author_merge_pinyin_view(self):
        # 回归：K 下「窺基（26部）」「釋窺基（1部）」合并为一条（27 部）
        win = self.win
        old_strokes, old_cache = win.creator.strokes, win._authors_pinyin_sorted
        win.creator.strokes = self._fake_strokes()
        win._authors_pinyin_sorted = None
        try:
            self._nav("作者")
            win.author_radios["拼音排序"].setChecked(True)
            win._refresh_author_tree()
            texts = self._author_texts(win)
            joined = "\n".join(texts)
            self.assertIn("窺基 (3部)", joined, joined)
            self.assertNotIn("釋窺基", joined, joined)
        finally:
            win.creator.strokes = old_strokes
            win._authors_pinyin_sorted = old_cache
            win.author_radios["拼音排序"].setChecked(True)
            self._nav("作者")

    def test_author_merge_stroke_view(self):
        # 笔画视图：归并成员只在部数多者原位显示，不重复
        win = self.win
        old_strokes, old_cache = win.creator.strokes, win._authors_pinyin_sorted
        win.creator.strokes = self._fake_strokes()
        win._authors_pinyin_sorted = None
        try:
            self._nav("作者")
            win.author_radios["笔画排序"].setChecked(True)
            win._refresh_author_tree()
            texts = self._author_texts(win)
            joined = "\n".join(texts)
            self.assertIn("窺基 (3部)", joined, joined)
            self.assertNotIn("釋窺基", joined, joined)
        finally:
            win.creator.strokes = old_strokes
            win._authors_pinyin_sorted = old_cache
            win.author_radios["拼音排序"].setChecked(True)
            self._nav("作者")

    def test_author_search_finds_merged_works(self):
        # 回归：作者视图搜“窥基”经作者 id 路径返回全部作品（含归并的 D8888），
        # 不再被首命中节点的 X0352 独占
        win = self.win
        self._nav("作者")
        win.author_radios["拼音排序"].setChecked(True)
        win.search.setText("窥基")
        for _ in range(10):
            _ensure_app().processEvents()
        try:
            res = list(win._search_results)
            self.assertGreaterEqual(len(res), 27, res[:5])
            for k in ("T1695", "D8888"):
                self.assertIn(k, res, res[:10])
        finally:
            win.search.clear()
            for _ in range(4):
                _ensure_app().processEvents()

    def test_search_results_sorted_by_work_id(self):
        # 搜索结果各视图统一按经号自然序（部类/刊本/作者一致，不随树序漂移）
        from cbeta_publish.gui.main_window import work_sort_key
        win = self.win
        try:
            for mode in ("部类", "刊本", "作者"):
                self._nav(mode)
                win.search.setText("窥基")
                for _ in range(10):
                    _ensure_app().processEvents()
                res = list(win._search_results)
                self.assertTrue(res, mode)
                self.assertEqual(res, sorted(res, key=work_sort_key), mode)
        finally:
            win.search.clear()
            for _ in range(4):
                _ensure_app().processEvents()

    def test_upstream_dialog_no_app_pollution(self):
        # 回归：上游 CssEditorDialog 不得碰 QApplication 样式表（曾追加全局
        # QToolTip 规则，左栏最小值 346→1272 锁死分栏；上游已修，规则下到
        # 对话框实例）。构造真对话框，应用样式表/最小值/分栏纹丝不动。
        from PySide6.QtWidgets import QApplication
        win = self.win
        app = QApplication.instance()
        old_sheet = app.styleSheet()
        left = win._splitter.widget(0)
        old_hint = left.minimumSizeHint().width()
        old_sizes = list(win._splitter.sizes())
        try:
            import sys
            sys.path.insert(0, "E:/dev/cbeta/xml2pdf")
            from pycbeta.gui.css_editor import CssEditorDialog
        except Exception as e:
            self.skipTest(f"无上游仓库可验证：{e}")
        import shutil
        dlg = None
        try:
            dlg = CssEditorDialog(sample_xml=None, engine_chain=None,
                                  parent=None)
            _ensure_app().processEvents()
            self.assertEqual(app.styleSheet(), old_sheet)
            self.assertEqual(left.minimumSizeHint().width(), old_hint)
            self.assertEqual(list(win._splitter.sizes()), old_sizes)
            self.assertIn("QToolTip", dlg.styleSheet())
        finally:
            try:
                if dlg is not None:
                    tmpd = getattr(dlg, "_tmp", None)
                    dlg.close()
                    dlg.deleteLater()
                    if tmpd:
                        shutil.rmtree(tmpd, ignore_errors=True)
            except Exception:
                pass
            try:
                app.setStyleSheet(old_sheet)
            except Exception:
                pass

    def test_author_lists_works(self):
        # 作者条目下挂著作叶（标题取源数据叶标题；展开/双击/拖拽共用）
        win = self.win
        old_strokes, old_cache = win.creator.strokes, win._authors_pinyin_sorted
        win.creator.strokes = self._fake_strokes()
        win._authors_pinyin_sorted = None
        try:
            self._nav("作者")
            win.author_radios["拼音排序"].setChecked(True)
            win._refresh_author_tree()
            found = []

            def walk(it):
                if it.text(0).startswith("窺基 "):
                    found.append(it)
                for i in range(it.childCount()):
                    walk(it.child(i))
            for i in range(win.tree.topLevelItemCount()):
                walk(win.tree.topLevelItem(i))
            self.assertEqual(len(found), 1, [it.text(0) for it in found])
            kids = [found[0].child(i).text(0)
                    for i in range(found[0].childCount())]
            self.assertEqual(len(kids), 3, kids)
            self.assertTrue(any("T0001" in k for k in kids), kids)
            self.assertTrue(any("T0003" in k for k in kids), kids)
        finally:
            win.creator.strokes = old_strokes
            win._authors_pinyin_sorted = old_cache
            win.author_radios["拼音排序"].setChecked(True)
            self._nav("作者")

    def test_coll_tree_lists_work_titles(self):
        import re
        win = self.win
        self._nav("丛书")
        self.assertGreater(win.tree.topLevelItemCount(), 0)
        cat = win.tree.topLevelItem(0)          # 分类节点
        self.assertGreater(cat.childCount(), 0, "分类下无丛书")
        node = cat.child(0)                     # 丛书节点
        self.assertGreater(node.childCount(), 0, "丛书树未列出经书")
        for i in range(node.childCount()):
            txt = node.child(i).text(0)
            self.assertTrue(txt.strip())
            self.assertRegex(txt, r"^[A-Z]+\d", txt)

    def _open_fixture(self):
        # 右键菜单存在性解析脚手架：自制 pdf＋缓存 epub＋缓存 docx 目录＋
        # 本地库 epub 单文件＋txt 多卷；返回恢复函数
        import tempfile
        from cbeta_publish.books import official_ebook_source as oes
        win = self.win
        tmp = Path(tempfile.mkdtemp())
        saved = {k: win.config.get(k) for k in
                 ("xml_to_ebooks_dir", "official_ebooks_dir",
                  "cbeta_ebooks_dir", "official_library")}
        xb = tmp / "xb"
        (xb / "pdf").mkdir(parents=True)
        (xb / "pdf" / "T0001.pdf").write_bytes(b"P")
        eb = tmp / "eb"
        (eb / "epub").mkdir(parents=True)
        (eb / "epub" / "T0001.epub").write_bytes(b"E")
        (eb / "docx" / "T0001").mkdir(parents=True)
        (eb / "docx" / "T0001" / "a.docx").write_bytes(b"D")
        (eb / "docx" / "T0001" / "b.docx").write_bytes(b"D")
        lib = tmp / "lib"
        (lib / "cbeta_epub_2026r2" / "T").mkdir(parents=True)
        (lib / "cbeta_epub_2026r2" / "T" / "T0001.epub").write_bytes(b"LE")
        (lib / "cbeta-text" / "T" / "T0001").mkdir(parents=True)
        (lib / "cbeta-text" / "T" / "T0001" / "T0001_001.txt").write_bytes(b"T")
        (lib / "cbeta-text" / "T" / "T0001" / "T0001_002.txt").write_bytes(b"T")
        win.config["xml_to_ebooks_dir"] = str(xb)
        win.config["official_ebooks_dir"] = str(eb)
        win.config.pop("cbeta_ebooks_dir", None)
        win.config["official_library"] = {"root": str(lib), "overrides": {}}
        oes.refresh_library_map()

        def _restore():
            for k, v in saved.items():
                if v is None:
                    win.config.pop(k, None)
                else:
                    win.config[k] = v
            oes.refresh_library_map()
            shutil.rmtree(tmp, ignore_errors=True)
        return tmp, xb, eb, lib, _restore

    def test_collect_open_rows_coll_first(self):
        # 丛书树：自制→缓存→本地库；目录命中出文件行＋多卷行
        win = self.win
        tmp, xb, eb, lib, restore = self._open_fixture()
        try:
            rows = win._collect_open_rows("T0001", True)
            got = [(s, l) for s, l, _ in rows]
            self.assertEqual(got, [
                ("made", "PDF（自制）"),
                ("cache", "EPUB（官方缓存）"),
                ("cache", "DOCX（官方缓存）"),
                ("cache", "打开多卷DOCX目录（官方缓存）"),
                ("lib", "EPUB（本地库）"),
                ("lib", "TXT（本地库）"),
                ("lib", "打开多卷TXT目录（本地库）"),
            ])
            by_label = {l: p for _, l, p in rows}
            self.assertEqual(by_label["PDF（自制）"], xb / "pdf" / "T0001.pdf")
            self.assertEqual(by_label["EPUB（官方缓存）"], eb / "epub" / "T0001.epub")
            self.assertEqual(by_label["DOCX（官方缓存）"], eb / "docx" / "T0001" / "a.docx")
            self.assertEqual(by_label["打开多卷DOCX目录（官方缓存）"],
                             eb / "docx" / "T0001")
            self.assertEqual(by_label["TXT（本地库）"],
                             lib / "cbeta-text" / "T" / "T0001" / "T0001_001.txt")
            self.assertEqual(by_label["打开多卷TXT目录（本地库）"],
                             lib / "cbeta-text" / "T" / "T0001")
            self.assertEqual(by_label["EPUB（本地库）"],
                             lib / "cbeta_epub_2026r2" / "T" / "T0001.epub")
        finally:
            restore()

    def test_collect_open_rows_other_first_and_empty(self):
        # 其它树：本地库→缓存→自制；零命中为空
        win = self.win
        tmp, xb, eb, lib, restore = self._open_fixture()
        try:
            rows = win._collect_open_rows("T0001", False)
            srcs = [s for s, _, _ in rows]
            self.assertEqual(srcs, ["lib"] * 3 + ["cache"] * 3 + ["made"])
            self.assertEqual(win._collect_open_rows("TX9Z9", True), [])
            self.assertEqual(win._collect_open_rows("TX9Z9", False), [])
        finally:
            restore()

    def test_collect_open_rows_lists_multi_made_products(self):
        # 同一 work 有多个自制产物时逐个列出，不只列第一项。
        import tempfile
        win = self.win
        saved = {k: win.config.get(k) for k in
                 ("xml_to_ebooks_dir", "official_ebooks_dir",
                  "cbeta_ebooks_dir", "official_library")}
        tmp = Path(tempfile.mkdtemp())
        xb = tmp / "xb"
        (xb / "pdf").mkdir(parents=True)
        first = xb / "pdf" / "TX0011 上.pdf"
        second = xb / "pdf" / "TX0011 中下.pdf"
        first.write_bytes(b"a")
        second.write_bytes(b"b")
        win.config["xml_to_ebooks_dir"] = str(xb)
        win.config["official_ebooks_dir"] = str(tmp / "missing-eb")
        win.config.pop("cbeta_ebooks_dir", None)
        win.config["official_library"] = {"root": str(tmp / "missing-lib"),
                                          "overrides": {}}
        try:
            got = [(label, path) for _, label, path in
                   win._collect_open_rows("TX0011", True)]
        finally:
            for k, v in saved.items():
                if v is None:
                    win.config.pop(k, None)
                else:
                    win.config[k] = v
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(got, [(f"PDF（自制：{first.stem}）", first),
                               (f"PDF（自制：{second.stem}）", second),
                               ("打开多卷PDF目录（自制）", xb / "pdf")])

    def test_tree_context_menu(self):
        # 右键：书叶弹菜单（含分隔线＋标题行）；非书叶不弹；点击打开文件
        from PySide6.QtCore import Qt
        win = self.win
        tmp, xb, eb, lib, restore = self._open_fixture()
        shown = []

        class CapMenu(__import__("PySide6.QtWidgets", fromlist=["QMenu"]).QMenu):
            def exec(self, *a, **k):
                shown.append(self)
                return None

        import PySide6.QtWidgets as qw
        _real_qmenu = qw.QMenu
        try:
            from PySide6.QtWidgets import QTreeWidgetItem
            self._nav("丛书")
            it = QTreeWidgetItem(["T0001"])
            it.setData(0, Qt.UserRole, {"key": "T0001"})
            win.tree.addTopLevelItem(it)
            win.show()
            win.tree.scrollToItem(it)
            for _ in range(4):
                _ensure_app().processEvents()
            rect = win.tree.visualItemRect(it)
            qw.QMenu = CapMenu
            win._on_tree_context_menu(rect.center())
            self.assertEqual(len(shown), 1)
            acts = [a.text() for a in shown[0].actions() if not a.isSeparator()]
            self.assertTrue(acts[0].startswith("T0001"), acts)
            self.assertIn("PDF（自制）", acts)
            self.assertIn("打开多卷TXT目录（本地库）", acts)
            # 文件行在前（按源分组）、目录行沉底
            self.assertLess(acts.index("TXT（本地库）"),
                            acts.index("打开多卷TXT目录（本地库）"))
            self.assertLess(acts.index("DOCX（官方缓存）"),
                            acts.index("打开多卷DOCX目录（官方缓存）"))
            self.assertEqual(acts[-2:], ["打开多卷DOCX目录（官方缓存）",
                                         "打开多卷TXT目录（本地库）"])
            seps = [a for a in shown[0].actions() if a.isSeparator()]
            self.assertEqual(len(seps), 3)
            # 非书叶不弹
            shown.clear()
            grp = QTreeWidgetItem(["分组"])
            win.tree.addTopLevelItem(grp)
            win.tree.scrollToItem(grp)
            for _ in range(4):
                _ensure_app().processEvents()
            win._on_tree_context_menu(
                win.tree.visualItemRect(grp).center())
            win.tree.takeTopLevelItem(win.tree.indexOfTopLevelItem(grp))
            self.assertEqual(shown, [])
            win.tree.takeTopLevelItem(win.tree.indexOfTopLevelItem(it))
        finally:
            qw.QMenu = _real_qmenu
            restore()

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


class MadeBooksInfoTest(unittest.TestCase):
    """下载/自制后「书籍信息」页签列出产物链接 + 总结行；格式图标 tooltip=双击打开。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_show_made_books_links_and_summary(self):
        win = self.win
        d = self.tmp / "made"
        d.mkdir(exist_ok=True)
        p1 = d / "T0001.pdf"
        p1.write_bytes(b"x")
        win.tab_bottom.setCurrentIndex(1)
        win._show_made_books("生成完成", [("T0001", "pdf", p1)],
                             "生成完成 1 部 →", out_dir=d)
        txt = win.detail.text()
        self.assertIn("href=", txt)
        self.assertIn("生成完成 1 部", txt)
        self.assertIn("T0001", txt)
        self.assertIn("made", txt)                             # 目录也可点开
        self.assertEqual(win.tab_bottom.currentIndex(), 0)     # 切到书籍信息页
        self.assertEqual(win.detail_scroll.verticalScrollBar().value(), 0)   # 回到第一行

    def test_detail_link_opens(self):
        from PySide6.QtGui import QDesktopServices
        opened = []
        real = QDesktopServices.openUrl
        QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u.toLocalFile()))
        try:
            self.win._open_publish_link("file:///E:/tmp/x.pdf")
        finally:
            QDesktopServices.openUrl = real
        self.assertTrue(opened and opened[-1].endswith("x.pdf"))

    def test_dir_labels_are_links(self):
        win = self.win
        self.assertEqual(win.lbl_cache_dir.text(), "官方")
        self.assertEqual(win.lbl_xml_dir.text(), "自制")
        self.assertEqual(win.lbl_out_dir.text(), "丛书")
        for lb in (win.lbl_cache_dir, win.lbl_xml_dir, win.lbl_out_dir):
            self.assertTrue(lb.toolTip())          # 保留全路径 tooltip
        self.assertEqual(len(win._dir_refreshers), 3)   # E书目录页可刷新

    def test_format_icon_tooltip_double_click(self):
        win = self.win
        win.config["default_source"] = "xml"
        win.config["xml_to_ebooks_dir"] = str(self.tmp / "xbtip")
        (self.tmp / "xbtip" / "pdf").mkdir(parents=True, exist_ok=True)
        (self.tmp / "xbtip" / "pdf" / "T0099.pdf").write_bytes(b"x")
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(True)
        try:
            win.coll_list.clear()
            win._render_coll_rows(["T0099"])
            _ensure_app().processEvents()
            item = win._coll_book_items()[0]
            row = win._coll_row(item)
            icons = {lb.fmt: lb for lb in row.findChildren(QLabel)
                     if getattr(lb, "fmt", None)}
            self.assertTrue(icons["pdf"].exists_flag)     # 已有 → 双击打开
            self.assertFalse(icons["epub"].exists_flag)   # 缺 → 未下载
            # 行级 tooltip 已移除（与图标提示冲突/闪烁）；图标提示由 eventFilter 悬停显示
            self.assertEqual(item.toolTip(0), "")
        finally:
            win.config["default_source"] = "official"


class LastCollectionTest(unittest.TestCase):
    """上次工作的丛书：兼容旧 ui.last_collection 启动选中；切换写入本地状态文件
    （config/ui_state.json，不进 git），不再写回 config/app.json。"""

    def _win(self, last=None):
        _ensure_app()
        tmp = Path(tempfile.mkdtemp())
        c = tmp / "collections" / "custom"
        c.mkdir(parents=True)
        (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
        for name, wid in (("甲", "T0001"), ("乙", "T0002")):
            (c / f"{name}.json").write_text(json.dumps(
                {"id": name, "name": name, "category": "custom", "tags": [],
                 "work_ids": [wid]}, ensure_ascii=False), encoding="utf-8")
        cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
        cfg["mulu_dir"] = str(ROOT / "mulu")
        cfg["collections_dir"] = str(tmp / "collections")
        cfg["update_interval"] = "manual"
        cfg["_config_path"] = str(tmp / "app.json")
        cfg.setdefault("ui", {})["last_collection"] = str(c / f"{last}.json") if last else ""
        return MainWindow(cfg), tmp, c

    def test_startup_selects_last_collection(self):
        win, tmp, c = self._win(last="乙")
        try:
            self.assertEqual(win.coll_combo.currentText(), "乙")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_switch_persists(self):
        win, tmp, c = self._win(last="乙")
        try:
            for i in range(win.coll_combo.count()):
                if win.coll_combo.itemData(i) == str(c / "甲.json"):
                    win.coll_combo.setCurrentIndex(i)
                    break
            _ensure_app().processEvents()
            state = json.loads((tmp / "ui_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_collection"], str(c / "甲.json"))
            # config/app.json 不再写 last_collection（不进版本库）
            if (tmp / "app.json").exists():
                disk = json.loads((tmp / "app.json").read_text(encoding="utf-8"))
                self.assertNotIn("last_collection", (disk.get("ui") or {}))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
