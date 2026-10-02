# -*- coding: utf-8 -*-
"""按作者/朝代分册：_group_works 分支、模式值域、右栏只读视图、合并弹框。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

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
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class GroupWorksAuthorDynastyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _works(self, mode, wmap_map, order=(), works=("T1", "T2", "T3", "T9")):
        win = self.win
        if mode == "dynasty":
            win._dynasty_index = lambda: (wmap_map, list(order))
        else:
            win._work_author_map = lambda: dict(wmap_map)
        titles = [f"书名{w}" for w in works]
        return win._group_works({}, list(works), titles, list(works), mode=mode)

    def test_dynasty_order_and_unknown_last(self):
        groups = self._works("dynasty",
                             {"T1": "唐", "T2": "漢", "T3": "唐"},
                             order=("漢", "唐"))
        self.assertEqual([g["label"] for g in groups], ["漢", "唐", "未詳"])
        self.assertEqual([g["stem"] for g in groups], ["漢", "唐", "未詳"])
        self.assertEqual(groups[0]["works"], ["T2"])
        self.assertEqual(groups[1]["works"], ["T1", "T3"])
        self.assertEqual(groups[2]["works"], ["T9"])
        self.assertEqual(groups[1]["segments"], ["唐"])

    def test_author_group_named_once_unknown_last(self):
        groups = self._works("author",
                             {"T1": "窺基", "T2": "安世高", "T3": "窺基"})
        self.assertEqual([g["label"] for g in groups], ["安世高", "窺基", "未署名"])
        self.assertEqual(groups[1]["works"], ["T1", "T3"])
        self.assertEqual(groups[2]["works"], ["T9"])
        self.assertEqual(groups[0]["stem"], "安世高")

    def test_no_depth_effect(self):
        # 作者/朝代单一维度：depth 不影响分组
        g1 = self._works("author", {"T1": "X"}, works=("T1",))
        win = self.win
        win._work_author_map = lambda: {"T1": "X"}
        g5 = win._group_works({}, ["T1"], ["t"], ["T1"], mode="author", depth=5)
        self.assertEqual([g["label"] for g in g1], [g["label"] for g in g5])

    def test_dynasty_title_strips_ce_range(self):
        win = self.win
        self.assertEqual(win._dynasty_name("後秦 384 CE ~ 417 CE"), "後秦")
        self.assertEqual(win._dynasty_name("東漢 25 CE ~ 220 CE"), "東漢")
        self.assertEqual(win._dynasty_name("未詳"), "未詳")
        self.assertEqual(win._dynasty_name(""), "")
        groups = self._works("dynasty",
                             {"T1": "唐 618 CE ~ 907 CE", "T2": "漢 202 BCE"},
                             order=("漢 202 BCE", "唐 618 CE ~ 907 CE"))
        self.assertEqual([g["label"] for g in groups], ["漢", "唐", "未詳"])
        self.assertEqual(groups[1]["stem"], "唐")


class MergeModeValueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_merge_mode_accepts_author_dynasty(self):
        win = self.win
        win.config["merge"] = {"mode": "author"}
        self.assertEqual(win._merge_mode(), "author")
        win.config["merge"] = {"mode": "dynasty"}
        self.assertEqual(win._merge_mode(), "dynasty")

    def test_ask_last_accepts_author_dynasty(self):
        win = self.win
        win.config["merge"] = {"ask_last": {"mode": "author", "depth": 2}}
        self.assertEqual(win._merge_ask_last()["mode"], "author")
        win.config["merge"] = {"ask_last": {"mode": "dynasty", "depth": 3}}
        self.assertEqual(win._merge_ask_last()["mode"], "dynasty")

    def test_right_view_structure_readonly_grouping(self):
        win = self.win
        win._work_author_map = lambda: {"T0001": "窺基"}
        win._dynasty_index = lambda: ({"T0001": "唐"}, ["唐"])
        for mode, label in (("author", "窺基"), ("dynasty", "唐")):
            idx = next(i for i in range(win.coll_view_combo.count())
                       if win.coll_view_combo.itemData(i) == mode)
            win.coll_view_combo.setCurrentIndex(idx)
            self.assertEqual(win._coll_display_mode(), mode)
            struct = win._coll_view_structure({}, ["T0001"])
            self.assertEqual([s[0] for s in struct], [label])


class MergeDialogAuthorDynastyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_author_dynasty_selection(self):
        from cbeta_publish.gui.merge_dialog import MergeDialog
        for mode, rb in (("author", "rb_author"), ("dynasty", "rb_dynasty")):
            dlg = MergeDialog(None, default_mode=mode, default_depth=2,
                              preview=lambda m, d: [])
            try:
                self.assertTrue(getattr(dlg, rb).isChecked())
                self.assertEqual(dlg.chosen(), (mode, 2))
                self.assertFalse(dlg.sp_depth.isEnabled())   # 单维度无深度
            finally:
                dlg.close()


if __name__ == "__main__":
    unittest.main()
