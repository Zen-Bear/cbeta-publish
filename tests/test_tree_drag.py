# -*- coding: utf-8 -*-
"""目录树拖拽载荷：选中节点（含子孙）应展开为作品 id 列表（text/plain）。

回归：QTreeWidget 默认 mimeData 只有内部模型格式、无 text/plain，
导致刊本/册等父节点拖到中栏/右栏时拿不到书。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402

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
    col = tmp / "collections" / "custom"
    col.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    (col / "t.json").write_text(json.dumps(
        {"id": "t", "name": "t", "category": "custom", "tags": [], "work_ids": []},
        ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class TreeDragPayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _ids_from(self, item):
        md = self.win.tree.mimeData([item])
        txt = md.text()
        return [x for x in txt.splitlines() if x], txt

    def test_vol_leaf_vol_and_edition(self):
        self.win.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        self.assertGreater(self.win.tree.topLevelItemCount(), 0, "未渲染刊本树（缺 mulu/vol.json？）")
        edition = self.win.tree.topLevelItem(0)
        # 找一个有册子节点的刊本（大正藏类）
        vol_node = None
        for i in range(edition.childCount()):
            c = edition.child(i)
            if c.childCount():
                vol_node = c
                break
        self.assertIsNotNone(vol_node, "刊本首个节点无子节点")
        leaf = vol_node.child(0)
        leaf_ids, leaf_txt = self._ids_from(leaf)
        self.assertEqual(len(leaf_ids), 1)
        self.assertEqual(leaf_txt.strip(), leaf_ids[0])
        vol_ids, _ = self._ids_from(vol_node)
        self.assertEqual(len(vol_ids), vol_node.childCount())
        edition_ids, _ = self._ids_from(edition)
        self.assertGreater(len(edition_ids), len(vol_ids))

    def test_dynasty_node_expands(self):
        self.win.nav_combo.setCurrentText("朝代")
        _ensure_app().processEvents()
        if self.win.tree.topLevelItemCount() == 0:
            self.skipTest("缺 mulu/dynasty-works.json")
        node = self.win.tree.topLevelItem(0)
        ids, _ = self._ids_from(node)
        self.assertEqual(len(ids), node.childCount())

    def test_author_node_expands(self):
        self.win.nav_combo.setCurrentText("作者")
        _ensure_app().processEvents()
        self.assertGreater(self.win.tree.topLevelItemCount(), 0)
        node = self.win.tree.topLevelItem(0)
        ids, _ = self._ids_from(node)
        self.assertGreater(len(ids), 0)

    def test_vol_leaf_group_payload(self):
        self.win.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        self.assertGreater(self.win.tree.topLevelItemCount(), 0)
        edition = self.win.tree.topLevelItem(0)
        vol_node = None
        for i in range(edition.childCount()):
            c = edition.child(i)
            if c.childCount():
                vol_node = c
                break
        self.assertIsNotNone(vol_node)
        md = self.win.tree.mimeData([vol_node])
        works, groups = self.win._mime_works_groups(md)
        self.assertEqual(len(works), vol_node.childCount())
        # 册标签应等于该册节点记录的 vol_title
        data = vol_node.data(0, Qt.UserRole)
        if isinstance(data, dict):
            label = data.get("vol_title")
            self.assertTrue(label)
            for w in works:
                self.assertEqual(groups.get(w), label)


if __name__ == "__main__":
    unittest.main()
