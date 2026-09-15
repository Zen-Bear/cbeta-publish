# -*- coding: utf-8 -*-
"""部類树合并：官方 category.json 缺分组时用 bulei.txt 补（实测般若部類缺 01/09）。"""
import unittest
from pathlib import Path

from cbeta_publish.catalog.bulei_parser import (
    parse_bulei, parse_bulei_json, merge_missing_children, BuleiNode,
)

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "mulu" / "category.json"
BT = ROOT / "mulu" / "bulei.txt"


class MergeMissingChildrenTest(unittest.TestCase):
    def _tree(self, spec):
        return BuleiNode(level=1, title=spec[0], raw=spec[0],
                         children=[BuleiNode(level=2, title=t, raw=t) for t in spec[1]])

    def test_insert_missing_in_number_order(self):
        pri = self._tree(("03 般若部類 T05-08", ["02 乙", "04 丁"]))
        fb = self._tree(("03 般若部類 T05-08", ["01 甲", "02 乙", "03 丙", "04 丁"]))
        n = merge_missing_children([pri], [fb])
        self.assertEqual(n, 2)
        self.assertEqual([c.title for c in pri.children], ["01 甲", "02 乙", "03 丙", "04 丁"])
        self.assertTrue(all(c.level == 2 for c in pri.children))

    def test_no_change_when_complete(self):
        pri = self._tree(("03 般若部類 T05-08", ["01 甲", "02 乙"]))
        fb = self._tree(("03 般若部類 T05-08", ["01 甲", "02 乙"]))
        self.assertEqual(merge_missing_children([pri], [fb]), 0)

    def test_real_data_restores_banruo_groups(self):
        if not CAT.exists() or not BT.exists():
            self.skipTest("缺 mulu 数据")
        pri = parse_bulei_json(CAT)
        fb = parse_bulei(BT)

        def nums(nodes, needle="般若部類"):
            top = next(t for t in nodes if needle in t.title)
            return [c.title.split()[0] for c in top.children]

        before = nums(pri)
        self.assertNotIn("01", before)      # 官方源确实缺
        added = merge_missing_children(pri, fb)
        after = nums(pri)
        self.assertIn("01", after)
        self.assertIn("09", after)
        self.assertEqual(after, ["%02d" % i for i in range(1, 14)])
        self.assertGreaterEqual(added, 2)
        # 补入的 01 带下了子树
        top = next(t for t in pri if "般若部類" in t.title)
        self.assertTrue(top.children[0].children)


if __name__ == "__main__":
    unittest.main()
