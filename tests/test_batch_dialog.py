# -*- coding: utf-8 -*-
"""批量对话框来源单选（官方书/自制书）：初始值、切换显隐、run_source()。"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
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


class BatchDialogPurgeTest(unittest.TestCase):
    def test_purge_defaults_off(self):
        dlg = _dlg()
        try:
            self.assertFalse(dlg.chk_purge.isChecked())
            self.assertFalse(dlg.purge_enabled())
        finally:
            dlg.close()

    def test_purge_only_in_merge_mode(self):
        dlg = _dlg()  # combined 默认 update
        try:
            dlg.chk_purge.setChecked(True)
            self.assertFalse(dlg.purge_enabled())  # update 模式不生效
            self.assertFalse(dlg.chk_purge.isVisible())
            dlg.rb_merge.setChecked(True)
            self.assertTrue(dlg.chk_purge.isVisible())
            self.assertTrue(dlg.purge_enabled())
        finally:
            dlg.close()


class BatchDialogXmlHintTest(unittest.TestCase):
    def test_hint_only_update_plus_xml(self):
        dlg = _dlg()
        try:
            self.assertFalse(dlg._xml_hint.isVisible())  # update＋官方：隐藏
            dlg.rb_src_xml.setChecked(True)
            self.assertTrue(dlg._xml_hint.isVisible())  # update＋自制：显示
            dlg.rb_merge.setChecked(True)
            self.assertFalse(dlg._xml_hint.isVisible())  # merge＋自制：隐藏
        finally:
            dlg.close()


class BatchDialogStateTest(unittest.TestCase):
    """选项记忆：state()/apply_state() 往返（供下次打开/下次启动重用）。"""

    def test_default_state_all_checked(self):
        dlg = _dlg()
        try:
            st = dlg.state()
            self.assertEqual(st["unchecked"], [])       # 默认全选非空
            self.assertEqual(st["mode"], "update")       # combined 默认更新素材
            self.assertEqual(st["source"], "official")
            self.assertEqual(st["official_policy"], "stale")
            self.assertEqual(st["self_policy"], "missing")
        finally:
            dlg.close()

    def test_state_roundtrip(self):
        dlg = _dlg()
        try:
            dlg.rb_merge.setChecked(True)
            dlg.rb_src_xml.setChecked(True)
            dlg.chk_zip.setChecked(False)
            dlg.chk_prepare.setChecked(False)
            dlg.chk_purge.setChecked(True)
            dlg.chk_report.setChecked(False)
            dlg._set_combo(dlg.cb_self, "all")
            dlg.list.topLevelItem(1).setCheckState(0, Qt.Unchecked)   # p2 不选
            st = dlg.state()
        finally:
            dlg.close()
        self.assertEqual(st["mode"], "merge")
        self.assertEqual(st["source"], "xml")
        self.assertFalse(st["zip"])
        self.assertFalse(st["auto_prepare"])
        self.assertTrue(st["purge"])
        self.assertFalse(st["save_report"])
        self.assertEqual(st["self_policy"], "all")
        self.assertEqual(st["unchecked"], ["p2"])

        dlg2 = _dlg(initial_state=st)
        try:
            self.assertEqual(dlg2.effective_mode(), "merge")
            self.assertEqual(dlg2.run_source(), "xml")
            self.assertFalse(dlg2.chk_zip.isChecked())
            self.assertFalse(dlg2.chk_prepare.isChecked())
            self.assertTrue(dlg2.chk_purge.isChecked())
            self.assertFalse(dlg2.chk_report.isChecked())
            self.assertEqual(dlg2.self_policy(), "all")
            self.assertEqual([p for p, _d in dlg2.list.selected_items()], ["p1"])
        finally:
            dlg2.close()

    def test_apply_state_new_collections_stay_checked(self):
        # 记录「未勾选」集合：不在其中的（含新增）默认勾选
        dlg = _dlg(initial_state={"unchecked": ["p2"]})
        try:
            self.assertEqual([p for p, _d in dlg.list.selected_items()], ["p1"])
        finally:
            dlg.close()

    def test_fixed_mode_ignores_state_mode(self):
        dlg = _dlg(mode="update", initial_state={"mode": "merge"})
        try:
            self.assertEqual(dlg.effective_mode(), "update")   # 固定模式不被覆盖
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
