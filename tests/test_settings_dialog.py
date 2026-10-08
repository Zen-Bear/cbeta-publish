# -*- coding: utf-8 -*-
"""设置对话框：封面/版式子页签顺序、字体路径用系统默认分隔符、确定(仅应用不保存)。

背景：settings_dialog.py 曾因编码往返损坏，这些断言同时防回归。
"""
import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFormLayout  # noqa: E402

from cbeta_publish.gui.settings_dialog import DEFAULT_CONFIG, SettingsDialog, cache_clean_warning  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class SettingsDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _app()

    def _dlg(self):
        return SettingsDialog(copy.deepcopy(DEFAULT_CONFIG), None)

    def test_official_library_roundtrip(self):
        # 本地库分组面板：根目录＋覆盖落盘；重扫弹窗说明结果
        import tempfile
        from PySide6.QtWidgets import QGroupBox, QMessageBox
        dlg = self._dlg()
        lib = Path(tempfile.mkdtemp()) / "lib"
        (lib / "cbeta_epub_2026r2" / "T").mkdir(parents=True)
        (lib / "cbeta_epub_2026r2" / "T" / "T0001.epub").write_bytes(b"E")
        try:
            # 分组面板常显（无折叠），控件归属其下
            boxes = [g for g in dlg.findChildren(QGroupBox)
                     if g.title() == "官方电子书本地库（本地优先）"]
            self.assertEqual(len(boxes), 1)
            box = boxes[0]
            self.assertTrue(box.isAncestorOf(dlg.ed_official_lib))
            self.assertTrue(box.isAncestorOf(dlg.btn_lib_refresh))
            self.assertTrue(box.isAncestorOf(dlg.lib_override_edits["epub"]))
            dlg.ed_official_lib.setText(str(lib))
            dlg.lib_override_edits["epub"].setText("")
            shown = []
            real = QMessageBox.information
            QMessageBox.information = staticmethod(lambda *a, **k: shown.append(a[2]))
            try:
                dlg._refresh_lib_map(show_popup=True)
            finally:
                QMessageBox.information = real
            self.assertTrue(any("epub" in s for s in shown), shown)
            cfg = dlg._collect()
            self.assertEqual(cfg["official_library"]["root"], str(lib))
            self.assertEqual(cfg["official_library"]["overrides"], {})
            dlg2 = SettingsDialog(cfg, None)
            try:
                self.assertEqual(dlg2.ed_official_lib.text(), str(lib))
            finally:
                dlg2.close()
        finally:
            import shutil
            shutil.rmtree(lib.parent, ignore_errors=True)
            dlg.close()

    def test_cover_subtabs_order(self):
        # 封面/版式 6 个子页签：署名/版本 → 封面/说明 → 封面/封底图、背景色 →
        # 字体 → 基准字号 → 边距
        dlg = self._dlg()
        sub = dlg._cover_subtabs
        names = [sub.tabText(i) for i in range(sub.count())]
        self.assertEqual(names, ["署名/版本", "封面/说明", "封面/封底图、背景色",
                                 "字体", "基准字号", "边距"])
        # 署名/版本（页签1）：系列名/版本来源/日期
        self.assertTrue(sub.widget(0).isAncestorOf(dlg.ed_imprint))
        self.assertTrue(sub.widget(0).isAncestorOf(dlg.ed_organizer_official))
        self.assertTrue(sub.widget(0).isAncestorOf(dlg.ed_organizer_xml))
        self.assertTrue(sub.widget(0).isAncestorOf(dlg.ed_date))
        # 封面/说明（页签2）：编辑说明/说明页/部类行；总开关已上移
        self.assertTrue(sub.widget(1).isAncestorOf(dlg.chk_editnote_enabled))
        self.assertTrue(sub.widget(1).isAncestorOf(dlg.chk_intro_enabled))
        self.assertTrue(sub.widget(1).isAncestorOf(dlg.chk_bulei_num))
        self.assertFalse(sub.widget(1).isAncestorOf(dlg.chk_cover_enabled))
        self.assertTrue(sub.widget(2).isAncestorOf(dlg.btn_bg))
        self.assertTrue(sub.widget(3).isAncestorOf(dlg.font_rows["title"]))
        self.assertTrue(sub.widget(4).isAncestorOf(dlg.sp_body["a5"]))
        self.assertTrue(sub.widget(5).isAncestorOf(dlg.sp_margins["a5"]["left"]))

    def test_cover_master_toggle_disables_subtabs(self):
        # 总开关关闭 → 子页签置灰；开启 → 恢复
        dlg = self._dlg()
        try:
            dlg.chk_cover_enabled.setChecked(False)
            self.assertFalse(dlg._cover_subtabs.isEnabled())
            dlg.chk_cover_enabled.setChecked(True)
            self.assertTrue(dlg._cover_subtabs.isEnabled())
        finally:
            dlg.close()

    def test_subtabs_styled(self):
        # 设置顶层页签与嵌套子页签统一强调样式（加粗 + 选中下划线）
        from cbeta_publish.gui.settings_dialog import SUBTAB_QSS
        dlg = self._dlg()
        try:
            for sub in (dlg._tabs, dlg._dirs_tabs, dlg._cover_subtabs):
                self.assertEqual(sub.styleSheet(), SUBTAB_QSS)
                self.assertIn("font-weight:bold", sub.styleSheet())
                self.assertIn("QTabBar::tab:selected", sub.styleSheet())
        finally:
            dlg.close()

    def test_note_display_path_relative(self):
        # 数据根内的绝对路径 → 相对路径；根外绝对路径原样；相对路径归一化
        import cbeta_publish.gui.settings_dialog as sd
        abs_inside = sd.PROJECT_ROOT / "assets" / "notes" / "sample.txt"
        self.assertEqual(sd.note_display_path(str(abs_inside)),
                         str(Path("assets") / "notes" / "sample.txt"))
        self.assertEqual(sd.note_display_path("assets/notes/a.txt"),
                         str(Path("assets") / "notes" / "a.txt"))
        self.assertEqual(sd.note_display_path("Z:/x/y.txt"), "Z:/x/y.txt")
        self.assertEqual(sd.note_display_path(""), "")

    def test_note_checkbox_texts_renamed(self):
        dlg = self._dlg()
        try:
            self.assertEqual(dlg.chk_editnote_enabled.text(), "加编辑说明页")
            self.assertEqual(dlg.chk_editnote_coll_enabled.text(), "加丛书说明页")
        finally:
            dlg.close()

    def test_collection_edit_note_roundtrip(self):
        # 丛书特定说明页：全局项 tooltip；随丛书上下文；collection_edit_note 往返
        coll = {"id": "c", "name": "C", "category": "custom", "tags": [],
                "work_ids": ["T0001"],
                "edit_note": {"file": "E:/n.txt", "enabled": True}}
        dlg = SettingsDialog(copy.deepcopy(DEFAULT_CONFIG), None,
                             collection=coll, collection_path="x.json")
        try:
            self.assertEqual(dlg.chk_editnote_enabled.toolTip(), "所有丛书的说明页")
            self.assertEqual(dlg.chk_editnote_coll_enabled.toolTip(), "当前丛书的说明页（随丛书切换）")
            self.assertTrue(dlg.chk_editnote_coll_enabled.isChecked())
            self.assertEqual(dlg.ed_editnote_coll.text(), "E:/n.txt")
            dlg.ed_editnote_coll.setText("E:/m.txt")
            dlg.chk_editnote_coll_enabled.setChecked(False)
            self.assertEqual(dlg.collection_edit_note(),
                             {"file": "E:/m.txt", "enabled": False})
        finally:
            dlg.close()
        # 无丛书上下文：控件禁用、返回 None
        dlg2 = self._dlg()
        try:
            self.assertIsNone(dlg2.collection_edit_note())
            self.assertFalse(dlg2.chk_editnote_coll_enabled.isEnabled())
        finally:
            dlg2.close()

    def test_note_rel_inside_and_outside(self):
        # 限定 assets/notes/ 内：目录内→相对路径；目录外→None
        import cbeta_publish.gui.settings_dialog as sd
        tmp = Path(tempfile.mkdtemp())
        real = sd.NOTES_DIR
        sd.NOTES_DIR = tmp / "notes"
        try:
            (sd.NOTES_DIR).mkdir(parents=True)
            inside = sd.NOTES_DIR / "n.txt"
            inside.write_text("x", encoding="utf-8")
            self.assertEqual(SettingsDialog._note_rel(str(inside)),
                             str(Path("assets") / "notes" / "n.txt"))
            outside = tmp / "out.txt"
            outside.write_text("x", encoding="utf-8")
            self.assertIsNone(SettingsDialog._note_rel(str(outside)))
            # 前缀相近但不是子目录 → 拒绝
            near = tmp / "notes2"
            near.mkdir()
            (near / "m.txt").write_text("x", encoding="utf-8")
            self.assertIsNone(SettingsDialog._note_rel(str(near / "m.txt")))
        finally:
            sd.NOTES_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)

    def test_choose_note_inside_and_outside(self):
        from unittest import mock
        import cbeta_publish.gui.settings_dialog as sd
        tmp = Path(tempfile.mkdtemp())
        real = sd.NOTES_DIR
        sd.NOTES_DIR = tmp / "notes"
        sd.NOTES_DIR.mkdir(parents=True)
        dlg = self._dlg()
        try:
            inside = sd.NOTES_DIR / "n.txt"
            inside.write_text("<title>T\n正文\n", encoding="utf-8")
            with mock.patch.object(sd.QFileDialog, "getOpenFileName",
                                   return_value=(str(inside), "")):
                dlg._choose_note(dlg.ed_editnote)
            self.assertEqual(dlg.ed_editnote.text(),
                             str(Path("assets") / "notes" / "n.txt"))
            # 目录外：复制进 notes 后采用
            outside = tmp / "外说明.txt"
            outside.write_text("<title>T\n正文\n", encoding="utf-8")
            with mock.patch.object(sd.QFileDialog, "getOpenFileName",
                                   return_value=(str(outside), "")):
                dlg._choose_note(dlg.ed_editnote)
            self.assertEqual(dlg.ed_editnote.text(),
                             str(Path("assets") / "notes" / "外说明.txt"))
            self.assertTrue((sd.NOTES_DIR / "外说明.txt").is_file())
        finally:
            dlg.close()
            sd.NOTES_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)

    def test_font_input_uses_native_separator(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["styles"]["title"] = {"font": "C:/Windows/Fonts/simhei.ttf"}
        dlg = SettingsDialog(cfg, None)
        shown = dlg.font_rows["title"].text()
        self.assertNotIn("/", shown.replace(os.sep, ""))   # 用系统默认分隔符
        self.assertEqual(Path(shown), Path("C:/Windows/Fonts/simhei.ttf"))
        self.assertEqual(SettingsDialog._native_path(""), "")
        self.assertEqual(Path(SettingsDialog._native_path("a/b/c")), Path("a/b/c"))

    def test_update_table_uses_readonly_textboxes(self):
        # 更新源表：URL / 本地文件两列改为只读文本框（可查看/拷贝完整内容）
        from PySide6.QtWidgets import QLineEdit
        from cbeta_publish.books.remote_sources import SOURCES, local_path
        dlg = self._dlg()
        tbl = dlg.tbl
        self.assertGreaterEqual(tbl.rowCount(), 1)
        for r, (key, cat, url, rel) in enumerate(SOURCES):
            for c, want in ((2, url), (3, str(local_path(rel)))):
                w = tbl.cellWidget(r, c)
                self.assertIsInstance(w, QLineEdit, (r, c))
                self.assertTrue(w.isReadOnly(), (r, c))
                self.assertEqual(w.text(), want, (r, c))
                self.assertIn(want, w.toolTip())

    def test_dirs_tab_scrolls_not_grows_dialog(self):
        # 数据/输出页包 QScrollArea：内容再长对话框也不撑高
        from PySide6.QtWidgets import QScrollArea, QTabWidget
        dlg = self._dlg()
        tabs = dlg.findChild(QTabWidget)
        self.assertIsNotNone(tabs)
        idx = next(i for i in range(tabs.count()) if tabs.tabText(i) == "数据/输出")
        page = tabs.widget(idx)
        self.assertIsInstance(page, QScrollArea)
        self.assertTrue(page.widgetResizable())
        # 控件仍可达（滚动不影响存取）
        self.assertTrue(page.widget().isAncestorOf(dlg.ed_official_lib))

    def test_restore_buttons_say_dir_data(self):
        # 两个恢复按钮去掉突兀的“(mulu)”，改称“目录数据”
        from PySide6.QtWidgets import QPushButton
        dlg = self._dlg()
        texts = [b.text() for b in dlg.findChildren(QPushButton)]
        self.assertIn("恢复原始（目录数据）", texts)
        self.assertIn("恢复上一次（目录数据）", texts)
        self.assertFalse([t for t in texts if "mulu" in t], texts)

    def test_cover_organizer_fields(self):
        # 书籍版本/来源分官方/自制两栏 + tooltip；日期/署名 tooltip
        dlg = self._dlg()
        try:
            self.assertTrue(dlg.ed_organizer_official.text())
            self.assertTrue(dlg.ed_organizer_xml.text())
            self.assertIn("官方", dlg.ed_organizer_official.toolTip())
            self.assertIn("自制", dlg.ed_organizer_xml.toolTip())
            self.assertIn("{date}", dlg.ed_date.toolTip())
            dlg.ed_organizer_official.setText("官A")
            dlg.ed_organizer_xml.setText("自B")
            out = dlg._collect()["cover"]
            self.assertEqual((out["organizer_official"], out["organizer_xml"]),
                             ("官A", "自B"))
        finally:
            dlg.close()
        # 旧配置只有 organizer → 两栏都回退该值
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"].pop("organizer_official", None)
        cfg["cover"].pop("organizer_xml", None)
        cfg["cover"]["organizer"] = "旧署名"
        d2 = SettingsDialog(cfg, None)
        self.assertEqual(d2.ed_organizer_official.text(), "旧署名")
        self.assertEqual(d2.ed_organizer_xml.text(), "旧署名")

    def test_apply_does_not_write(self):
        dlg = self._dlg()
        # 记录磁盘内容，确认「确定」不写盘
        from cbeta_publish.gui import settings_dialog as sd
        before = sd.CONFIG_PATH.read_bytes() if sd.CONFIG_PATH.exists() else None
        dlg.ed_organizer_official.setText("测试整理")
        dlg._apply()
        after = sd.CONFIG_PATH.read_bytes() if sd.CONFIG_PATH.exists() else None
        self.assertEqual(before, after)
        self.assertFalse(dlg._did_save)
        self.assertIsInstance(dlg.result_config(), dict)
        self.assertEqual(dlg.result_config()["cover"]["organizer_official"], "测试整理")

    def test_apply_button_labelled_ok(self):
        dlg = self._dlg()
        self.assertEqual(dlg._btn_apply.text(), "确定")

    def test_buttons_layout_and_default(self):
        # 恢复默认/恢复原始靠左；确定/保存/取消靠右；确定为默认按钮
        dlg = self._dlg()
        row = dlg._btn_row
        texts = [row.itemAt(i).widget().text()
                 for i in range(row.count()) if row.itemAt(i).widget()]
        self.assertEqual(texts, ["恢复默认", "恢复原始", "确定", "保存", "取消"])
        self.assertTrue(dlg._btn_apply.isDefault())
        self.assertFalse(dlg._btn_save.isDefault())

    def test_series_migrates_to_imprint(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["series"] = "太虛大師全書"
        dlg = SettingsDialog(cfg, None)
        self.assertEqual(dlg.ed_imprint.text(), "太虛大師全書")
        self.assertNotIn("series", dlg._cfg["cover"])

    def test_dead_cover_keys_dropped(self):        # 死键清理：intro.list / positions.cbeta_left_mm/top_mm 无人读取，
        # 出厂默认不带；旧配置经 _collect 保存时一并去掉
        self.assertNotIn("list", DEFAULT_CONFIG["cover"]["intro"])
        self.assertNotIn("cbeta_left_mm", DEFAULT_CONFIG["cover"]["positions"])
        self.assertNotIn("cbeta_top_mm", DEFAULT_CONFIG["cover"]["positions"])
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["intro"]["list"] = True
        cfg["cover"]["positions"]["cbeta_left_mm"] = 18
        cfg["cover"]["positions"]["cbeta_top_mm"] = 12
        dlg = SettingsDialog(cfg, None)
        out = dlg._collect()
        self.assertNotIn("list", out["cover"]["intro"])
        self.assertNotIn("cbeta_left_mm", out["cover"]["positions"])
        self.assertNotIn("cbeta_top_mm", out["cover"]["positions"])

    def test_mode_is_radio_buttons(self):
        # PDF 合并模式：单选按钮（打印模式/阅读模式），round-trip 到 cover.mode
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["mode"] = "reading"
        dlg = SettingsDialog(cfg, None)
        self.assertEqual([dlg.rb_print.text(), dlg.rb_reading.text()],
                         ["打印模式", "阅读模式"])
        self.assertTrue(dlg.rb_reading.isChecked())
        self.assertFalse(dlg.rb_print.isChecked())
        dlg.rb_print.setChecked(True)
        self.assertEqual(dlg._collect()["cover"]["mode"], "print")
        dlg.rb_reading.setChecked(True)
        self.assertEqual(dlg._collect()["cover"]["mode"], "reading")

    def test_restore_buttons_have_tooltips(self):
        dlg = self._dlg()
        self.assertTrue(dlg._btn_default.toolTip())
        self.assertTrue(dlg._btn_original.toolTip())

    def test_merge_mode_radios_and_roundtrip(self):
        # 分册模式七选一（两行）+ 深度 + 文件名模板 + 阈值；持久化 merge 全套
        dlg = self._dlg()
        self.assertEqual([dlg.rb_merge_none.text(), dlg.rb_merge_volume.text(),
                          dlg.rb_merge_catalog.text(), dlg.rb_merge_manual.text(),
                          dlg.rb_merge_author.text(), dlg.rb_merge_dynasty.text(),
                          dlg.rb_merge_ask.text()],
                         ["不分册", "按刊本册", "按目录（部类）", "按手工分册（右栏）",
                          "按作者", "按朝代", "合并时选择（每次弹框）"])
        # 七个单选分两行
        _kinds = []
        for _row in dlg._rb_merge_rows:
            _h = _row[0].parent().layout()
            _kinds += [type(_h.itemAt(i).widget()).__name__
                       for i in range(_h.count())]
        self.assertEqual(_kinds.count("QRadioButton"), 7)
        dlg.rb_merge_catalog.setChecked(True)
        dlg.sp_merge_depth.setValue(3)
        dlg.ed_merge_name.setText("{coll}.{nn}.{seg}")
        dlg.sp_split_pdf.setValue(0)
        dlg.sp_split_epub.setValue(0)
        out = dlg._collect()["merge"]
        self.assertEqual(out["mode"], "catalog")
        self.assertEqual(out["depth"], 3)
        self.assertEqual(out["name_template"], "{coll}.{nn}.{seg}")
        self.assertFalse(out["by_volume"])
        # 作者/朝代往返
        dlg.rb_merge_author.setChecked(True)
        self.assertEqual(dlg._collect()["merge"]["mode"], "author")
        dlg.rb_merge_dynasty.setChecked(True)
        self.assertEqual(dlg._collect()["merge"]["mode"], "dynasty")
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["merge"] = {"mode": "author", "depth": 1, "by_volume": False,
                        "name_template": "{coll}.{nn}.{seg}"}
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.rb_merge_author.isChecked())
        cfg["merge"]["mode"] = "dynasty"
        self.assertTrue(SettingsDialog(cfg, None).rb_merge_dynasty.isChecked())
        self.assertEqual(dlg._collect()["pdf"]["split_pages"], 0)
        self.assertEqual(dlg._collect()["epub"]["split_items"], 0)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["merge"] = {"mode": "volume", "depth": 1, "by_volume": True,
                        "name_template": "{coll}.{nn}.{seg}"}
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.rb_merge_volume.isChecked())
        self.assertEqual(d2.sp_merge_depth.value(), 1)
        self.assertEqual(d2.ed_merge_name.text(), "{coll}.{nn}.{seg}")
        self.assertTrue(d2._collect()["merge"]["by_volume"])

    def test_split_box_hidden_and_zero_default(self):
        # 分册阈值组在分册模式组之下、默认隐藏；默认 0=不分册
        dlg = self._dlg()
        self.assertTrue(dlg.split_box.isHidden())
        self.assertEqual(dlg.sp_split_pdf.value(), 0)
        self.assertEqual(dlg.sp_split_epub.value(), 0)
        self.assertEqual(DEFAULT_CONFIG["pdf"]["split_pages"], 0)
        self.assertEqual(DEFAULT_CONFIG["epub"]["split_items"], 0)
        self.assertEqual(DEFAULT_CONFIG["merge"]["name_template"],
                         "{coll}.{nn}.{seg}")

    def test_cover_labels_renamed(self):
        # 顶部两行：PDF 合并模式（独立行，在上）＋ 总开关；不再有「发布模式」
        from PySide6.QtWidgets import QFormLayout
        dlg = self._dlg()
        labels = []
        for i in range(dlg._cover_form.rowCount()):
            it = dlg._cover_form.itemAt(i, QFormLayout.LabelRole)
            if it is not None and it.widget() is not None and hasattr(it.widget(), "text"):
                labels.append(it.widget().text())
        self.assertIn("PDF 合并模式", labels)
        self.assertNotIn("发布模式", labels)

        def _row_of(widget):
            for i in range(dlg._cover_form.rowCount()):
                for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                    it = dlg._cover_form.itemAt(i, role)
                    if it is not None and it.widget() is widget:
                        return i
            return -1
        self.assertGreaterEqual(_row_of(dlg.cb_mode), 0)
        self.assertGreaterEqual(_row_of(dlg.chk_cover_enabled), 0)
        self.assertLess(_row_of(dlg.cb_mode), _row_of(dlg.chk_cover_enabled))

    def test_default_source_is_radio(self):
        # 默认来源=单选（官方/自制），存值 official/xml
        dlg = self._dlg()
        self.assertEqual([dlg.rb_src_official.text(), dlg.rb_src_made.text()],
                         ["官方", "自制"])
        self.assertTrue(dlg.rb_src_official.isChecked())
        dlg.rb_src_made.setChecked(True)
        self.assertEqual(dlg._collect()["default_source"], "xml")
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["default_source"] = "xml"
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.rb_src_made.isChecked())

    def test_default_formats_roundtrip(self):
        # 默认勾选格式：合并（pdf/epub）与 官方/自制 两组（各自用于 ZIP/导出）
        dlg = self._dlg()
        dlg.fmt_merge_boxes["epub"].setChecked(False)
        dlg.fmt_made_boxes["docx"].setChecked(False)
        dlg.fmt_off_boxes["html"].setChecked(False)
        df = dlg._collect()["default_formats"]
        self.assertEqual(df["merge"], ["pdf"])
        self.assertNotIn("docx", df["xml"])
        self.assertNotIn("html", df["official"])
        self.assertEqual(set(df["xml"]) | set(), {"pdf"})
        # 默认值：官方去掉 odt/txt_notes；自制不含 epub
        self.assertEqual(DEFAULT_CONFIG["default_formats"]["official"],
                         ["pdf", "epub", "html", "docx", "txt"])
        self.assertEqual(DEFAULT_CONFIG["default_formats"]["xml"], ["pdf", "docx"])
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["default_formats"]["merge"] = ["epub"]
        d2 = SettingsDialog(cfg, None)
        self.assertFalse(d2.fmt_merge_boxes["pdf"].isChecked())
        self.assertTrue(d2.fmt_merge_boxes["epub"].isChecked())
        self.assertFalse(d2.fmt_off_boxes["odt"].isChecked())
        self.assertFalse(d2.fmt_made_boxes["epub"].isChecked())
        self.assertEqual(d2.fmt_off_boxes["txt_notes"].text(), "txt含注释")

    def test_build_verify_radio_and_roundtrip(self):
        # 制作书籍：校验/无校验 单选，持久化到 xml2pdf.verify_build
        dlg = self._dlg()
        self.assertTrue(dlg.rb_build_noverify.isChecked())
        dlg.rb_build_verify.setChecked(True)
        self.assertTrue(dlg._collect()["xml2pdf"]["verify_build"])
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["xml2pdf"]["verify_build"] = True
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.rb_build_verify.isChecked())

    def test_reuse_pdf_companion_default_and_roundtrip(self):
        # PDF 伴生复用：默认开；落盘回读
        dlg = self._dlg()
        self.assertTrue(dlg.chk_reuse_pdf_docx.isChecked())
        dlg.chk_reuse_pdf_docx.setChecked(False)
        self.assertFalse(dlg._collect()["xml2pdf"]["reuse_pdf_companion"])
        dlg.chk_reuse_pdf_docx.setChecked(True)
        self.assertTrue(dlg._collect()["xml2pdf"]["reuse_pdf_companion"])
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["xml2pdf"]["reuse_pdf_companion"] = False
        d2 = SettingsDialog(cfg, None)
        self.assertFalse(d2.chk_reuse_pdf_docx.isChecked())

    def test_verify_thresholds_default_and_roundtrip(self):
        # 校验阈值/报告行数：范围 0–50；max_diff 默认 0（严格）、diff_lines 默认 5；回写
        dlg = self._dlg()
        for sp in (dlg.sp_verify_maxdiff, dlg.sp_verify_difflines):
            self.assertEqual(sp.minimum(), 0)
            self.assertEqual(sp.maximum(), 50)
        self.assertEqual(dlg.sp_verify_maxdiff.value(), 0)
        self.assertEqual(dlg.sp_verify_difflines.value(), 5)
        dlg.sp_verify_maxdiff.setValue(3)
        dlg.sp_verify_difflines.setValue(7)
        out = dlg._collect()["xml2pdf"]
        self.assertEqual(out["verify_max_diff"], 3)
        self.assertEqual(out["verify_diff_lines"], 7)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["xml2pdf"]["verify_max_diff"] = 2
        cfg["xml2pdf"]["verify_diff_lines"] = 9
        d2 = SettingsDialog(cfg, None)
        self.assertEqual(d2.sp_verify_maxdiff.value(), 2)
        self.assertEqual(d2.sp_verify_difflines.value(), 9)

    def test_cover_date_row_order_and_roundtrip(self):
        # 行序：左上角系列名 → 整理者署名 → 日期；date_text 落盘回读
        from PySide6.QtWidgets import QFormLayout
        dlg = self._dlg()
        labels = []
        for i in range(dlg._cover_sig_form.rowCount()):
            it = dlg._cover_sig_form.itemAt(i, QFormLayout.LabelRole)
            if it is not None and it.widget() is not None:
                labels.append(it.widget().text())
        self.assertLess(labels.index("左上角系列名"),
                        labels.index("书籍版本/来源（官方）"))
        self.assertLess(labels.index("书籍版本/来源（官方）"),
                        labels.index("书籍版本/来源（自制）"))
        self.assertLess(labels.index("书籍版本/来源（自制）"),
                        labels.index("日期/署名"))
        self.assertEqual(dlg.ed_date.text(), "{date}")  # 缺省自动今天
        dlg.ed_date.setText("丙午年秋")
        out = dlg._collect()
        self.assertEqual(out["cover"]["date_text"], "丙午年秋")

    def test_cover_editnote_rows_and_roundtrip(self):
        # 编辑说明文件行＋插入复选框（默认关）；落盘回读
        dlg = self._dlg()
        self.assertEqual(dlg.ed_editnote.text(), "")
        self.assertFalse(dlg.chk_editnote_enabled.isChecked())
        dlg.ed_editnote.setText("D:/notes/x.txt")
        dlg.chk_editnote_enabled.setChecked(True)
        out = dlg._collect()
        self.assertEqual(out["cover"]["edit_note"],
                         {"file": "D:/notes/x.txt", "enabled": True})
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["edit_note"] = {"file": "D:/notes/x.txt", "enabled": True}
        d2 = SettingsDialog(cfg, None)
        self.assertEqual(d2.ed_editnote.text(), "D:/notes/x.txt")
        self.assertTrue(d2.chk_editnote_enabled.isChecked())
        self.assertIn("editnote_title", d2.font_rows)
        self.assertIn("editnote_body", d2.font_rows)
        # 行结构：复选框＋选择/导入按钮＋输入框同行；说明页标题并入复选框行右侧
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton
        row = dlg.chk_editnote_enabled.parent()
        kinds = [type(w).__name__ for w in
                 [row.layout().itemAt(i).widget() for i in range(row.layout().count())]]
        self.assertEqual(kinds, ["QCheckBox", "QPushButton", "QLineEdit"])
        self.assertEqual(row.layout().itemAt(1).widget().text(), "选择…")
        irow = dlg.chk_intro_enabled.parent()
        itexts = [w.text() for w in
                  [irow.layout().itemAt(i).widget() for i in range(irow.layout().count())]
                  if isinstance(w, QLabel)]
        self.assertIn("说明页标题", itexts)

    def test_cover_checkbox_text(self):
        # 合并开关改名：封面封底＋说明（以下所有内容）
        dlg = self._dlg()
        self.assertEqual(dlg.chk_cover_enabled.text(),
                         "合并时加封面封底、说明（以下所有内容）")

    def test_cover_bulei_roundtrip(self):
        # 封面部类行：总开关/书名模式/深度/版式/分隔符/序号，落盘回读
        dlg = self._dlg()
        self.assertTrue(dlg.chk_bulei_show.isChecked())
        self.assertEqual(dlg.cb_bulei_titles.currentData(), "none")
        self.assertEqual(dlg.sp_bulei_depth.value(), 0)
        self.assertEqual(dlg.cb_bulei_layout.currentData(), "lines")
        self.assertEqual(dlg.ed_bulei_sep.text(), "·")
        self.assertFalse(dlg.chk_bulei_num.isChecked())
        dlg.sp_bulei_depth.setValue(2)
        dlg.cb_bulei_layout.setCurrentIndex(
            dlg.cb_bulei_layout.findData("one"))
        dlg.ed_bulei_sep.setText("|")
        dlg.chk_bulei_num.setChecked(True)
        dlg.chk_bulei_show.setChecked(False)
        dlg.cb_bulei_titles.setCurrentIndex(
            dlg.cb_bulei_titles.findData("all"))
        out = dlg._collect()["cover"]["bulei"]
        self.assertEqual(out, {"enabled": False, "depth": 2, "layout": "one",
                               "sep": "|", "show_num": True, "titles": "all"})
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["bulei"] = {"enabled": False, "depth": 3, "layout": "one",
                                 "sep": "-", "show_num": True, "titles": "all"}
        d2 = SettingsDialog(cfg, None)
        self.assertFalse(d2.chk_bulei_show.isChecked())
        self.assertEqual(d2.cb_bulei_titles.currentData(), "all")
        self.assertEqual(d2.sp_bulei_depth.value(), 3)
        self.assertEqual(d2.cb_bulei_layout.currentData(), "one")
        self.assertEqual(d2.ed_bulei_sep.text(), "-")
        self.assertTrue(d2.chk_bulei_num.isChecked())

    def test_font_rows_editable_and_checked(self):
        # 字体名可手输；输完检测路径存在性（缺失红框，不拦保存）
        dlg = self._dlg()
        ed = dlg.font_rows["toc_item"]
        self.assertFalse(ed.isReadOnly())
        # 缺省：编辑说明标题=雅黑粗、说明正文=宋体
        self.assertEqual(dlg.font_rows["editnote_title"].text(),
                         str(Path("C:/Windows/Fonts/msyhbd.ttc")))
        self.assertEqual(dlg.font_rows["editnote_body"].text(),
                         str(Path("C:/Windows/Fonts/simsun.ttc")))
        # 存在的路径不清红框
        ed.setText(str(Path("C:/Windows/Fonts/simhei.ttf")))
        dlg._check_font_row("toc_item", ed)
        self.assertEqual(ed.styleSheet(), "")
        # 不存在的标红，落盘仍保存原文
        ed.setText("Z:/no/such/font.ttf")
        dlg._check_font_row("toc_item", ed)
        self.assertIn("red", ed.styleSheet())
        out = dlg._collect()
        self.assertEqual(out["cover"]["styles"]["toc_item"]["font"],
                         "Z:/no/such/font.ttf")
        # 恢复存在路径后红框清除
        ed.setText(str(Path("C:/Windows/Fonts/simhei.ttf")))
        dlg._check_font_row("toc_item", ed)
        self.assertEqual(ed.styleSheet(), "")

    def test_intro_note_and_summary_font(self):
        # 「说明页注明」可改；说明页简介字体在「字体」子页签
        dlg = self._dlg()
        self.assertIn("intro_summary", dlg.font_rows)
        dlg.ed_intro_note.setText("測試註記")
        dlg.font_rows["intro_summary"].setText("C:/Windows/Fonts/simfang.ttf")
        out = dlg._collect()
        self.assertEqual(out["cover"]["intro"]["note"], "測試註記")
        self.assertEqual(out["cover"]["styles"]["intro_summary"]["font"],
                         "C:/Windows/Fonts/simfang.ttf")

    def test_preset_rows_and_collect(self):
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        try:
            root = tmp / "x2p"
            (root / "presets").mkdir(parents=True)
            (root / "presets" / "a.json").write_text("{}", encoding="utf-8")
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg["xml2pdf"]["path"] = str(root)
            cfg["xml2pdf"]["preset"] = "a"
            cfg["default_source"] = "xml"
            cfg["xml_to_ebooks_dir"] = str(tmp / "xb")
            dlg = SettingsDialog(cfg, None)
            self.assertEqual(dlg.cb_preset.currentData(), "a")
            self.assertTrue(dlg.rb_src_made.isChecked())
            self.assertEqual(dlg.ed_xmlbooks.text(), str(tmp / "xb"))
            out = dlg._collect()
            self.assertEqual(out["xml2pdf"]["preset"], "a")
            self.assertEqual(out["xml2pdf"]["path"], str(root))
            self.assertEqual(out["default_source"], "xml")
            self.assertEqual(out["xml_to_ebooks_dir"], str(tmp / "xb"))
            for k in ("page", "font_lang", "engine", "vertical", "preset_dir"):
                self.assertNotIn(k, out["xml2pdf"])
            self.assertFalse(hasattr(dlg, "cb_x2p_page"))
            self.assertFalse(hasattr(dlg, "ed_preset_dir"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_collect_roundtrip_after_restructure(self):
        # 子页签拆分后，控件仍在 _collect 覆盖范围内
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["sizes"]["body_a5"] = 13
        cfg["cover"]["sizes"]["margins"]["a5"] = {"left": 21, "right": 22, "top": 23, "bottom": 24}
        cfg["cover"]["styles"]["background"] = {"color": [1, 2, 3]}
        cfg["cover"]["images"]["buddha"]["enabled"] = False
        dlg = SettingsDialog(cfg, None)
        dlg.ed_organizer_official.setText("某某整理")
        out = dlg._collect()
        cv = out["cover"]
        self.assertEqual(cv["organizer_official"], "某某整理")
        self.assertEqual(cv["organizer"], "某某整理")   # 旧键=官方值（兼容）
        self.assertEqual(cv["sizes"]["body_a5"], 13)
        self.assertEqual(cv["sizes"]["margins"]["a5"],
                         {"left": 21, "right": 22, "top": 23, "bottom": 24})
        self.assertEqual(cv["styles"]["background"]["color"], [1, 2, 3])
        self.assertFalse(cv["images"]["buddha"]["enabled"])
        self.assertIn("font", cv["styles"]["title"])

    def test_editnote_body_size_roundtrip(self):
        # 编辑说明正文字号：缺省 12；改值落盘回读
        dlg = self._dlg()
        self.assertEqual(dlg.sp_editnote_body.value(), 12)
        dlg.sp_editnote_body.setValue(18)
        out = dlg._collect()
        self.assertEqual(out["cover"]["sizes"]["editnote_body"], 18)
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["sizes"]["editnote_body"] = 15
        d2 = SettingsDialog(cfg, None)
        self.assertEqual(d2.sp_editnote_body.value(), 15)
        self.assertEqual(d2._collect()["cover"]["sizes"]["editnote_body"], 15)

    def test_intro_toc_bg_default_follow_cover(self):
        # 缺席＝跟随封面：默认显示封面色、落盘不写键；单独选色后独立落盘
        from PySide6.QtGui import QColor
        from cbeta_publish.books import ebook_merger as _em
        dlg = self._dlg()
        self.assertEqual(dlg._bg_colors["intro_background"].getRgb()[:3],
                         dlg._bg_color.getRgb()[:3])
        self.assertEqual(dlg._bg_colors["toc_background"].getRgb()[:3],
                         dlg._bg_color.getRgb()[:3])
        self.assertTrue(dlg._cover_subtabs.widget(2).isAncestorOf(
            dlg._bg_btns["intro_background"]))
        self.assertTrue(dlg._cover_subtabs.widget(2).isAncestorOf(
            dlg._bg_btns["toc_background"]))
        out0 = dlg._collect()["cover"]["styles"]
        self.assertNotIn("intro_background", out0)
        self.assertNotIn("toc_background", out0)
        # 跟随端到端：只有封面色时，渲染取封面色
        self.assertEqual(_em._page_bg({"styles": out0}, "intro_background"),
                         list(out0["background"]["color"]))
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["styles"]["background"] = {"color": [1, 2, 3]}
        d2 = SettingsDialog(cfg, None)
        self.assertEqual(d2._bg_colors["intro_background"].getRgb()[:3], (1, 2, 3))
        d2._bg_colors["toc_background"] = QColor(4, 5, 6)
        d2._bg_custom.add("toc_background")
        out = d2._collect()["cover"]["styles"]
        self.assertNotIn("intro_background", out)
        self.assertEqual(out["toc_background"]["color"], [4, 5, 6])

    def test_default_cover_images_b01_b02(self):
        # 封面/封底图默认输入栏：B01.jpg / B02.jpg（存在时优先于编号）
        dlg = self._dlg()
        bfile = Path(dlg.img_rows["buddha"][1].text())
        wfile = Path(dlg.img_rows["weituo"][1].text())
        self.assertEqual(bfile.name, "B01.jpg")
        self.assertEqual(wfile.name, "B02.jpg")
        self.assertTrue(bfile.is_file())
        self.assertTrue(wfile.is_file())

    def test_dirs_tab_groups_and_browse(self):
        # 数据/输出：「E书默认来源和格式」框（来源单选+默认格式）；浏览按钮齐全
        from PySide6.QtWidgets import QGroupBox, QPushButton, QTabWidget
        dlg = self._dlg()
        groups = [g for g in dlg.findChildren(QGroupBox) if g.title() == "E书默认来源和格式"]
        self.assertEqual(len(groups), 1)
        box = groups[0]
        for w in (dlg.src_default_box, dlg.fmt_merge_boxes["pdf"],
                  dlg.fmt_off_boxes["pdf"], dlg.fmt_made_boxes["docx"]):
            self.assertTrue(box.isAncestorOf(w), w)
        # 自制路径已移到「自制E书」页签（不在来源/格式框内）
        for w in (dlg.ed_x2p, dlg.ed_x2p_ebook, dlg.ed_xmlbooks, dlg.ed_verify,
                  dlg.cb_preset):
            self.assertFalse(box.isAncestorOf(w), w)
        tabs = dlg.findChildren(QTabWidget)[0]
        names = [tabs.tabText(i) for i in range(tabs.count())]
        self.assertIn("自制E书", names)
        self.assertIn("更新源", names)
        # 主 tab 顺序：数据/输出，封面/版式，自制E书，缓存，目录过滤，更新源，外观
        self.assertEqual(names, ["数据/输出", "封面/版式", "自制E书", "缓存",
                                 "目录过滤", "更新源", "外观"])
        # 分册模式面板：标签行/控件行贴紧（spacing=2，不用默认 6）
        mode_box = dlg._dirs_tabs.widget(0)
        self.assertTrue(mode_box.title().startswith("分册模式"))
        self.assertEqual(mode_box.layout().spacing(), 2)
        # 面板内边距收窄，内容整体上移
        _m = mode_box.layout().contentsMargins()
        self.assertEqual((_m.left(), _m.top(), _m.right(), _m.bottom()), (4, 9, 4, 2))
        # 顶部与另两页签（E书默认来源和格式/官方电子书本地库）对齐
        for i in (1, 2):
            _om = dlg._dirs_tabs.widget(i).layout().contentsMargins()
            self.assertEqual(_m.top(), _om.top())
        # 余高沉底：末项是 stretch，行只取自然高度（对话框拉高时行间不均摊）
        _lay = mode_box.layout()
        self.assertIsNotNone(_lay.itemAt(_lay.count() - 1).spacerItem())
        # 数据/输出页行距压缩（路径行与页签面板贴紧）
        self.assertEqual(dlg._dirs_tabs.parentWidget().layout().verticalSpacing(), 2)
        labels = []

        def _labels_of(form):
            from PySide6.QtWidgets import QFormLayout
            out = []
            for i in range(form.rowCount()):
                it = form.itemAt(i, QFormLayout.LabelRole)
                if it is not None and it.widget() is not None and hasattr(it.widget(), "text"):
                    out.append(it.widget().text())
            return out

        for f in dlg.findChildren(QFormLayout):
            labels.extend(_labels_of(f))
        self.assertIn("自制程序路径", labels)
        self.assertIn("默认E书来源", labels)
        self.assertNotIn("xml2pdf 路径", labels)
        self.assertNotIn("链路B", "".join(labels))
        # 每个目录行都有浏览按钮
        browses = [b for b in dlg.findChildren(QPushButton) if b.text() == "浏览…"]
        self.assertGreaterEqual(len(browses), 6)
        self.assertTrue(hasattr(dlg, "_pick_dir"))
        self.assertTrue(hasattr(dlg, "_dir_row"))
        self.assertFalse(hasattr(dlg, "ed_book"))
        self.assertFalse(hasattr(dlg, "ed_xmlroot"))

    def test_dirs_subtabs_order(self):
        # 数据/输出三组改 tab 面板，顺序：分册模式 / E书默认来源和格式 / 官方电子书本地库
        dlg = self._dlg()
        tabs = dlg._dirs_tabs
        self.assertEqual([tabs.tabText(i) for i in range(tabs.count())],
                         ["分册模式", "E书默认来源和格式", "官方电子书本地库"])
        self.assertTrue(tabs.widget(0).isAncestorOf(dlg.rb_merge_none))
        self.assertTrue(tabs.widget(1).isAncestorOf(dlg.src_default_box))
        self.assertTrue(tabs.widget(2).isAncestorOf(dlg.ed_official_lib))

    def test_paths_use_native_separator(self):
        # 路径统一本地分隔符显示与落盘（Windows 反斜杠）
        from pathlib import Path as _P
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["official_ebooks_dir"] = "E:/x/y"
        cfg["xml_to_ebooks_dir"] = "E:/x/xb"
        cfg["mulu_dir"] = "E:/x/mulu"
        d2 = SettingsDialog(cfg, None)
        self.assertEqual(d2.ed_ebooks.text(), str(_P("E:/x/y")))
        self.assertEqual(d2.ed_xmlbooks.text(), str(_P("E:/x/xb")))
        out = d2._collect()
        self.assertNotIn("/", out["official_ebooks_dir"])
        self.assertNotIn("/", out["xml_to_ebooks_dir"])

    def test_xml_dir_defaults_and_not_empty(self):
        # 「CBETA XML 目录」：默认 cbeta_xml、不可为空（空则回落默认）；旧空值也回落
        from cbeta_publish.books import xml2pdf_bridge as b
        dlg = self._dlg()
        default = str(Path(b.PROJECT_ROOT) / "cbeta_xml")
        self.assertEqual(dlg.ed_x2p_ebook.text().replace("\\", "/"),
                         default.replace("\\", "/"))
        dlg.ed_x2p_ebook.setText("")
        out = dlg._collect()
        self.assertEqual(out["xml2pdf"]["cbeta_ebook"].replace("\\", "/"),
                         default.replace("\\", "/"))
        # 旧配置空值 → 显示默认
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["xml2pdf"]["cbeta_ebook"] = ""
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.ed_x2p_ebook.text())
        # 标签名
        from PySide6.QtWidgets import QFormLayout
        labels = []
        for f in d2.findChildren(QFormLayout):
            for i in range(f.rowCount()):
                it = f.itemAt(i, QFormLayout.LabelRole)
                if it is not None and it.widget() is not None and hasattr(it.widget(), "text"):
                    labels.append(it.widget().text())
        self.assertIn("CBETA XML 目录", labels)
        self.assertNotIn("XML 工作根", labels)

    def test_cache_xmlbooks_row_wired(self):
        # 缓存页「自制电子书」用 bridge 默认兜底 → 未配置也有值（可统计/清理）
        dlg = self._dlg()
        getter, lbl = dlg._cache_rows["xmlbooks"]
        self.assertTrue(getter())
        self.assertEqual(lbl.text(), "（未配置）" if not getter() else lbl.text())
        self.assertNotEqual(lbl.text(), "（未配置）")

    def test_cache_records_clean_button_label(self):
        # 「校验通过记录」行清理按钮文案「清理」（不再叫「清理通过记录」）
        from PySide6.QtWidgets import QPushButton
        dlg = self._dlg()
        try:
            parent = dlg._verify_records_lbl.parent()
            texts = [b.text() for b in parent.findChildren(QPushButton)]
            self.assertIn("清理", texts)
            self.assertNotIn("清理通过记录", texts)
        finally:
            dlg.close()

    def test_cache_verify_row_wired(self):        # 缓存页新增「校验目录」：getter 用 bridge.verify_dir（未配置也有默认）
        from cbeta_publish.books import xml2pdf_bridge
        dlg = self._dlg()
        self.assertIn("verify", dlg._cache_rows)
        getter, lbl = dlg._cache_rows["verify"]
        self.assertEqual(getter(), str(xml2pdf_bridge.verify_dir(dlg._cfg)))
        self.assertTrue(getter())
        self.assertNotEqual(lbl.text(), "（未配置）")


class CacheCleanWarningTest(unittest.TestCase):
    def _cfg(self, xml_root):
        return {"xml2pdf": {"cbeta_ebook": str(xml_root)}}

    def test_same_dir_warns(self):
        self.assertTrue(cache_clean_warning("E:/dev/cbeta/cbeta_ebook",
                                            self._cfg("E:/dev/cbeta/cbeta_ebook")))

    def test_parent_of_xml_root_warns(self):
        self.assertTrue(cache_clean_warning("E:/dev/cbeta",
                                            self._cfg("E:/dev/cbeta/cbeta_ebook")))

    def test_unrelated_dir_no_warning(self):
        self.assertEqual(cache_clean_warning("E:/dev/cbeta/other",
                                             self._cfg("E:/dev/cbeta/cbeta_ebook")), "")
        self.assertEqual(cache_clean_warning("", self._cfg("E:/x")), "")


if __name__ == "__main__":
    unittest.main()
