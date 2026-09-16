# -*- coding: utf-8 -*-
"""工作区统一模型：

- 中栏（三栏）与左栏工作区面板（二栏）是同一个内存目录 `_workspace`，功能一致
- 搜索结果渲染到左栏「搜索结果」节点，不写入工作区（＋/双击才加入）
- 加入右栏 = 移动（从工作区移出）；右栏移除 = 把书加入工作区
- 固定约束：右栏书目操作不影响左栏（树/选中/过滤器/搜索框）
- 「工作区/目录区」切换按钮只在二栏显示
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
    """轻量 drop 事件（避免真拖拽）：source()/mimeData()/acceptProposedAction()。"""
    def __init__(self, src, md):
        self._src, self._md, self.accepted = src, md, False
    def source(self): return self._src
    def mimeData(self): return self._md
    def acceptProposedAction(self): self.accepted = True
    def ignore(self): pass


def _md(text):
    m = QMimeData()
    m.setText(text)
    return m


def _make_window(layout="three"):
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "collections" / "custom").mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    (tmp / "collections" / "custom" / "测.json").write_text(json.dumps({
        "id": "t", "name": "测", "category": "custom", "tags": [], "work_ids": []},
        ensure_ascii=False), encoding="utf-8")
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
    for _ in range(6):
        _ensure_app().processEvents()
    return win, tmp


class ThreePaneTest(unittest.TestCase):
    """三栏：中栏=工作区（同一份数据）。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window("three")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        w = self.win
        d = self.coll()
        d["work_ids"] = []
        d["work_groups"] = {}
        d["work_sources"] = {}
        w._load_coll_works()
        w._workspace = []
        w._selected = set()
        w._search_results = []
        w._refresh_ws_views()
        w.search.blockSignals(True); w.search.clear(); w.search.blockSignals(False)
        w.nav_combo.blockSignals(True); w.nav_combo.setCurrentText("部类"); w.nav_combo.blockSignals(False)
        w._on_nav_changed("部类")
        self.pump(4)

    # ---------- 工具 ----------
    def pump(self, n=8):
        for _ in range(n):
            _ensure_app().processEvents()

    def mid(self):
        w = self.win
        return [w.list.item(i).data(Qt.UserRole) for i in range(w.list.count())]

    def ws_left(self):
        w = self.win
        return [(w.ws_tree.topLevelItem(i).data(0, Qt.UserRole) or {}).get("key")
                for i in range(w.ws_tree.topLevelItemCount())]

    def coll(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def left_state(self):
        w = self.win
        cur = w.tree.currentItem()
        return (w.nav_combo.currentText(), w.tree.topLevelItemCount(),
                cur.text(0) if cur else None, w.search.text(),
                w.bulei_filter.currentIndex(), w.tripitaka_filter.currentIndex(),
                w.vol_filter.currentIndex())

    # ---------- 中栏与左栏工作区 = 同一份数据 ----------
    def test_mid_and_left_share_workspace(self):
        w = self.win
        w._ws_add(["T0001", "T0002"])
        self.pump(2)
        self.assertEqual(self.mid(), ["T0001", "T0002"])
        self.assertEqual(self.ws_left(), ["T0001", "T0002"])
        self.assertEqual(self.mid(), self.ws_left())

    def test_checks_sync_both_views(self):
        w = self.win
        w._ws_add(["T0001", "T0002"])
        self.pump(2)
        w.list.item(0).setCheckState(Qt.Checked)
        self.pump(2)
        self.assertIn("T0001", w._selected)
        self.assertEqual(w.ws_tree.topLevelItem(0).checkState(0), Qt.Checked)
        # 反向：左栏取消勾选 → 中栏同步
        w.ws_tree.topLevelItem(0).setCheckState(0, Qt.Unchecked)
        self.pump(2)
        self.assertNotIn("T0001", w._selected)
        self.assertEqual(w.list.item(0).checkState(), Qt.Unchecked)

    def test_sort_orders_both_views(self):
        w = self.win
        w._ws_add(["T0009", "T0001"])
        self.pump(2)
        self.assertEqual(self.mid(), ["T0009", "T0001"])
        w._set_sort_mode("经号排序")
        self.pump(2)
        self.assertEqual(self.mid(), ["T0001", "T0009"])
        self.assertEqual(self.ws_left(), ["T0001", "T0009"])
        w._set_sort_mode("原始顺序")      # 视图级排序，不改原始加入顺序
        self.pump(2)
        self.assertEqual(self.mid(), ["T0009", "T0001"])

    # ---------- 加入右栏 = 移动（移出工作区） ----------
    def test_add_selected_moves_out_of_workspace(self):
        w = self.win
        w._ws_add(["T0001", "T0002"])
        self.pump(2)
        for i in range(w.list.count()):
            w.list.item(i).setCheckState(Qt.Checked)
        self.pump(2)
        w._add_selected_to_coll()
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], ["T0001", "T0002"])
        self.assertEqual(self.mid(), [])            # 已移出工作区
        self.assertEqual(self.ws_left(), [])
        self.assertEqual(w._selected, set())
        # 目录里仍能搜到（可重复加入）
        w.search.setText("T0001")
        self.pump(12)
        self.assertTrue(any(t.startswith("搜索结果") for t in self.left_tops()))
        w._clear_search()
        self.pump(6)

    def test_add_already_in_collection_also_moves_out(self):
        w = self.win
        w._ws_add(["T0001"])
        self.pump(2)
        w.list.item(0).setCheckState(Qt.Checked)
        w._add_selected_to_coll()          # 第一次：真正加入
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], ["T0001"])
        w._ws_add(["T0001"])               # 再放进工作区
        self.pump(2)
        w.list.item(0).setCheckState(Qt.Checked)
        self.pump(2)
        w._add_selected_to_coll()          # 第二次：已在右栏，也应移出
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], ["T0001"])   # 未重复
        self.assertEqual(self.mid(), [])

    def test_middle_drag_to_coll_moves_out(self):
        w = self.win
        w._ws_add(["T0095", "T0102"])
        self.pump(2)
        w.list.item(0).setSelected(True)
        w._coll_drop(FakeDrop(w.list, _md("T0095")))
        self.pump(4)
        self.assertIn("T0095", self.coll()["work_ids"])
        self.assertNotIn("T0095", self.mid())       # 移动语义
        self.assertIn("T0102", self.mid())

    def test_workspace_double_click_moves_to_right(self):
        w = self.win
        w._ws_add(["T0009"])
        self.pump(2)
        item = w.ws_tree.topLevelItem(0)
        w._on_ws_double_click(item, 0)
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], ["T0009"])
        self.assertEqual(self.mid(), [])

    # ---------- 右栏移除 = 加入工作区 ----------
    def test_remove_adds_to_workspace_and_restores_group(self):
        w = self.win
        self.coll()["work_ids"] = ["T0001", "T0002"]
        self.coll().setdefault("work_groups", {})["T0001"] = "第一册"
        w._load_coll_works()
        self.pump(2)
        w._remove_works_from_collection(["T0001"])
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], ["T0002"])
        self.assertEqual(self.mid(), ["T0001"])
        self.assertEqual(w._work_groups.get("T0001"), "第一册")   # 册标签恢复
        self.assertEqual(self.coll().get("work_groups") or {}, {})
        # 再移除一部 → 追加到末尾、不重复
        self.coll()["work_ids"] = ["T0002"]
        w._load_coll_works()
        self.pump(2)
        w._remove_works_from_collection(["T0002"])
        self.pump(4)
        self.assertEqual(self.mid(), ["T0001", "T0002"])

    def test_right_drag_back_to_workspace(self):
        w = self.win
        self.coll()["work_ids"] = ["T0001"]
        w._load_coll_works()
        self.pump(2)
        w.coll_list.item(0).setSelected(True)
        w._list_drop(FakeDrop(w.coll_list, _md("T0001")))
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], [])
        self.assertEqual(self.mid(), ["T0001"])

    def test_remove_button_path(self):
        from PySide6.QtWidgets import QCheckBox
        w = self.win
        self.coll()["work_ids"] = ["T0001"]
        w._load_coll_works()
        self.pump(2)
        row = w.coll_list.itemWidget(w.coll_list.item(0))
        cb = row.findChildren(QCheckBox)[0]
        cb.setChecked(True)
        w._remove_from_coll()
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], [])
        self.assertEqual(self.mid(), ["T0001"])

    # ---------- 目录树 -> 右栏 = 拷贝 ----------
    def test_left_tree_drag_to_coll_is_copy(self):
        w = self.win
        w.nav_combo.setCurrentText("刊本")
        self.pump(12)
        self.assertGreater(w.tree.topLevelItemCount(), 0)
        edition = w.tree.topLevelItem(0)
        vol = None
        for i in range(edition.childCount()):
            if edition.child(i).childCount():
                vol = edition.child(i)
                break
        self.assertIsNotNone(vol)
        md = w.tree.mimeData([vol])
        fe = FakeDrop(w.tree, md)
        w._coll_drop(fe)
        self.pump(4)
        self.assertTrue(fe.accepted)
        self.assertGreater(len(self.coll()["work_ids"]), 0)
        self.assertGreater(len(self.coll().get("work_groups") or {}), 0)
        self.assertEqual(self.mid(), [])            # 目录树拖入不经过工作区

    # ---------- 约束：右栏操作不影响左栏 ----------
    def test_right_ops_do_not_touch_left(self):
        w = self.win
        w.nav_combo.setCurrentText("刊本")
        w.search.setText("")
        self.pump(12)
        before = self.left_state()
        self.coll()["work_ids"] = ["T0001", "T0002"]
        w._load_coll_works()
        self.pump(2)
        w._remove_works_from_collection(["T0001"])   # 右栏移除
        self.pump(2)
        w._ws_add(["T0001"])
        w.list.item(0).setCheckState(Qt.Checked)
        self.pump(2)
        w._add_selected_to_coll()                    # 右栏加入
        self.pump(4)
        self.assertEqual(self.left_state(), before)

    # ---------- 工作区内部手势 ----------
    def test_tree_drop_removes_from_workspace(self):
        w = self.win
        w._ws_add(["T0001", "T0002"])
        self.pump(2)
        w._tree_drop(FakeDrop(w.list, _md("T0001")))
        self.pump(4)
        self.assertEqual(self.mid(), ["T0002"])
        self.assertEqual(self.coll()["work_ids"], [])

    # ---------- 搜索：结果进左栏，不进工作区 ----------
    def left_tops(self):
        w = self.win
        return [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]

    def test_search_renders_results_in_left_not_workspace(self):
        w = self.win
        w._ws_add(["T0001"])
        self.pump(2)
        w.search.setText("T0095")
        self.pump(14)
        self.assertTrue(any(t.startswith("搜索结果") for t in self.left_tops()), self.left_tops())
        self.assertTrue(w._search_results)
        self.assertEqual(self.mid(), ["T0001"])      # 工作区不受搜索影响

    def test_ws_add_search_from_results(self):
        w = self.win
        w.search.setText("T0095")
        self.pump(14)
        res = list(w._search_results)
        self.assertTrue(res)
        w._ws_add_search()
        self.pump(4)
        for x in res:
            self.assertIn(x, w._workspace)

    def test_catalog_double_click_adds_to_workspace_in_three(self):
        w = self.win
        w.nav_combo.setCurrentText("刊本")
        self.pump(12)
        edition = w.tree.topLevelItem(0)
        vol = None
        for i in range(edition.childCount()):
            if edition.child(i).childCount():
                vol = edition.child(i)
                break
        leaf = vol.child(0)
        wid = (leaf.data(0, Qt.UserRole) or {}).get("key")
        w._on_tree_double_click(leaf, 0)
        self.pump(4)
        self.assertIn(wid, w._workspace)
        self.assertEqual(self.coll()["work_ids"], [])   # 三栏：只进工作区


class LayoutSettingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window("three")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_apply_layout_hides_middle(self):
        w = self.win
        w._apply_layout("three")
        self.assertFalse(w.mid.isHidden())
        w._apply_layout("two")
        self.assertTrue(w.mid.isHidden())          # 真二栏：隐藏中栏（不是压成 0 宽）
        w._apply_layout("three")
        self.assertFalse(w.mid.isHidden())

    def test_layout_actions_in_menu(self):
        # 布局 2/3 栏在菜单栏「视图」里，可选中且互斥；切换写入配置
        import json
        w = self.win
        self.assertTrue(w.act_three.isCheckable() and w.act_two.isCheckable())
        self.assertTrue(w.act_three.isChecked() or w.act_two.isChecked())
        w.act_two.setChecked(True)
        w.act_two.trigger()
        _ensure_app().processEvents()
        self.assertTrue(w.mid.isHidden())
        self.assertEqual(w.config["ui"]["layout"], "two")
        p = Path(w._config_path)
        if p.exists():
            self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["ui"]["layout"], "two")
        self.assertFalse(w.act_three.isChecked())    # 互斥
        w.act_three.setChecked(True)
        w.act_three.trigger()
        _ensure_app().processEvents()
        self.assertFalse(w.mid.isHidden())
        self.assertEqual(w.config["ui"]["layout"], "three")

    def test_settings_action_direct_in_menubar(self):
        # 设置可直接点（不再 设置→设置 两级）
        w = self.win
        acts = [a.text() for a in w.menuBar().actions()]
        self.assertIn("设置…", acts)
        menus = [a.menu().title() for a in w.menuBar().actions() if a.menu() is not None]
        self.assertNotIn("设置", menus)

    def test_workspace_button_only_in_two_pane(self):
        w = self.win
        w._apply_layout("three")
        _ensure_app().processEvents()
        self.assertFalse(w.btn_workspace.isVisibleTo(w))
        w._apply_layout("two")
        _ensure_app().processEvents()
        self.assertTrue(w.btn_workspace.isVisibleTo(w))
        w._apply_layout("three")
        _ensure_app().processEvents()

    def test_startup_window_size_by_layout(self):
        # 启动时：二栏收窄窗口，三栏用默认宽度
        import json as _json
        base = _json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
        tmp = Path(tempfile.mkdtemp())
        (tmp / "collections" / "custom").mkdir(parents=True)
        (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
        (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
        base["mulu_dir"] = str(ROOT / "mulu")
        base["collections_dir"] = str(tmp / "collections")
        base["update_interval"] = "manual"
        base["_config_path"] = str(tmp / "app.json")
        made = []
        try:
            for layout, expect in (("two", 1000), ("three", 1240)):
                base.setdefault("ui", {})["layout"] = layout
                win = MainWindow(base)
                made.append(win)
                self.assertEqual(win.width(), expect, layout)
        finally:
            for win in made:
                win.close()
            shutil.rmtree(tmp, ignore_errors=True)


class TwoPaneTest(unittest.TestCase):
    """二栏（隐藏中栏）：左栏工作区面板 = 中栏；搜索结果进左栏树。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window("two")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        w = self.win
        d = self.coll()
        d["work_ids"] = []
        d["work_groups"] = {}
        d["work_sources"] = {}
        w._load_coll_works()
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
        self.pump(6)

    def pump(self, n=8):
        for _ in range(n):
            _ensure_app().processEvents()

    def coll(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def left_tops(self):
        w = self.win
        return [w.tree.topLevelItem(i).text(0) for i in range(w.tree.topLevelItemCount())]

    def test_two_pane_hides_middle(self):
        self.assertTrue(self.win.mid.isHidden())

    def test_workspace_panel_toggle_and_controls(self):
        w = self.win
        self.assertTrue(w.tree.isVisibleTo(w))
        w.btn_workspace.setChecked(True)
        self.pump(4)
        self.assertTrue(w.ws_page.isVisibleTo(w))
        self.assertFalse(w.tree.isVisibleTo(w))
        # 与中栏一致的控制行
        self.assertEqual([w.ws_sort_combo.count()], [3])
        self.assertEqual(w.ws_btn_all.text(), "全选")
        self.assertEqual(w.ws_btn_none.text(), "不选")
        self.assertEqual(w.ws_btn_add_sel.text(), "加入已选")
        self.assertEqual(w.ws_btn_clear_list.text(), "全删")
        w.btn_workspace.setChecked(False)
        self.pump(4)
        self.assertTrue(w.tree.isVisibleTo(w))

    def test_ws_panel_checkbox_and_add_selected(self):
        # 左栏工作区面板可直接勾选并加入右栏（功能与中栏一致）
        w = self.win
        w._ws_add(["T0001"])
        self.pump(2)
        it = w.ws_tree.topLevelItem(0)
        it.setCheckState(0, Qt.Checked)
        self.pump(2)
        self.assertIn("T0001", w._selected)
        w.ws_btn_add_sel.click()
        self.pump(4)
        self.assertEqual(self.coll()["work_ids"], ["T0001"])
        self.assertEqual(w._workspace, [])

    def test_right_remove_adds_to_workspace(self):
        w = self.win
        self.coll()["work_ids"] = ["T0001"]
        w._load_coll_works()
        self.pump(4)
        w._remove_works_from_collection(["T0001"])
        self.pump(6)
        self.assertEqual(self.coll()["work_ids"], [])
        self.assertIn("T0001", w._workspace)
        self.assertFalse(w.btn_workspace.isChecked())   # 不自动切到工作区面板
        self.assertFalse(any(t.startswith("已移除") for t in self.left_tops()), self.left_tops())

    def test_search_results_render_in_left_tree(self):
        w = self.win
        w.search.setText("T0095")
        self.pump(14)
        self.assertTrue(any(t.startswith("搜索结果") for t in self.left_tops()), self.left_tops())
        self.assertTrue(w._search_results)
        self.assertEqual(w._workspace, [])              # 搜索不进工作区
        w._clear_search()
        self.pump(8)
        self.assertFalse(any(t.startswith("搜索结果") for t in self.left_tops()), self.left_tops())

    def test_double_click_adds_to_right_not_workspace(self):
        w = self.win
        w.nav_combo.setCurrentText("刊本")
        self.pump(12)
        edition = w.tree.topLevelItem(0)
        vol = next((edition.child(i) for i in range(edition.childCount())
                    if edition.child(i).childCount()), None)
        self.assertIsNotNone(vol)
        leaf = vol.child(0)
        wid = (leaf.data(0, Qt.UserRole) or {}).get("key")
        w._on_tree_double_click(leaf, 0)
        self.pump(6)
        self.assertIn(wid, self.coll()["work_ids"])     # 二栏：直接加入右栏
        self.assertEqual(w._workspace, [])

    def test_clear_search_keeps_nav_expansion(self):
        w = self.win
        w.nav_combo.setCurrentText("部类")
        self.pump(10)
        top = w.tree.topLevelItem(0)
        top.setExpanded(True)
        kid = top.child(0)
        kid.setExpanded(True)
        w.search.setText("T0095")
        self.pump(12)
        w._clear_search()
        self.pump(12)
        t0 = w.tree.topLevelItem(0)
        self.assertTrue(t0.isExpanded())
        self.assertTrue(t0.child(0).isExpanded())

    def test_nav_change_returns_to_catalog(self):
        w = self.win
        w.btn_workspace.setChecked(True)
        self.pump(4)
        self.assertFalse(w.tree.isVisibleTo(w))
        w.nav_combo.setCurrentText("刊本")
        self.pump(6)
        self.assertFalse(w.btn_workspace.isChecked())
        self.assertTrue(w.tree.isVisibleTo(w))


if __name__ == "__main__":
    unittest.main()
