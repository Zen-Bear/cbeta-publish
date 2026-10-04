# -*- coding: utf-8 -*-
"""工作编号规范化 + 丛书 JSON id 迁移（读入规范化、保存回写）。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.catalog.work_id import canonical_work, is_work_id
from cbeta_publish.collection.collection_model import (Collection, normalize_collection,
                                                       create_collection, write_index)


class WorkIdTest(unittest.TestCase):
    def test_canonical_keeps_no_case(self):
        self.assertEqual(canonical_work("TXA001"), "TXa001")
        self.assertEqual(canonical_work("txa001"), "TXa001".lower().replace("txa", "TXa"))
        self.assertEqual(canonical_work("T0128A"), "T0128a")
        self.assertEqual(canonical_work("jb005"), "JB005")
        self.assertEqual(canonical_work("T0001"), "T0001")
        # 未命中 catalog：原样返回
        self.assertEqual(canonical_work("ZZ9999"), "ZZ9999")

    def test_is_work_id(self):
        for ok in ("T0349", "A1057", "T0128a", "TXa001", "JB005", "T01n0001"):
            self.assertTrue(is_work_id(ok), ok)
        for bad in ("", "T01", "阿含經", "T01 阿含部"):
            self.assertFalse(is_work_id(bad), bad)


class NormalizeCollectionTest(unittest.TestCase):
    def test_normalize_fields(self):
        d = {
            "work_ids": ["TXA001", "txa001", "T0128A", "T0001"],
            "work_sources": {"TXA001": "xml", "T0128A": "official"},
            "works": [{"id": "TXA001"}, {"id": "T0128A"}],
        }
        out = normalize_collection(d)
        self.assertEqual(out["work_ids"], ["TXa001", "T0128a", "T0001"])
        self.assertEqual(set(out["work_sources"]), {"TXa001", "T0128a"})
        self.assertEqual([w["id"] for w in out["works"]], ["TXa001", "T0128a"])

    def test_normalize_edit_note(self):
        d = {"work_ids": ["T0001"],
             "edit_note": {"file": "E:/n.txt", "enabled": 1}}
        out = normalize_collection(d)
        self.assertEqual(out["edit_note"], {"file": "E:/n.txt", "enabled": True})
        # 缺省无该键则不创建
        self.assertNotIn("edit_note",
                         normalize_collection({"work_ids": ["T0001"]}))

    def test_roundtrip_mixed_case(self):
        c = create_collection("测试", "custom", [], ["TXA001", "T0128A"])
        self.assertEqual(c.work_ids, ["TXa001", "T0128a"])
        # to_dict 落盘后再 load，id 保持不变
        d = c.to_dict()
        self.assertEqual([w["id"] for w in d["works"]], ["TXa001", "T0128a"])
        dir_ = Path(tempfile.mkdtemp())
        try:
            p = dir_ / "custom" / "测试.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(Collection.load(p)["work_ids"], ["TXa001", "T0128a"])
        finally:
            shutil.rmtree(dir_, ignore_errors=True)


class IndexTest(unittest.TestCase):
    def test_write_index(self):
        d1 = Path(tempfile.mkdtemp())
        try:
            cdir = d1 / "collections"
            cdir.mkdir(parents=True)
            c = create_collection("甲", "custom", [], ["TXA001", "T0001"])
            colls = [(cdir / "custom" / "甲.json", c.to_dict())]
            ip = write_index(colls, cdir / "index.json")
            rows = json.loads(ip.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "甲")
            self.assertEqual(rows[0]["work_count"], 2)
            self.assertEqual(rows[0]["category"], "custom")
        finally:
            shutil.rmtree(d1, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
