# -*- coding: utf-8 -*-
"""手工分册：丛书 JSON `manual_volumes` 模型 / 规范化；右栏两级树（第N册 · 副标题 / 未分组）；
右键操作（新建/移入/设副标题/上下移/删除）；分组下拉视图；合并「按手工分册」。"""
import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

from cbeta_publish.collection.collection_model import normalize_collection, create_collection  # noqa: E402
from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window(work_ids=None):
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "collections" / "custom").mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    ids = work_ids if work_ids is not None else ["T0001", "T0002", "T0003"]
    (tmp / "collections" / "custom" / "手.json").write_text(json.dumps({
        "id": "m", "name": "手", "category": "custom", "tags": [],
        "work_ids": ids}, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    win = MainWindow(cfg)
    for i in range(win.coll_combo.count()):
        if str(win.coll_combo.itemData(i)).endswith("手.json"):
            win.coll_combo.setCurrentIndex(i)
            break
    _ensure_app().processEvents()
    return win, tmp


class ModelTest(unittest.TestCase):
    def test_normalize_canonicalizes_prunes_dedupes(self):
        d = {
            "work_ids": ["T0001", "T0002", "T0003"],
            "manual_volumes": [
                {"title": "甲", "work_ids": ["t0001", "T0003", "TX999"]},  # 小写归一 + 脏 id 剔
                {"title": "", "work_ids": ["T0001", "T0002"]},             # 跨卷去重（T0001）
                {"title": "空", "work_ids": []},                           # 空卷保留
            ],
        }
        out = normalize_collection(d)
        self.assertEqual(out["manual_volumes"][0]["work_ids"], ["T0001", "T0003"])
        self.assertEqual(out["manual_volumes"][1]["work_ids"], ["T0002"])
        self.assertEqual(out["manual_volumes"][2], {"title": "空", "work_ids": []})

    def test_collection_roundtrip(self):
        c = create_collection("手", "custom", ["custom"], ["T0001"],
                              manual_volumes=[{"title": "x", "work_ids": ["T0001"]}])
        d = c.to_dict()
        self.assertEqual(d["manual_volumes"], [{"title": "x", "work_ids": ["T0001"]}])


class ViewComboTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _d(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def test_combo_items(self):
        vals = [self.win.coll_view_combo.itemData(i)
                for i in range(self.win.coll_view_combo.count())]
        self.assertEqual(vals, ["flat", "volume", "catalog", "manual"])

    def test_combo_left_of_remove_and_no_label(self):
        # 下拉框移到「移除」左边（同一按钮行）；不再有「分组:」标签
        win = self.win
        lay = win.btn_remove.parentWidget().layout()
        items = [lay.itemAt(i).widget() for i in range(lay.count())]
        self.assertIn(win.coll_view_combo, items)
        self.assertLess(items.index(win.coll_view_combo), items.index(win.btn_remove))
        from PySide6.QtWidgets import QLabel
        self.assertFalse([lb for lb in win.findChildren(QLabel) if lb.text() == "分组:"])

    def test_sel_buttons_narrow_combo_wide(self):
        # 全选/不选缩窄（固定宽）；显示方式下拉放宽（最小宽）
        win = self.win
        self.assertEqual(win.btn_coll_sel_all.minimumWidth(),
                         win.btn_coll_sel_all.maximumWidth())
        self.assertEqual(win.btn_coll_sel_none.minimumWidth(),
                         win.btn_coll_sel_none.maximumWidth())
        self.assertLessEqual(win.btn_coll_sel_all.maximumWidth(), 48)
        self.assertGreaterEqual(win.coll_view_combo.minimumWidth(), 140)

    def test_flat_default_render(self):
        self.win._coll_view.clear()
        self.win._load_coll_works()
        self.assertEqual(self.win._coll_display_mode(), "flat")
        self.assertEqual(len(self.win._coll_group_headers()), 0)
        self.assertEqual(len(self.win._coll_book_items()), 3)

    def test_manual_render_headers_and_ungrouped_last(self):
        self.win._coll_view[str(self.win.coll_combo.currentData())] = "manual"
        self._d()["manual_volumes"] = [
            {"title": "法藏", "work_ids": ["T0001", "T0002"]},
        ]
        self.win._load_coll_works()
        self.win.coll_view_combo.blockSignals(True)
        idx = self.win.coll_view_combo.findData("manual")
        self.win.coll_view_combo.setCurrentIndex(idx)
        self.win.coll_view_combo.blockSignals(False)
        self.win._load_coll_works()
        headers = [h.text(0) for h in self.win._coll_group_headers()]
        self.assertEqual(headers, ["第1册 · 法藏", "未分组"])
        # 未分组在最后
        self.assertTrue(headers[-1].endswith("未分组"))


class ManualOpsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        w = self.win
        w._coll_view.clear()
        d = self._d()
        d["manual_volumes"] = []
        w._load_coll_works()
        _ensure_app().processEvents()

    def _d(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def _headers(self):
        return [h.text(0) for h in self.win._coll_group_headers()]

    def test_new_volume_switches_and_persists(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001", "T0002"])
        self.assertEqual(w._coll_display_mode(), "manual")
        self.assertEqual(self._d()["manual_volumes"][0]["work_ids"], ["T0001", "T0002"])
        self.assertIn(str(w.coll_combo.currentData()), w._changed_colls)
        self.assertEqual(self._headers()[0], "第1册")
        # 落盘 → 读回一致
        path = str(w.coll_combo.currentData())
        self.assertTrue(w._save_one_collection(path))
        on_disk = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["manual_volumes"][0]["work_ids"], ["T0001", "T0002"])

    def test_move_to_and_reindex(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        w._manual_new_volume(self._d(), ["T0002"])
        # 把 T0002 移入第1册
        w._manual_move_to(self._d(), ["T0002"], 0)
        vols = self._d()["manual_volumes"]
        self.assertEqual(vols[0]["work_ids"], ["T0001", "T0002"])
        self.assertEqual(vols[1]["work_ids"], [])
        # work_ids 重排：卷序在前，未分组（T0003）在后
        self.assertEqual(self._d()["work_ids"], ["T0001", "T0002", "T0003"])

    def test_volume_updown_renumber(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        w._manual_new_volume(self._d(), ["T0002"])
        self.assertEqual(self._headers()[:2], ["第1册", "第2册"])
        w._manual_move_volume(self._d(), 0, 1)
        self.assertEqual([v["work_ids"] for v in self._d()["manual_volumes"]],
                         [["T0002"], ["T0001"]])
        self.assertEqual(self._headers()[:2], ["第1册", "第2册"])  # 编号自动重排

    def test_delete_volume_returns_to_ungrouped(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001", "T0002"])
        w._manual_delete_volume(self._d(), 0)
        self.assertEqual(self._d()["manual_volumes"], [])
        self.assertEqual(len(w._coll_group_headers()), 0)   # 无卷 → 平铺
        self.assertEqual(len(w._coll_book_items()), 3)

    def test_set_title(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        with mock.patch("cbeta_publish.gui.main_window.QInputDialog.getText",
                        return_value=("法藏", True)):
            w._manual_set_title(self._d(), 0)
        self.assertEqual(self._d()["manual_volumes"][0]["title"], "法藏")
        self.assertEqual(self._headers()[0], "第1册 · 法藏")

    def test_option_dialog_template_vars(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        base = w._merge_basename({"name": "手"}, {"segments": ["第1册"],
                                                  "label": "第1册", "works": ["T0001"]},
                                 1, template="{coll}.{nn}.{seg}", total=2)
        self.assertEqual(base, "手.1.第1册")   # {nn} 宽度=总文件数位数（2→1 位）

    def test_render_preserves_expanded_state(self):
        # 拖拽/移动重渲染后，已有卷保持原展开状态，不整树合上
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        w._manual_new_volume(self._d(), ["T0002"])
        heads = w._coll_group_headers()
        self.assertGreaterEqual(len(heads), 2)
        heads[0].setExpanded(True)
        heads[1].setExpanded(False)
        w._manual_move_to(self._d(), ["T0002"], 0)   # 触发重渲染
        heads2 = w._coll_group_headers()
        self.assertTrue(heads2[0].isExpanded())      # 第1册仍展开
        self.assertFalse(heads2[1].isExpanded())     # 第2册仍合上

    def test_new_volume_defaults_expanded(self):
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])    # 首个卷：此前无组头 → 默认展开
        self.assertTrue(w._coll_group_headers()[0].isExpanded())


class MergeManualTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_group_works_manual(self):
        w = self.win
        d = {"manual_volumes": [
            {"title": "法藏", "work_ids": ["T0001", "T0002"]},
            {"title": "", "work_ids": ["T0003"]},
        ]}
        works = ["T0001", "T0002", "T0003"]
        groups = w._group_works(d, works, works, works, mode="manual", depth=2)
        labels = [g["label"] for g in groups]
        self.assertEqual(labels, ["第1册 · 法藏", "第2册"])
        self.assertEqual(groups[0]["works"], ["T0001", "T0002"])
        self.assertEqual(groups[1]["works"], ["T0003"])

    def test_group_works_manual_ungrouped_and_fallback(self):
        w = self.win
        d = {"manual_volumes": [{"title": "", "work_ids": ["T0001"]}]}
        works = ["T0001", "T0002"]
        groups = w._group_works(d, works, works, works, mode="manual", depth=2)
        self.assertEqual([g["label"] for g in groups], ["第1册", "未分组"])
        self.assertEqual(groups[1]["works"], ["T0002"])
        # 无卷 → 回退不分册（单组 label None）
        g2 = w._group_works({}, works, works, works, mode="manual", depth=2)
        self.assertEqual(len(g2), 1)
        self.assertIsNone(g2[0]["label"])

    def test_merge_mode_accepts_manual(self):
        w = self.win
        w.config.setdefault("merge", {})["mode"] = "manual"
        self.assertEqual(w._merge_mode(), "manual")


class BuleiOriginTest(unittest.TestCase):
    """同书多部类：从部类树拖入时记录来源部类路径，分组优先用它（不再首个命中抢走）。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window(["T0001"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _d(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def test_item_payload_carries_bulei_path(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QTreeWidgetItem
        w = self.win
        top = QTreeWidgetItem(["16 淨土部類 T12,14 etc."])
        top.setData(0, Qt.UserRole, SimpleNamespace(title="16 淨土部類 T12,14 etc."))
        leaf = QTreeWidgetItem(["T0310 佛說無量壽經"])
        leaf.setData(0, Qt.UserRole, SimpleNamespace(title="T0310 佛說無量壽經"))
        top.addChild(leaf)
        payload = w._item_payload(top)
        self.assertEqual(payload[0][0], "T0310")
        self.assertEqual(payload[0][2], ["16 淨土部類 T12,14 etc.", "T0310 佛說無量壽經"])

    def test_mime_carries_bulei(self):
        from types import SimpleNamespace
        from PySide6.QtWidgets import QTreeWidgetItem
        w = self.win
        top = QTreeWidgetItem(["16 淨土部類"])
        top.setData(0, Qt.UserRole, SimpleNamespace(title="16 淨土部類"))
        leaf = QTreeWidgetItem(["T0310 佛說無量壽經"])
        leaf.setData(0, Qt.UserRole, SimpleNamespace(title="T0310 佛說無量壽經"))
        top.addChild(leaf)
        md = w._tree_mimeData([top])
        works, groups, bulei = w._mime_works_groups(md)
        self.assertIn("T0310", works)
        self.assertEqual(bulei["T0310"], ["16 淨土部類", "T0310 佛說無量壽經"])

    def test_add_persists_bulei_groups(self):
        w = self.win
        d = self._d()
        d["work_ids"] = []
        d["bulei_groups"] = {}
        w._add_to_collection(["T0001"], bulei_groups={"T0001": ["16 淨土部類", "T0001 淨土經"]})
        self.assertEqual(d["bulei_groups"]["T0001"], ["16 淨土部類", "T0001 淨土經"])
        self.assertIn(str(w.coll_combo.currentData()), w._changed_colls)

    def test_group_works_prefers_origin(self):
        w = self.win
        d = {"bulei_groups": {"T0001": ["16 淨土部類", "T0001 淨土經"]}}
        groups = w._group_works(d, ["T0001"], ["T0001"], ["T0001"],
                                mode="catalog", depth=2)
        self.assertEqual(groups[0]["label"], "16 淨土部類 / 淨土經")
        # 无记录 → 走自动解析（首次命中），与人工归属不同
        auto = w._group_works({}, ["T0001"], ["T0001"], ["T0001"],
                              mode="catalog", depth=2)
        self.assertNotEqual(auto[0]["label"], groups[0]["label"])

    def test_remove_cleans_and_stashes(self):
        w = self.win
        d = self._d()
        d["work_ids"] = ["T0001"]
        d["bulei_groups"] = {"T0001": ["16 淨土部類"]}
        w._load_coll_works()
        w._remove_works_from_collection(["T0001"])
        self.assertNotIn("T0001", d.get("bulei_groups") or {})
        self.assertEqual(w._bulei_groups.get("T0001"), ["16 淨土部類"])

    def test_normalize_canonicalizes(self):
        d = {"work_ids": ["T0001"],
             "bulei_groups": {"t0001": ["16 淨土部類"], "TX999": ["x"]}}
        out = normalize_collection(d)
        self.assertEqual(out["bulei_groups"], {"T0001": ["16 淨土部類"]})


class CopyViewToManualTest(unittest.TestCase):
    """只读视图（按刊本册/按部类）右键：把当前自动分册拷贝（覆盖）到手工分册。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window(["T0001", "T0002"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        w = self.win
        w._coll_view.clear()
        w._load_coll_works()
        _ensure_app().processEvents()

    def _d(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def test_copy_all_switches_to_manual(self):
        w = self.win
        d = self._d()
        d["manual_volumes"] = []
        path = str(w.coll_combo.currentData())
        w._coll_view[path] = "catalog"
        w._copy_view_to_manual(d)
        self.assertEqual(w._coll_display_mode(), "manual")
        self.assertTrue(d["manual_volumes"])
        ids = [x for v in d["manual_volumes"] for x in v["work_ids"]]
        self.assertSetEqual(set(ids), {"T0001", "T0002"})
        self.assertIn(path, w._changed_colls)   # 标星号待保存

    def test_copy_single_group(self):
        w = self.win
        d = self._d()
        d["manual_volumes"] = []
        path = str(w.coll_combo.currentData())
        w._coll_view[path] = "catalog"
        groups = w._group_works(d, d["work_ids"], d["work_ids"], d["work_ids"],
                                mode="catalog", depth=w._merge_depth())
        label = groups[0]["label"]
        w._copy_view_to_manual(d, only_label=label)
        self.assertEqual(len(d["manual_volumes"]), 1)
        self.assertEqual(d["manual_volumes"][0]["title"], label)
        self.assertEqual(d["manual_volumes"][0]["work_ids"], list(groups[0]["works"]))

    def test_context_menu_has_copy_in_catalog(self):
        w = self.win
        w._coll_view[str(w.coll_combo.currentData())] = "catalog"
        w._load_coll_works()
        menu = w._build_coll_menu(w.coll_list.viewport().rect().center())
        texts = [ac.text() for ac in menu.actions()]
        self.assertIn("拷贝全部分册覆盖到手工分册", texts)


class WrapProgressTest(unittest.TestCase):
    """弹窗文字折行（不产生左右滚动条）：软换行 + 进度窗日志按窗口宽折行。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window(["T0001"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_soft_break_inserts_zwsp(self):
        self.assertEqual(MainWindow._soft_break("E:\\a/b"), "E:\\\u200ba/\u200bb")

    def test_progress_log_wraps(self):
        from PySide6.QtWidgets import QTextBrowser
        dlg, update, pstate = self.win._make_progress("t", 1)
        try:
            tb = dlg.findChild(QTextBrowser)
            self.assertIsNotNone(tb)
            self.assertEqual(tb.lineWrapMode(), QTextBrowser.WidgetWidth)
        finally:
            dlg.deleteLater()


class InternalDropTest(unittest.TestCase):
    """树内拖拽：书落卷头=入卷；落书=按位置插入。itemAt/落点指标打桩。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    class _Ev:
        def __init__(self):
            self.accepted = False
            self.drop_action = None
        def source(self):
            return self.win.coll_list
        def position(self):
            from PySide6.QtCore import QPointF
            return QPointF(1, 1)
        def setDropAction(self, a):
            self.drop_action = a
        def accept(self):
            self.accepted = True
        def acceptProposedAction(self):
            self.accepted = True
        def ignore(self):
            pass

    def setUp(self):
        w = self.win
        w._coll_view.clear()
        d=self._d(); d["manual_volumes"]=[]
        w._load_coll_works()
        _ensure_app().processEvents()

    def _d(self):
        return self.win._coll_dict(self.win.coll_combo.currentData())

    def test_drop_onto_header_moves_in(self):
        from PySide6.QtWidgets import QAbstractItemView
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        w._manual_new_volume(self._d(), ["T0002"])
        ev = InternalDropTest._Ev()
        ev.win = w
        # 目标=第1册卷头，落点 OnItem → T0002 入第1册
        hdr = w._coll_group_headers()[0]
        with mock.patch.object(w.coll_list, "itemAt", return_value=hdr), \
             mock.patch.object(w.coll_list, "dropIndicatorPosition",
                               return_value=QAbstractItemView.OnItem), \
             mock.patch.object(w, "_coll_dragged_works", return_value=["T0002"]):
            w._coll_internal_drop(ev)
        self.assertTrue(ev.accepted)
        self.assertEqual(self._d()["manual_volumes"][0]["work_ids"], ["T0001", "T0002"])
        self.assertEqual(self._d()["manual_volumes"][1]["work_ids"], [])

    def test_drop_onto_collapsed_header_expands(self):
        # 拖进折叠卷：卷自动展开，被拖的书可见（不再“消失”）
        from PySide6.QtWidgets import QAbstractItemView
        w = self.win
        w._manual_new_volume(self._d(), ["T0001"])
        hdr = w._coll_group_headers()[0]
        hdr.setExpanded(False)
        # 真实拖拽中被拖的书处于选中态：先选中 T0003
        for it in w._coll_book_items():
            if it.data(0, Qt.UserRole) == "T0003":
                it.setSelected(True)
        ev = InternalDropTest._Ev()
        ev.win = w
        with mock.patch.object(w.coll_list, "itemAt", return_value=hdr), \
             mock.patch.object(w.coll_list, "dropIndicatorPosition",
                               return_value=QAbstractItemView.OnItem), \
             mock.patch.object(w, "_coll_dragged_works", return_value=["T0003"]):
            w._coll_internal_drop(ev)
        self.assertTrue(ev.accepted)
        self.assertEqual(self._d()["manual_volumes"][0]["work_ids"], ["T0001", "T0003"])
        heads = w._coll_group_headers()
        self.assertTrue(heads[0].isExpanded())   # 目的地展开
        books = [it.data(0, Qt.UserRole) for it in w._coll_book_items()]
        self.assertIn("T0003", books)
        self.assertTrue(w._coll_book_items()[books.index("T0003")].isSelected())

    def test_flat_reorder_keeps_dragged_visible(self):
        # 平铺拖拽排序：重排后仍可见/选中（不再“消失”）
        from PySide6.QtWidgets import QAbstractItemView
        w = self.win
        w._coll_view[str(w.coll_combo.currentData())] = "flat"
        w._load_coll_works()
        tgt = next(it for it in w._coll_book_items()
                   if it.data(0, Qt.UserRole) == "T0001")
        ev = InternalDropTest._Ev()
        ev.win = w
        with mock.patch.object(w.coll_list, "itemAt", return_value=tgt), \
             mock.patch.object(w.coll_list, "dropIndicatorPosition",
                               return_value=QAbstractItemView.AboveItem), \
             mock.patch.object(w, "_coll_dragged_works", return_value=["T0003"]):
            w._coll_internal_drop(ev)
        self.assertTrue(ev.accepted)
        self.assertEqual(ev.drop_action, Qt.IgnoreAction)   # 拒绝 MoveAction，阻止 Qt 清理被拖行
        self.assertEqual(self._d()["work_ids"][0], "T0003")   # 排到最前
        items = {it.data(0, Qt.UserRole): it for it in w._coll_book_items()}
        self.assertIn("T0003", items)
        self.assertTrue(items["T0003"].isSelected())


    def test_coll_tree_routes_drop_to_owner(self):
        # 书单树用真子类重写拖放虚函数 → 必转交 MainWindow，杜绝 Qt 默认内部移动
        # （默认移动会丢 setItemWidget 的行控件，表现为“拖动的书消失”）
        from cbeta_publish.gui.main_window import _CollTree
        w = self.win
        self.assertIsInstance(w.coll_list, _CollTree)
        self.assertNotIn("dropEvent", w.coll_list.__dict__)   # 不再是实例属性覆写
        calls = []
        real = w._coll_drop
        w._coll_drop = lambda e: calls.append(e)
        try:
            w.coll_list.dropEvent(object())
        finally:
            w._coll_drop = real
        self.assertEqual(len(calls), 1)


    def test_real_drop_route_keeps_row_widgets(self):
        # 经真实虚函数 dropEvent 走一遍：重排后每行仍有行控件（未因 Qt 原生移动变空/消失）
        from PySide6.QtWidgets import QAbstractItemView
        w = self.win
        w._coll_view[str(w.coll_combo.currentData())] = "flat"
        w._load_coll_works()
        tgt = next(it for it in w._coll_book_items()
                   if it.data(0, Qt.UserRole) == "T0001")

        class _Ev:
            def source(self): return w.coll_list
            def position(self):
                from PySide6.QtCore import QPointF
                return QPointF(0, 0)
            def mimeData(self): return None
            def setDropAction(self, a): pass
            def accept(self): pass
            def acceptProposedAction(self): pass
            def ignore(self): pass

        with mock.patch.object(w.coll_list, "itemAt", return_value=tgt), \
             mock.patch.object(w.coll_list, "dropIndicatorPosition",
                               return_value=QAbstractItemView.AboveItem), \
             mock.patch.object(w, "_coll_dragged_works", return_value=["T0003"]):
            w.coll_list.dropEvent(_Ev())
        items = w._coll_book_items()
        self.assertTrue(items)
        for it in items:
            self.assertIsNotNone(w.coll_list.itemWidget(it, 0))
        self.assertIn("T0003", [it.data(0, Qt.UserRole) for it in items])


if __name__ == "__main__":
    unittest.main()
