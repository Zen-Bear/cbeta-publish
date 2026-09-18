# -*- coding: utf-8 -*-
"""设置对话框：封面/版式子页签顺序、字体路径用系统默认分隔符、确定(仅应用不保存)。

背景：settings_dialog.py 曾因编码往返损坏，这些断言同时防回归。
"""
import copy
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFormLayout  # noqa: E402

from cbeta_publish.gui.settings_dialog import DEFAULT_CONFIG, SettingsDialog  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


class SettingsDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _app()

    def _dlg(self):
        return SettingsDialog(copy.deepcopy(DEFAULT_CONFIG), None)

    def test_cover_subtabs_order(self):
        # 封面/版式 4 个子页签，按 佛像、背景色 → 字体 → 基准字号 → 边距
        dlg = self._dlg()
        sub = dlg._cover_subtabs
        names = [sub.tabText(i) for i in range(sub.count())]
        self.assertEqual(names, ["封面佛像、背景色", "字体", "基准字号", "边距"])
        # 控件归属：背景色在页签1、字体在页签2、基准字号在页签3、边距在页签4
        self.assertTrue(sub.widget(0).isAncestorOf(dlg.btn_bg))
        self.assertTrue(sub.widget(1).isAncestorOf(dlg.font_rows["title"]))
        self.assertTrue(sub.widget(2).isAncestorOf(dlg.sp_body["a5"]))
        self.assertTrue(sub.widget(3).isAncestorOf(dlg.sp_margins["a5"]["left"]))

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

    def test_restore_buttons_say_dir_data(self):
        # 两个恢复按钮去掉突兀的“(mulu)”，改称“目录数据”
        from PySide6.QtWidgets import QPushButton
        dlg = self._dlg()
        texts = [b.text() for b in dlg.findChildren(QPushButton)]
        self.assertIn("恢复原始（目录数据）", texts)
        self.assertIn("恢复上一次（目录数据）", texts)
        self.assertFalse([t for t in texts if "mulu" in t], texts)

    def test_apply_does_not_write(self):
        dlg = self._dlg()
        # 记录磁盘内容，确认「确定」不写盘
        from cbeta_publish.gui import settings_dialog as sd
        before = sd.CONFIG_PATH.read_bytes() if sd.CONFIG_PATH.exists() else None
        dlg.ed_organizer.setText("测试整理")
        dlg._apply()
        after = sd.CONFIG_PATH.read_bytes() if sd.CONFIG_PATH.exists() else None
        self.assertEqual(before, after)
        self.assertFalse(dlg._did_save)
        self.assertIsInstance(dlg.result_config(), dict)
        self.assertEqual(dlg.result_config()["cover"]["organizer"], "测试整理")

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
        # 分册模式四选一 + 深度；持久化 merge.mode/depth
        dlg = self._dlg()
        self.assertEqual([dlg.rb_merge_none.text(), dlg.rb_merge_volume.text(),
                          dlg.rb_merge_catalog.text(), dlg.rb_merge_ask.text()],
                         ["不分册", "按刊本册", "按目录（部类）", "合并时选择（每次弹框）"])
        dlg.rb_merge_catalog.setChecked(True)
        dlg.sp_merge_depth.setValue(3)
        out = dlg._collect()["merge"]
        self.assertEqual(out["mode"], "catalog")
        self.assertEqual(out["depth"], 3)
        self.assertFalse(out["by_volume"])
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["merge"] = {"mode": "volume", "depth": 1, "by_volume": True}
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.rb_merge_volume.isChecked())
        self.assertEqual(d2.sp_merge_depth.value(), 1)
        self.assertTrue(d2._collect()["merge"]["by_volume"])

    def test_cover_labels_renamed(self):
        # 「发布模式」→「PDF 合并模式」
        dlg = self._dlg()
        labels = []
        form = dlg._cover_form
        for i in range(form.rowCount()):
            it = form.itemAt(i, QFormLayout.LabelRole)
            if it is not None and it.widget() is not None and hasattr(it.widget(), "text"):
                labels.append(it.widget().text())
        self.assertIn("PDF 合并模式", labels)
        self.assertNotIn("发布模式", labels)

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
        # 自制书籍：校验/无校验 单选，持久化到 xml2pdf.verify_build
        dlg = self._dlg()
        self.assertTrue(dlg.rb_build_noverify.isChecked())
        dlg.rb_build_verify.setChecked(True)
        self.assertTrue(dlg._collect()["xml2pdf"]["verify_build"])
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["xml2pdf"]["verify_build"] = True
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.rb_build_verify.isChecked())

    def test_theme_language_are_radio(self):
        # 外观：主题（浅色/深色/跟随系统）与语言（简体/繁体/English）单选
        dlg = self._dlg()
        self.assertEqual([r.text() for r in dlg.theme_radios.values()],
                         ["浅色", "深色", "跟随系统"])
        self.assertEqual([r.text() for r in dlg.lang_radios.values()],
                         ["简体", "繁体", "English"])
        self.assertTrue(dlg.theme_radios["system"].isChecked())
        dlg.theme_radios["dark"].setChecked(True)
        dlg.lang_radios["zh-Hant"].setChecked(True)
        out = dlg._collect()
        self.assertEqual(out["theme"]["mode"], "dark")
        self.assertEqual(out["language"], "zh-Hant")
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["theme"]["mode"] = "light"
        cfg["language"] = "en"
        d2 = SettingsDialog(cfg, None)
        self.assertTrue(d2.theme_radios["light"].isChecked())
        self.assertTrue(d2.lang_radios["en"].isChecked())

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
        dlg.ed_organizer.setText("某某整理")
        out = dlg._collect()
        cv = out["cover"]
        self.assertEqual(cv["organizer"], "某某整理")
        self.assertEqual(cv["sizes"]["body_a5"], 13)
        self.assertEqual(cv["sizes"]["margins"]["a5"],
                         {"left": 21, "right": 22, "top": 23, "bottom": 24})
        self.assertEqual(cv["styles"]["background"]["color"], [1, 2, 3])
        self.assertFalse(cv["images"]["buddha"]["enabled"])
        self.assertIn("font", cv["styles"]["title"])

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


if __name__ == "__main__":
    unittest.main()
