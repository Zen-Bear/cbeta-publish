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

    def test_by_volume_label_mentions_file_naming(self):
        dlg = self._dlg()
        self.assertIn("每册一个文件", dlg.chk_by_volume.text())
        self.assertTrue(dlg.chk_by_volume.toolTip())

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


if __name__ == "__main__":
    unittest.main()
