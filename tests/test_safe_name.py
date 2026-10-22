# -*- coding: utf-8 -*-
"""文件名清洗：非法字符/路径穿越/空名；显示名不受影响。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.collection.collection_model import Collection
from cbeta_publish.utils.safe_name import safe_name


class SafeNameTest(unittest.TestCase):
    def test_illegal_and_traversal(self):
        self.assertEqual(safe_name("a/b"), "a_b")
        self.assertEqual(safe_name("a:b"), "a_b")
        self.assertEqual(safe_name("a\\b"), "a_b")
        self.assertEqual(safe_name("T01/卷一"), "T01_卷一")
        self.assertEqual(safe_name("阿含/地藏"), "阿含_地藏")

    def test_trailing_dots_spaces(self):
        self.assertEqual(safe_name("名字."), "名字")
        self.assertEqual(safe_name("名字 "), "名字")

    def test_dangerous_names_fall_back(self):
        for bad in ("..", ".", "...", "  ", "\n"):
            self.assertEqual(safe_name(bad), "未分册", bad)
        self.assertEqual(safe_name("..", "备用"), "备用")

    def test_collection_save_uses_safe_name_keeps_display(self):
        d = Path(tempfile.mkdtemp(prefix="collsafe-"))
        try:
            c = Collection("cid", "../越界", "custom", works=["T0001"])
            p = c.save(d / "collections")
            self.assertEqual(p.parent, d / "collections" / "custom")
            self.assertEqual(p.name, "越界.json")
            self.assertEqual(c.name, "../越界")   # 显示名保持原文
        finally:
            shutil.rmtree(d, ignore_errors=True)


class MergeDirNameTest(unittest.TestCase):
    def test_degenerate_names_get_unique_fallback(self):
        from cbeta_publish.gui.main_window import MainWindow
        self.assertEqual(MainWindow._merge_dir_name({"name": "阿含"}, Path("a.json")),
                         "阿含")
        self.assertEqual(MainWindow._merge_dir_name({"name": ".."}, Path("a/越界.json")),
                         "未分册_越界")
        self.assertNotEqual(
            MainWindow._merge_dir_name({"name": "..."}, Path("a/另一部.json")),
            MainWindow._merge_dir_name({"name": ".."}, Path("a/越界.json")))


if __name__ == "__main__":
    unittest.main()
