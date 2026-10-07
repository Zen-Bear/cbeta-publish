# -*- coding: utf-8 -*-
"""批量对话框来源单选（官方书/自制书）：初始值、切换显隐、run_source()。"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.gui.batch_dialogs import BatchDialog  # noqa: E402

_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _dlg(**kw):
    _ensure_app()
    items = [("p1", {"name": "甲", "work_ids": ["T0001"]}),
             ("p2", {"name": "乙", "work_ids": ["T0002"]})]
    kw.setdefault("mode", "combined")
    kw.setdefault("merge_fmts", ["pdf"])
    kw.setdefault("zip_fmts", ["epub"])
    dlg = BatchDialog(items, lambda d: ("none", 2, ""), **kw)
    dlg.show()  # offscreen 下 show 才能用 isVisible 断言行显隐
    return dlg


class BatchDialogSourceTest(unittest.TestCase):
    def test_default_is_official(self):
        dlg = _dlg()
        try:
            self.assertTrue(dlg.rb_src_official.isChecked())
            self.assertEqual(dlg.run_source(), "official")
            self.assertTrue(dlg._row_official.isVisible())
            self.assertFalse(dlg._row_self.isVisible())
        finally:
            dlg.close()

    def test_init_source_xml(self):
        dlg = _dlg(run_source="xml")
        try:
            self.assertTrue(dlg.rb_src_xml.isChecked())
            self.assertEqual(dlg.run_source(), "xml")
            self.assertFalse(dlg._row_official.isVisible())
            self.assertTrue(dlg._row_self.isVisible())
        finally:
            dlg.close()

    def test_invalid_source_falls_back_official(self):
        dlg = _dlg(run_source="bogus")
        try:
            self.assertEqual(dlg.run_source(), "official")
        finally:
            dlg.close()

    def test_toggle_switches_policy_rows(self):
        dlg = _dlg()
        try:
            dlg.rb_src_xml.setChecked(True)
            self.assertEqual(dlg.run_source(), "xml")
            self.assertFalse(dlg._row_official.isVisible())
            self.assertTrue(dlg._row_self.isVisible())
            dlg.rb_src_official.setChecked(True)
            self.assertEqual(dlg.run_source(), "official")
            self.assertTrue(dlg._row_official.isVisible())
            self.assertFalse(dlg._row_self.isVisible())
        finally:
            dlg.close()

    def test_policies_still_readable(self):
        dlg = _dlg()
        try:
            self.assertEqual(dlg.official_policy(), "stale")
            self.assertEqual(dlg.self_policy(), "missing")
        finally:
            dlg.close()

    def test_source_row_visible_in_update_mode(self):
        # 更新素材模式也有来源单选（两种模式共用）
        dlg = _dlg(mode="update")
        try:
            self.assertTrue(dlg.rb_src_official.isVisible())
            dlg.rb_src_xml.setChecked(True)
            self.assertEqual(dlg.run_source(), "xml")
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
