# -*- coding: utf-8 -*-
"""界面字体即时生效：保存设置后无需重启（apply_ui_fonts）。"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.gui.main_window import apply_ui_fonts  # noqa: E402


def _ensure_app():
    return QApplication.instance() or QApplication([])


class UiFontsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_apply_changes_app_font_live(self):
        apply_ui_fonts({"app_font": "SimSun", "app_font_size": 11,
                        "supplement_ttf": ""})
        f = QApplication.instance().font()
        self.assertEqual(f.pointSize(), 11)
        self.assertEqual(f.family(), "SimSun")

    def test_bad_values_fall_back(self):
        apply_ui_fonts({"app_font": "", "app_font_size": "xx",
                        "supplement_ttf": "Z:/no/such.ttf"})
        f = QApplication.instance().font()
        self.assertEqual(f.pointSize(), 9)
        self.assertEqual(f.family(), "SimSun")
        # 恢复默认，避免影响其它测试
        apply_ui_fonts({"app_font": "SimSun", "app_font_size": 9,
                        "supplement_ttf": ""})


if __name__ == "__main__":
    unittest.main()
