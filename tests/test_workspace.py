# -*- coding: utf-8 -*-
"""左栏工作区面板（统一模型的二栏视图）：

- 搜索行：清除(✕)恢复目录（保留展开）与「＋」把搜索结果加入工作区；「工作区/目录区」切换面板
- 工作区面板 = 中栏（同一份 `_workspace`，同一套 排序/全选/不选/加入已选/全删 控件）
- 右栏移除的书流入工作区（不自动切换面板）
- 工作区可拖入右栏（移动：加入后移出工作区）
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt, QMimeData  # noqa: E402

from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class FakeDrop:
    def __init__(self, src, md):
        self._src, self._md, self.accepted = src, md, False
    def source(self): return self._src
    def mimeData(self): return self._md
    def acceptProposedAction(self): self.accepted = True
    def ignore(self): pass


def _make_window(layout="two"):
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "collections" / "custom").mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    (tmp / "collections" / "custom" / "测.json").write_text(json.dumps({
        "id": "t", "name": "测", "category": "custom", "tags": [],
        "work_ids": ["T0001", "T0002"]}, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    cfg.setdefault("ui", {})["layout"] = layout
    win = MainWindow(cfg)
    for i in range(win.coll_combo.count()):
        if str(win.coll_combo.itemData(i)).endswith("测.json"):
            win.coll_combo.setCurrentIndex(i)
            break
    _ensure_app().processEvents()
    return win, tmp


class WorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window("two")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _coll_data(self):
        w = self.win
        for i in range(w.coll_combo.count()):
            if str(w.coll_combo.itemData(i)).endswith("测.json"):
                return w.coll_combo.itemData(i)
        self.fail("测.json not in combo")

    def setUp(self):
        w = self.win
        w._workspace = []
        w._selected = set()
        w._search_results = []
        if w.btn_workspace.isChecked():
            w.btn_workspace.setChecked(False)
        w._refresh_ws_views()
        w.search.blockSignals(True); w.search.clear(); w.search.blockSignals(False)
        w.nav_combo.blockSignals(True); w.nav_combo.setCurrentText("部类"); w.nav_combo.blockSignals(False)
        w._on_nav_changed("部类")
        w._apply_layout("two")
        # 右栏状态快照：各用例互不污染
        self._saved_ids = list(w._coll_dict(self._coll_data())["work_ids"])
        _ensure_app().processEvents()

    def tearDown(self):
        self.win._coll_dict(self._coll_data())["work_ids"] = self._saved_ids

    # ---------- 搜索行按钮 ----------
    def test_search_row_buttons_exist(self):
        w = self.win
        self.assertEqual(w.btn_clear_search.text(), "✕")
        self.assertEqual(w.btn_ws_add.text(), "＋")
        self.assertTrue(w.btn_workspace.isCheckable())
        self.assertFalse(w.ws_page.isVisibleTo(w))
        # 顺序：搜索框… ✕ ＋ 工作区（＋ 在清除右边）
        lay = w.btn_clear_search.parent().layout()
        self.assertLess(lay.indexOf(w.btn_clear_search), lay.indexOf(w.btn_ws_add))
        self.assertLess(lay.indexOf(w.btn_ws_add), lay.indexOf(w.btn_workspace))

    def test_clear_search_resets_filters(self):
        w = self.win
        w.search.setText("長阿含")
        _ensure_app().processEvents()
        if w.bulei_filter.count() > 1:
            w.bulei_filter.setCurrentIndex(1)
            _ensure_app().processEvents()
        w._clear_search()
        _ensure_app().processEvents()
        self.assertEqual(w.search.text(), "")
        self.assertEqual(w.bulei_filter.currentIndex(), 0)
        self.assertEqual(w._search_results, [])

    def test_clear_search_keeps_nav_expansion(self):
        w = self.win
        w.nav_combo.setCurrentText("部类")
        _ensure_app().processEvents()
        top = w.tree.topLevelItem(0)
        top.setExpanded(True)
        kid = top.child(0)
        kid.setExpanded(True)
        before = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
        w.search.setText("T0095")
        _ensure_app().processEvents()
        w._clear_search()
        _ensure_app().processEvents()
        after = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
        self.assertEqual(before, after)
        self.assertTrue(w.tree.topLevelItem(0).isExpanded())
        self.assertTrue(w.tree.topLevelItem(0).child(0).isExpanded())

    # ---------- 面板切换 ----------
    def test_workspace_toggle_hides_catalog(self):
        w = self.win
        self.assertTrue(w.tree.isVisibleTo(w))
        self.assertEqual(w.btn_workspace.text(), "工作区")
        w.btn_workspace.setChecked(True)
        _ensure_app().processEvents()
        self.assertTrue(w.ws_page.isVisibleTo(w))
        self.assertFalse(w.tree.isVisibleTo(w))
        self.assertEqual(w.btn_workspace.text(), "目录区")   # 文字随状态切换
        w.btn_workspace.setChecked(False)
        _ensure_app().processEvents()
        self.assertFalse(w.ws_page.isVisibleTo(w))
        self.assertTrue(w.tree.isVisibleTo(w))
        self.assertEqual(w.btn_workspace.text(), "工作区")

    def test_ws_button_label_shows_count(self):
        w = self.win
        w._ws_add(["T0001", "T0002"])
        self.assertEqual(w.btn_workspace.text(), "工作区（2）")
        w.btn_workspace.setChecked(True)
        _ensure_app().processEvents()
        self.assertEqual(w.btn_workspace.text(), "目录区（2）")

    def test_ws_items_show_work_id(self):
        w = self.win
        w._ws_add(["T0001"])
        self.assertIn("T0001", w.ws_tree.topLevelItem(0).text(0))
        self.assertIn("T0001", w.list.item(0).text())

    # ---------- 加入工作区 ----------
    def test_ws_add_search(self):
        w = self.win
        w.search.setText("T0095")
        _ensure_app().processEvents()
        res = list(w._search_results)
        self.assertTrue(res)
        w._ws_add_search()
        self.assertEqual(w._workspace, res)
        self.assertIn("工作区", w.btn_workspace.text())
        w._ws_add_search()          # 去重
        self.assertEqual(len(w._workspace), len(res))

    def test_removal_goes_to_workspace(self):
        w = self.win
        w._remove_works_from_collection(["T0001"])
        _ensure_app().processEvents()
        self.assertIn("T0001", w._workspace)
        # 中栏与左栏工作区同一份数据
        self.assertIn("T0001", [w.list.item(i).data(Qt.UserRole) for i in range(w.list.count())])
        # 目录树/搜索框不受影响
        self.assertEqual(w.search.text(), "")

    # ---------- 工作区 → 右栏（移动） ----------
    def test_ws_drag_to_right(self):
        w = self.win
        w._ws_add(["T0095"])
        w.btn_workspace.setChecked(True)
        _ensure_app().processEvents()
        it = w.ws_tree.topLevelItem(0)
        it.setSelected(True)
        fe = FakeDrop(w.ws_tree, w.ws_tree.mimeData([it]))
        w._coll_drop(fe)
        _ensure_app().processEvents()
        self.assertTrue(fe.accepted)
        self.assertIn("T0095", w._coll_dict(self._coll_data())["work_ids"])
        self.assertEqual(w._workspace, [])          # 移动语义：移出工作区

    def test_ws_double_click_adds_to_right(self):
        w = self.win
        w._ws_add(["T0095"])
        it = w.ws_tree.topLevelItem(0)
        w._on_ws_double_click(it, 0)
        _ensure_app().processEvents()
        self.assertIn("T0095", w._coll_dict(self._coll_data())["work_ids"])
        self.assertEqual(w._workspace, [])

    # ---------- 拖放目标放行 ----------
    def test_drag_move_accepts_real_drags(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QDragMoveEvent
        w = self.win
        for view in (w.coll_list, w.list, w.tree, w.ws_tree):
            md = QMimeData()
            md.setText("T0001\n")
            ev = QDragMoveEvent(QPoint(5, 5), Qt.CopyAction | Qt.MoveAction, md,
                                Qt.LeftButton, Qt.NoModifier)
            view.dragMoveEvent(ev)
            self.assertTrue(ev.isAccepted(), view)

    def _select_coll_row(self, w, wid):
        w._load_coll_works()
        _ensure_app().processEvents()
        for i in range(w.coll_list.count()):
            if w.coll_list.item(i).data(Qt.UserRole) == wid:
                w.coll_list.setCurrentRow(i)
                w.coll_list.item(i).setSelected(True)
                return True
        return False

    def test_coll_drop_to_tree_removes(self):
        # 右栏拖到目录树 = 移除（并加入工作区），目录树本身不动
        w = self.win
        w.nav_combo.setCurrentText("部类")
        _ensure_app().processEvents()
        before_tops = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
        self.assertTrue(self._select_coll_row(w, "T0001"))
        fe = FakeDrop(w.coll_list, QMimeData())
        w._tree_drop(fe)
        _ensure_app().processEvents()
        self.assertTrue(fe.accepted)
        self.assertNotIn("T0001", w._coll_dict(self._coll_data())["work_ids"])
        self.assertIn("T0001", w._workspace)
        after_tops = [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]
        self.assertEqual(before_tops, after_tops)

    def test_coll_drop_to_workspace_removes_without_auto_enter(self):
        # 右栏拖到工作区面板 = 移除；不自动切到工作区面板（用户点「工作区」才进入）
        w = self.win
        self.assertFalse(w.btn_workspace.isChecked())
        self.assertTrue(self._select_coll_row(w, "T0002"))
        fe = FakeDrop(w.coll_list, QMimeData())
        w._ws_drop(fe)
        _ensure_app().processEvents()
        self.assertTrue(fe.accepted)
        self.assertNotIn("T0002", w._coll_dict(self._coll_data())["work_ids"])
        self.assertIn("T0002", w._workspace)
        self.assertFalse(w.btn_workspace.isChecked())
        self.assertFalse(w.ws_page.isVisibleTo(w))
        self.assertTrue(w.tree.isVisibleTo(w))

    def _find_bulei_leaf(self, w):
        def walk(it):
            if it.childCount() == 0:
                return it
            for i in range(it.childCount()):
                r = walk(it.child(i))
                if r is not None:
                    return r
            return None
        for i in range(w.tree.topLevelItemCount()):
            r = walk(w.tree.topLevelItem(i))
            if r is not None:
                return r
        return None

    def test_coll_drop_with_empty_mime_uses_selection(self):
        # 真实拖拽带的 mime 没有 text/plain（内部 model 格式）：靠选中项提取作品
        w = self.win
        w.nav_combo.setCurrentText("部类")
        _ensure_app().processEvents()
        leaf = self._find_bulei_leaf(w)
        self.assertIsNotNone(leaf)
        wid = w._item_payload(leaf)[0][0]
        w.tree.clearSelection()
        leaf.setSelected(True)
        fe = FakeDrop(w.tree, QMimeData())
        w._coll_drop(fe)
        _ensure_app().processEvents()
        self.assertTrue(fe.accepted)
        self.assertIn(wid, w._coll_dict(self._coll_data())["work_ids"])

    def test_ws_drop_with_empty_mime_uses_selection(self):
        w = self.win
        w._ws_add(["T0098"])
        d = w._coll_dict(self._coll_data())
        if "T0098" in d["work_ids"]:
            d["work_ids"] = [x for x in d["work_ids"] if x != "T0098"]
        w.btn_workspace.setChecked(True)
        _ensure_app().processEvents()
        it = next(w.ws_tree.topLevelItem(i) for i in range(w.ws_tree.topLevelItemCount())
                  if (w.ws_tree.topLevelItem(i).data(0, Qt.UserRole) or {}).get("key") == "T0098")
        w.ws_tree.clearSelection()
        it.setSelected(True)
        fe = FakeDrop(w.ws_tree, QMimeData())
        w._coll_drop(fe)
        _ensure_app().processEvents()
        self.assertTrue(fe.accepted)
        self.assertIn("T0098", w._coll_dict(self._coll_data())["work_ids"])
        self.assertEqual(w._workspace, [])          # 移动语义：加入后移出工作区

    def test_nav_change_returns_to_catalog(self):
        w = self.win
        w.btn_workspace.setChecked(True)
        _ensure_app().processEvents()
        self.assertFalse(w.tree.isVisibleTo(w))
        w.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        self.assertFalse(w.btn_workspace.isChecked())
        self.assertTrue(w.tree.isVisibleTo(w))

    def test_ws_panel_controls_share_handlers(self):
        # 左栏工作区面板与中栏同一套操作：勾选 → 加入已选 → 移出工作区
        w = self.win
        w._ws_add(["T0098"])
        w.btn_workspace.setChecked(True)
        _ensure_app().processEvents()
        it = w.ws_tree.topLevelItem(0)
        it.setCheckState(0, Qt.Checked)
        _ensure_app().processEvents()
        self.assertIn("T0098", w._selected)
        w.ws_btn_add_sel.click()
        _ensure_app().processEvents()
        self.assertIn("T0098", w._coll_dict(self._coll_data())["work_ids"])
        self.assertEqual(w._workspace, [])
        # 全删清空
        w._ws_add(["T0098"])
        w.ws_btn_clear_list.click()
        _ensure_app().processEvents()
        self.assertEqual(w._workspace, [])

    # ---------- 分隔条收起/恢复按钮 ----------
    def _mid_handle(self):
        # 取「中间栏右侧」的分隔条（其左侧栏索引 == 1）
        sp = self.win._splitter
        for i in range(sp.count()):
            h = sp.handle(i)
            if h is not None and h._left_index() == 1:
                return h
        return None

    def test_splitter_handle_collapse_restore_repeatable(self):
        # 收起/恢复必须可反复：判定一次后缓存，第 2 次收起也要生效
        w = self.win
        w._apply_layout("three")
        sp = w._splitter
        sp.setSizes([400, 360, 360])
        _ensure_app().processEvents()
        h = self._mid_handle()
        self.assertIsNotNone(h)
        h._collapse()
        self.assertEqual(sp.sizes()[1], 0)
        h._restore()
        self.assertGreater(sp.sizes()[1], 0)
        h._collapse()                      # 第二次收起（旧实现在这里失效）
        self.assertEqual(sp.sizes()[1], 0)
        h._restore()
        self.assertGreater(sp.sizes()[1], 0)

    def test_splitter_handle_index_cached(self):
        w = self.win
        w._apply_layout("three")
        w._splitter.setSizes([400, 360, 360])
        _ensure_app().processEvents()
        h = self._mid_handle()
        idx = h._left_index()
        self.assertEqual(h._panel(), idx)
        h._collapse()
        # 折叠后几何变了，但缓存索引不变（否则会指错栏）
        self.assertEqual(h._panel(), idx)
        h._restore()
        self.assertEqual(h._panel(), idx)


if __name__ == "__main__":
    unittest.main()
