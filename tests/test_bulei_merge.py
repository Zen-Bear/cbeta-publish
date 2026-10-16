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
        added = merge_missing_children(pri, fb)
        after = nums(pri)
        # 官方源可能已补齐（2026-10-15「立即检查更新」后 category.json 已含 01）：
        # 合并幂等——合并后恒为 01..13 全序；只有合并前确实缺时才要求"补入带子树"。
        self.assertEqual(after, ["%02d" % i for i in range(1, 14)])
        if "01" not in before:
            self.assertGreaterEqual(added, 2)
            # 补入的 01 带下了子树
            top = next(t for t in pri if "般若部類" in t.title)
            self.assertTrue(top.children[0].children)

    def test_deep_leaf_graft(self):
        # 深层叶子缺失：主源把 T0220c 当无子节点叶子，回退有卷区间叶 → 整棵接上
        pri = BuleiNode(level=1, title="03 般若部類", raw="03 般若部類", children=[
            BuleiNode(level=2, title="02 中品般若", raw="02 中品般若", children=[
                BuleiNode(level=3, title="T0220c,21-23 中品般若經 T07-08",
                          raw="T0220c,21-23 中品般若經 T07-08"),
            ]),
        ])
        fb = BuleiNode(level=1, title="03 般若部類", raw="03 般若部類", children=[
            BuleiNode(level=2, title="02 中品般若", raw="02 中品般若", children=[
                BuleiNode(level=3, title="T0220c,21-23 中品般若經 T07-08",
                          raw="T0220c,21-23 中品般若經 T07-08", children=[
                              BuleiNode(level=4, title="T0220_401..537 T0220 X",
                                        raw="T0220_401..537 T0220 X"),
                          ]),
            ]),
        ])
        a_before = pri.children[0].children[0]
        n = merge_missing_children([pri], [fb])
        self.assertEqual(n, 1)
        # 主源已有节点原样保留（同一对象），只多了子节点
        self.assertIs(pri.children[0].children[0], a_before)
        self.assertEqual([c.title for c in a_before.children],
                         ["T0220_401..537 T0220 X"])
        self.assertEqual(a_before.children[0].level, 4)
        # 幂等：再合并一次 +0
        self.assertEqual(merge_missing_children([pri], [fb]), 0)

    def test_graft_ordered_by_work(self):
        # 深层无序号 graft 按经号定序：T0220_* 排到 T0221 前（不盲追加尾部）
        def grp(kids):
            return BuleiNode(level=2, title="G 组", raw="G 组", children=[
                BuleiNode(level=3, title=t, raw=t) for t in kids])
        pri = BuleiNode(level=1, title="Top", raw="Top",
                        children=[grp(["T0221 X", "T0223 Y"])])
        fb = BuleiNode(level=1, title="Top", raw="Top",
                       children=[grp(["T0221 X", "T0223 Y",
                                      "T0220_401..537 T0220 Z"])])
        n = merge_missing_children([pri], [fb])
        self.assertEqual(n, 1)
        self.assertEqual([c.title for c in pri.children[0].children],
                         ["T0220_401..537 T0220 Z", "T0221 X", "T0223 Y"])

    def test_real_data_restores_volume_leaves(self):
        # 真数据回归：18 组卷区间叶在合并后必须全部出现；
        # `N70_1cont` 之类帮助路径不是卷（词界收紧后不算），文档链接永不 graft。
        import re
        if not CAT.exists() or not BT.exists():
            self.skipTest("缺 mulu 数据")
        pri = parse_bulei_json(CAT)
        fb = parse_bulei(BT)
        merge_missing_children(pri, fb)
        pat = re.compile(r"([A-Z]{1,2}\d+[A-Za-z]?)_(\d{1,4})(?:\.\.(\d{1,4}))?(?![0-9A-Za-z])")
        got = set()
        doc_leaves = []

        def walk(ns):
            for x in ns or []:
                if not x.children:
                    for m in pat.finditer(x.title or ""):
                        got.add((m.group(1), int(m.group(2)),
                                 int(m.group(3) or m.group(2))))
                    if (x.title or "").strip().startswith("help/"):
                        doc_leaves.append(x.title)
                else:
                    walk(x.children)
        walk(pri)
        want = ([("T0220", 401, 537), ("T0220", 538, 565), ("T0220", 566, 573),
                 ("T0220", 574, 575), ("T0220", 576, 576), ("T0220", 577, 577),
                 ("T0220", 578, 578)]
                + [("JB277", a, b) for a, b in
                   [(12, 12), (13, 13), (14, 14), (15, 15), (16, 16),
                    (17, 18), (19, 21), (22, 22), (23, 23), (25, 25)]]
                + [("T0310", 17, 18)])
        self.assertEqual(len(want), 18)
        for w in want:
            self.assertIn(w, got, w)
        self.assertEqual(doc_leaves, [])
        # 真数据顺序：T0220c 下的卷叶按经号排在 T0221 前
        def find(ns, pred):
            for x in ns or []:
                if pred(x.title):
                    return x
                r = find(x.children, pred)
                if r is not None:
                    return r
            return None
        t0220c = find(pri, lambda t: (t or "").startswith("T0220c,"))
        self.assertIsNotNone(t0220c)
        kids = [c.title for c in t0220c.children]
        i401 = next(i for i, t in enumerate(kids) if "T0220_401" in t)
        i221 = next(i for i, t in enumerate(kids) if t.startswith("T0221"))
        self.assertLess(i401, i221)


if __name__ == "__main__":
    unittest.main()
