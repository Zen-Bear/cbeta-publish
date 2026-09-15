# -*- coding: utf-8 -*-
"""设置对话框：封面/版式面板顺序、字体路径正斜杠与起始目录、确定(仅应用不保存)。

背景：settings_dialog.py 曾因编码往返损坏，这些断言同时防回归。
"""
import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton  # noqa: E402

from cbeta_publish.gui.settings_dialog import DEFAULT_CONFIG, SettingsDialog  # noqa: E402


def _app():
    return QApplication.instance() or QApplication([])


def _row_titles(form):
    """QFormLayout 行标签文本序列（仅字符串标签）。"""
    from PySide6.QtWidgets import QFormLayout
    role = QFormLayout.ItemRole.LabelRole
    out = []
    for i in range(form.rowCount()):
        item = form.itemAt(i, role)
        w = form.itemAt(i, QFormLayout.ItemRole.FieldRole)
        text = ""
        if item is not None and item.widget() is not None:
            text = item.widget().text()
        elif w is not None and w.widget() is not None and isinstance(w.widget(), QGroupBox):
            text = w.widget().title()
        out.append(text)
    return out


class SettingsDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _app()

    def _dlg(self):
        return SettingsDialog(copy.deepcopy(DEFAULT_CONFIG), None)

    def test_cover_tab_order_bg_font_margins(self):
        dlg = self._dlg()
        texts = _row_titles(dlg._cover_form)
        i_bg = texts.index("封面背景色")
        i_font = texts.index("字体（封面/目录/说明页）")
        i_margin = texts.index("每纸张边距(pt)")
        self.assertLess(i_bg, i_font)
        self.assertLess(i_font, i_margin)

    def test_slash_and_font_input(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["styles"]["title"] = {"font": "C:\\Windows\\Fonts\\simhei.ttf"}
        dlg = SettingsDialog(cfg, None)
        self.assertEqual(dlg.font_rows["title"].text(), "C:/Windows/Fonts/simhei.ttf")
        self.assertEqual(SettingsDialog._slash(None), "")
        self.assertEqual(SettingsDialog._slash("a\\b\\c"), "a/b/c")

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

    def test_series_migrates_to_imprint(self):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["cover"]["series"] = "太虛大師全書"
        dlg = SettingsDialog(cfg, None)
        self.assertEqual(dlg.ed_imprint.text(), "太虛大師全書")
        self.assertNotIn("series", dlg._cfg["cover"])


if __name__ == "__main__":
    unittest.main()
