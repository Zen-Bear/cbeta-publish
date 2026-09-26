# -*- coding: utf-8 -*-
"""作者服务：同 id 多节点作品收齐（别名分立不断档）。"""
import unittest
from pathlib import Path

from cbeta_publish.creators.creator_service import CreatorService

ROOT = Path(__file__).resolve().parents[1]


class CreatorWorksOfTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cs = CreatorService(ROOT / "mulu" / "all-creators-with-alias.json",
                                ROOT / "mulu" / "creators-by-strokes-with-works.json")

    def test_works_of_collects_all_same_id_nodes(self):
        # A001019 窺基挂在 窺基/釋窺基/慈恩法師/大乘 四个节点下：
        # 旧逻辑首命中即停只返回 X0352 一部
        keys = [w.get("key") for w in self.cs.works_of("A001019")]
        self.assertGreater(len(keys), 1, keys)
        for k in ("T1695", "D8888", "X0352", "L1629"):
            self.assertIn(k, keys, keys)
        self.assertEqual(len(keys), len(set(keys)))  # 去重

    def test_works_of_unknown_id_empty(self):
        self.assertEqual(self.cs.works_of("NO_SUCH_ID"), [])


if __name__ == "__main__":
    unittest.main()
