# -*- coding: utf-8 -*-
"""标签管理：CRUD、层级删除、id 生成。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.collection.tags_manager import TagsManager


class TagsManagerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.tm = TagsManager(self.dir / "tags.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_add_get_rename(self):
        tid = self.tm.add("太虚", description="太虚大师")
        self.assertTrue(tid)
        self.assertEqual(self.tm.get(tid)["name"], "太虚")
        self.assertEqual(self.tm.name_of(tid), "太虚")
        self.tm.update(tid, new_name="太虛", new_desc="改")
        t = self.tm.get(tid)
        self.assertEqual(t["name"], "太虛")
        self.assertEqual(t["description"], "改")

    def test_unique_id(self):
        a = self.tm.add("禅宗")
        b = self.tm.add("禅宗")
        self.assertNotEqual(a, b)

    def test_delete_cascades(self):
        parent = self.tm.add("藏经")
        child = self.tm.add("大正藏", parent=parent)
        self.tm.delete(parent)
        self.assertIsNone(self.tm.get(parent))
        self.assertIsNone(self.tm.get(child))

    def test_persist(self):
        self.tm.add("净土")
        tm2 = TagsManager(self.dir / "tags.json")
        self.assertEqual(len(tm2.all()), 1)
        self.assertEqual(tm2.all()[0]["name"], "净土")

    def test_unknown_name_of(self):
        self.assertEqual(self.tm.name_of("nope"), "nope")


if __name__ == "__main__":
    unittest.main()
