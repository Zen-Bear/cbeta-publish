# -*- coding: utf-8 -*-
"""按册分册：work_groups 规范化 + 分组/文件名安全化。

- collection_model：work_groups 键 canonical 化、to_dict 输出。
- main_window._group_works：按册标签分组（首见顺序、空→未分册）。
- main_window._safe_name：文件名非法字符替换。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.collection.collection_model import (  # noqa: E402
    Collection, create_collection, normalize_collection,
)
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
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(tmp / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class WorkGroupsModelTest(unittest.TestCase):
    def test_collection_to_dict_has_groups(self):
        c = Collection("cid", "n", "custom", [], ["T0001"], work_groups={"T0001": "第一册"})
        d = c.to_dict()
        self.assertEqual(d["work_groups"], {"T0001": "第一册"})

    def test_normalize_canonicalizes_group_keys(self):
        d = {"work_ids": [], "work_groups": {"T0128A": "x", "txa001": "y"}}
        out = normalize_collection(d)
        self.assertEqual(set(out["work_groups"].keys()), {"T0128a", "TXa001"})
        self.assertEqual(out["work_groups"]["T0128a"], "x")

    def test_create_collection_passes_groups(self):
        c = create_collection("n", "custom", [], ["T0001"], work_groups={"T0001": "甲"})
        self.assertEqual(c.work_groups, {"T0001": "甲"})


class GroupWorksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _set_mode(self, mode, depth=2):
        self.win.config.setdefault("merge", {}).update({"mode": mode, "depth": depth})

    def test_single_group_when_disabled(self):
        self._set_mode("none")
        d = {"work_groups": {"T0001": "甲"}}
        groups = self.win._group_works(d, ["a", "b"], ["ta", "tb"], ["T0001", "T0002"])
        self.assertEqual(len(groups), 1)
        self.assertIsNone(groups[0]["label"])
        self.assertIsNone(groups[0]["stem"])

    def test_group_by_label_order(self):
        self._set_mode("volume")
        d = {"work_groups": {"T0001": "乙册", "T0002": "甲册"}}
        groups = self.win._group_works(
            d, ["f1", "f2", "f3"], ["t1", "t2", "t3"], ["T0001", "T0002", "T0003"])
        self.assertEqual([g["label"] for g in groups], ["乙册", "甲册", "未分册"])
        self.assertEqual(groups[0]["works"], ["T0001"])
        self.assertEqual(groups[1]["works"], ["T0002"])
        self.assertEqual(groups[2]["works"], ["T0003"])

    def test_auto_file_map_with_edition_and_seq(self):
        self._set_mode("volume")
        self.win._wvol_cache = {
            "T0001": {"edition": "太虛大師全書", "seq": 2, "label": "法藏"},
            "T0002": {"edition": "太虛大師全書", "seq": 3, "label": "制藏"},
        }
        d = {}
        groups = self.win._group_works(
            d, ["a", "b", "c"], ["ta", "tb", "tc"], ["T0002", "T0001", "T9999"])
        # 按 seq 排序：法藏(2) 在 制藏(3) 前；未知在最后（label 为完整路径）
        self.assertEqual([g["label"] for g in groups],
                         ["太虛大師全書 / 法藏", "太虛大師全書 / 制藏", "未分册"])
        self.assertEqual(groups[0]["stem"], "太虛大師全書_法藏")
        self.assertEqual(groups[1]["stem"], "太虛大師全書_制藏")
        self.assertEqual(groups[2]["stem"], "未分册")
        self.win._wvol_cache = None

    def test_volume_depth1_is_one_file(self):
        # depth=1：只按刊本名（太虚=1 个文件）
        self._set_mode("volume", depth=1)
        self.win._wvol_cache = {
            "T0001": {"edition": "太虛大師全書", "seq": 2, "label": "法藏"},
            "TXa001": {"edition": "太虛大師全書", "seq": 1, "label": "編纂說明"},
        }
        groups = self.win._group_works({}, ["a", "b"], ["t1", "t2"], ["T0001", "TXa001"])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["stem"], "太虛大師全書")
        self.assertEqual(groups[0]["works"], ["T0001", "TXa001"])
        self.win._wvol_cache = None

    def test_manual_overrides_auto(self):
        self._set_mode("volume")
        self.win._wvol_cache = {"T0001": {"edition": "X", "seq": 1, "label": "自动册"}}
        d = {"work_groups": {"T0001": "手动册"}}
        groups = self.win._group_works(d, ["a", "b"], ["ta", "tb"], ["T0001", "T0002"])
        self.assertEqual([g["label"] for g in groups], ["手动册", "未分册"])
        self.assertEqual(groups[0]["stem"], "手动册")
        self.win._wvol_cache = None

    def test_manual_without_auto_keeps_label(self):
        self._set_mode("volume")
        self.win._wvol_cache = {}
        d = {"work_groups": {"T0001": "手动册"}}
        groups = self.win._group_works(d, ["a"], ["ta"], ["T0001"])
        self.assertEqual(groups[0]["label"], "手动册")
        self.assertEqual(groups[0]["stem"], "手动册")
        self.win._wvol_cache = None

    def test_manual_edition_falls_back_to_auto(self):
        # 老拖拽回退值（直属经记成刊本名）让位给自动书名
        self._set_mode("volume")
        self.win._wvol_cache = {"TXa001": {"edition": "太虛大師全書", "seq": 1, "label": "編纂說明"}}
        d = {"work_groups": {"TXa001": "太虛大師全書"}}
        groups = self.win._group_works(d, ["a"], ["ta"], ["TXa001"])
        self.assertEqual(groups[0]["label"], "太虛大師全書 / 編纂說明")
        self.assertEqual(groups[0]["stem"], "太虛大師全書_編纂說明")
        self.win._wvol_cache = None

    def test_same_label_still_grouped(self):
        self._set_mode("volume")
        d = {"work_groups": {"T0001": "甲册", "T0002": "甲册"}}
        groups = self.win._group_works(d, ["a", "b"], ["ta", "tb"], ["T0001", "T0002"])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["label"], "甲册")
        self.assertEqual(groups[0]["works"], ["T0001", "T0002"])

    def test_safe_name(self):
        self.assertEqual(self.win._safe_name("第1册/上"), "第1册_上")
        self.assertEqual(self.win._safe_name('a:b*c?"d'), "a_b_c_d")
        self.assertEqual(self.win._safe_name("   "), "未分册")
        self.assertEqual(self.win._safe_name(None), "未分册")


class ProgressLinkTest(unittest.TestCase):
    """合并进度日志：file:// 链接必须走系统默认程序打开，
    不能让 QTextBrowser 当内部文档加载（报 No document 且打不开，中文路径亦然）。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_file_links_open_externally(self):
        import PySide6.QtGui as _gui
        from PySide6.QtWidgets import QTextBrowser
        from PySide6.QtCore import QUrl
        dlg, update, st = self.win._make_progress("合成", 10)
        try:
            logs = dlg.findChildren(QTextBrowser)
            self.assertTrue(logs)
            log = logs[0]
            self.assertFalse(log.openLinks())
            opened = []

            class _FakeDS:
                @staticmethod
                def openUrl(url):
                    opened.append(url.toString())
                    return True

            orig = _gui.QDesktopServices
            _gui.QDesktopServices = _FakeDS
            try:
                log.anchorClicked.emit(QUrl("file:///C:/x/%E4%B8%AD.pdf"))
            finally:
                _gui.QDesktopServices = orig
            self.assertEqual(len(opened), 1)
            self.assertTrue(opened[0].startswith("file:///"))
            st["finish"](['  → 已生成 <a href="file:///C:/x/a.pdf">a.pdf</a>'])
        finally:
            dlg.close()

    def test_plain_lines_not_stained_blue(self):
        # 链接行的蓝/锚点格式不得泄漏给后续纯文本行（源文件名保持默认色）
        from PySide6.QtWidgets import QTextBrowser
        dlg, update, st = self.win._make_progress("合成", 10)
        try:
            log = dlg.findChildren(QTextBrowser)[0]
            update(1, '  → 已生成 <a href="file:///C:/x/a.pdf">a.pdf</a>', True)
            update(2, "TX0015 太虛大師全書．第十五編　時論（TX0015.pdf）")
            html = log.toHtml()
            self.assertIn("TX0015.pdf", html)
            self.assertNotIn("TX0015.pdf</a>", html)
        finally:
            dlg.close()


if __name__ == "__main__":
    unittest.main()
