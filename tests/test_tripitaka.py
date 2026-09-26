# -*- coding: utf-8 -*-
"""三藏映射覆盖测试：确保 bulei 顶层部類全部落入 经/律/论/藏外。
若 CBETA 新增部類未命中映射，本测试失败以提醒补表。"""
import unittest
from pathlib import Path

from cbeta_publish.catalog.bulei_parser import parse_bulei
from cbeta_publish.catalog.tripitaka_service import (
    pitaka_of, group_by_pitaka, PITAKA_ORDER, pitaka_of_work)

MULU = Path(__file__).resolve().parents[1] / "mulu" / "bulei.txt"


class TripitakaCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roots = parse_bulei(MULU)

    def test_has_top_nodes(self):
        self.assertGreater(len(self.roots), 0)

    def test_all_mapped(self):
        """所有顶层部類必须映射到已知三藏，不得落入 '其他'。"""
        unmapped = [r.title for r in self.roots if pitaka_of(r.title) == "其他"]
        self.assertEqual(unmapped, [], f"未映射部類（请补 PITAKA_KEYWORDS/PITAKA_BY_NUM）: {unmapped}")

    def test_groups_nonempty(self):
        groups = dict(group_by_pitaka(self.roots))
        for p in PITAKA_ORDER:
            self.assertIn(p, groups, f"三藏分组缺失: {p}")

    def test_counts(self):
        groups = {k: len(v) for k, v in group_by_pitaka(self.roots)}
        # CBETA 23 部類：经10 / 律1 / 论4 / 藏外8
        self.assertEqual(groups.get("經"), 10)
        self.assertEqual(groups.get("律"), 1)
        self.assertEqual(groups.get("論"), 4)
        self.assertEqual(groups.get("藏外"), 8)


class PitakaOfWorkTest(unittest.TestCase):
    """经号查三藏（说明页统计用）：T0001–1420經/T1421–1504律/
    T1505–1692論；T1693＋及非 T 经号一律其他。"""

    def test_boundaries(self):
        cases = {"T0001": "經", "T1420": "經", "T1421": "律", "T1504": "律",
                 "T1505": "論", "T1692": "論", "T1693": "其他",
                 "T0366": "經", "T2760": "其他", "T2920": "其他"}
        for wid, want in cases.items():
            self.assertEqual(pitaka_of_work(wid), want, wid)

    def test_non_t_and_malformed(self):
        for wid in ("X0420", "JA111", "B0024", "N01", "ZW01", "ZZ9999",
                    "", None, "ABC", "T"):
            self.assertEqual(pitaka_of_work(wid), "其他", repr(wid))
        # 后缀字母忽略、前导零与小写兼容
        self.assertEqual(pitaka_of_work("T0099a"), "經")
        self.assertEqual(pitaka_of_work("t0366"), "經")


if __name__ == "__main__":
    unittest.main()
