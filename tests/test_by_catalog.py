# -*- coding: utf-8 -*-
"""按目录（部类）分册：catalog_path 路径/命名/序 + _group_works catalog 模式 + 合并弹框。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.catalog import catalog_path as cp  # noqa: E402
from cbeta_publish.catalog.bulei_parser import parse_bulei  # noqa: E402
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
    cfg["mulu_dir"] = str(ROOT / "mulu")           # 用真实目录树
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class CatalogPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roots = parse_bulei(ROOT / "mulu" / "bulei.txt")
        cls.bm = cp.build_bulei_map(cls.roots)

    def test_depth_and_naming(self):
        r1 = cp.resolve("T0002", "bulei", 1, bulei_map=self.bm)
        r2 = cp.resolve("T0002", "bulei", 2, bulei_map=self.bm)
        self.assertEqual(r1["label"], "01 阿含部類")
        self.assertEqual(r2["label"], "01 阿含部類 / 長阿含經")
        self.assertEqual(r2["stem"], "01 阿含部類_長阿含經")   # 下划线连接
        self.assertFalse(r2["unclassified"])

    def test_order_is_tree_order(self):
        # T0001（長阿含經）在 T0026（中阿含經）之前
        a = cp.resolve("T0001", "bulei", 2, bulei_map=self.bm)["order"]
        b = cp.resolve("T0026", "bulei", 2, bulei_map=self.bm)["order"]
        self.assertLess(a, b)

    def test_unclassified(self):
        r = cp.resolve("ZZ9999", "bulei", 2, bulei_map=self.bm)
        self.assertEqual(r["label"], "未歸類")
        self.assertTrue(r["unclassified"])
        self.assertEqual(r["order"], (10 ** 6,))

    def test_clean_seg_strips_ids(self):
        self.assertEqual(cp._clean_bulei_seg("T0001-25 長阿含經 etc. T01"), "長阿含經")
        self.assertEqual(cp._clean_bulei_seg("01 阿含部類 T01-02,25,33 etc."), "01 阿含部類")
        # 全角 ／ 保留；T/K/X/G 经号与 etc. 去掉
        self.assertEqual(cp._clean_bulei_seg("T30a, K41 中觀部／疏 T42,85, X46, G151"),
                         "中觀部／疏")
        self.assertEqual(cp._clean_bulei_seg("T1564-67, K1482 中論 etc.／疏 T42"),
                         "中論／疏")
        # 经号后的裸卷号列表（X46,54 / T42,85）也要去掉
        self.assertEqual(cp._clean_bulei_seg("T45, X46,54 三論宗"), "三論宗")
        # 作者等正文（含 】）保留，不被截断
        self.assertEqual(cp._clean_bulei_seg("T2034 二諦義 (3卷)【隋 吉藏撰】"),
                         "二諦義 (3卷)【隋 吉藏撰】")


class CatalogGroupingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_group_works_catalog(self):
        self.win.config.setdefault("merge", {})["mode"] = "catalog"
        groups = self.win._group_works(
            {}, ["a", "b"], ["t1", "t2"], ["T0002", "T0001"])
        self.assertEqual(len(groups), 1)                       # 同属長阿含經
        self.assertEqual(groups[0]["label"], "01 阿含部類 / 長阿含經")
        self.assertEqual(groups[0]["stem"], "01 阿含部類_長阿含經")

    def test_group_works_catalog_depth1(self):
        self.win.config.setdefault("merge", {})["mode"] = "catalog"
        groups = self.win._group_works({}, ["a", "b"], ["t1", "t2"],
                                        ["T0001", "T0026"], mode="catalog", depth=1)
        self.assertEqual(groups[0]["label"], "01 阿含部類")
        self.assertEqual(len(groups), 1)

    def test_merge_preview(self):
        rows = self.win._merge_preview(["T0001", "T0026"], "catalog", 2)
        self.assertTrue(any("01 阿含部類" in r[0] for r in rows))
        self.assertTrue(all(r[1] >= 1 for r in rows))

    def test_merge_mode_helpers(self):
        self.win.config.setdefault("merge", {})["mode"] = "ask"
        self.assertEqual(self.win._merge_mode(), "ask")
        # 旧配置：无 mode、by_volume=true → volume
        self.win.config["merge"] = {"by_volume": True}
        self.assertEqual(self.win._merge_mode(), "volume")
        self.win.config["merge"] = {"mode": "catalog", "depth": 9}
        self.assertEqual(self.win._merge_depth(), 5)           # clamp 1..5


    def test_merge_ask_dialog_reject_aborts(self):
        # 「合并时选择」→ 弹框；取消则中止（并覆盖 QDialog.Accepted 判定）
        import cbeta_publish.gui.merge_dialog as md
        win = self.win
        col = Path(win.config["collections_dir"]) / "custom" / "ask.json"
        col.write_text(json.dumps({"id": "ask", "name": "ask", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("ask.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        win.config.setdefault("merge", {})["mode"] = "ask"

        class _D:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return 0                     # != QDialog.Accepted

            def chosen(self):
                return ("none", 2)

        real = md.MergeDialog
        md.MergeDialog = _D
        try:
            win._merge()
        finally:
            md.MergeDialog = real
            col.unlink(missing_ok=True)
        self.assertIn("未选择分册模式", win.detail.text())


class MergeDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_chosen_and_preview(self):
        from cbeta_publish.gui.merge_dialog import MergeDialog
        rows = [("01 阿含部類 / 長阿含經", 2, "01 阿含部類_長阿含經.pdf / .epub")]
        dlg = MergeDialog(None, default_mode="catalog", default_depth=2,
                          preview=lambda m, d: rows)
        try:
            self.assertTrue(dlg.rb_catalog.isChecked())
            self.assertEqual(dlg.chosen(), ("catalog", 2))
            self.assertIn("01 阿含部類", dlg.lst.item(0).text())
            dlg.rb_none.setChecked(True)
            self.assertFalse(dlg.sp_depth.isEnabled())
            self.assertEqual(dlg.chosen(), ("none", 2))
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
