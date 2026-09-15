# -*- coding: utf-8 -*-
"""刊本目录解析（vol.json：刊本→册→经）。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.catalog.vol_service import (
    load_vol, edition_titles, count_works, work_vol_map, work_edition_map, work_file_map,
)

SAMPLE = [
    {"title": "選擇全部", "children": [
        {"title": "大正藏", "children": [
            {"title": "T01 大正藏 T0001-0098", "children": [
                {"key": "T0001", "title": "T0001 長阿含經 (22卷)【後秦 佛陀耶舍共竺佛念譯】"},
                {"key": "T0002", "title": "T0002 七佛經 (1卷)【宋 法天譯】"},
            ]},
            {"title": "T02 大正藏 T0099-0154", "children": [
                {"key": "T0099", "title": "T0099 雜阿含經 (50卷)【劉宋 求那跋陀羅譯】"},
            ]},
        ]},
        {"title": "高麗藏", "children": [
            {"title": "K01 高麗藏 K0001-", "children": [
                {"key": "K0016", "title": "K0016 大乘理趣六波羅蜜多經 (10卷)"},
            ]},
        ]},
        # 第二层直接是经（无册分组）
        {"title": "房山石經", "children": [
            {"key": "F0016", "title": "F0016 大王觀世音經 (1卷)"},
        ]},
    ]},
]


class VolServiceTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "vol.json"
        self.path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_load(self):
        d = load_vol(self.path)
        self.assertEqual([e["edition"] for e in d], ["大正藏", "高麗藏", "房山石經"])
        tai = d[0]
        self.assertEqual([v["title"] for v in tai["vols"]],
                         ["T01 大正藏 T0001-0098", "T02 大正藏 T0099-0154"])
        self.assertEqual(tai["vols"][0]["works"][0][0], "T0001")
        self.assertEqual(len(tai["vols"][0]["works"]), 2)
        self.assertEqual(count_works(tai), 3)
        # 房山石經：第二层直接是经
        fs = d[2]
        self.assertEqual(fs["vols"], [])
        self.assertEqual(fs["works"], [("F0016", "F0016 大王觀世音經 (1卷)")])
        self.assertEqual(count_works(fs), 1)

    def test_edition_titles(self):
        self.assertEqual(edition_titles(self.path), ["大正藏", "高麗藏", "房山石經"])

    def test_missing(self):
        self.assertEqual(load_vol(self.dir / "nope.json"), [])

    def test_work_vol_map(self):
        m = work_vol_map(self.path)
        self.assertEqual(m["T0001"], "T01 大正藏 T0001-0098")
        self.assertEqual(m["T0099"], "T02 大正藏 T0099-0154")
        # 直属经回落到刊本名
        self.assertEqual(m["F0016"], "房山石經")

    def test_work_edition_map(self):
        m = work_edition_map(self.path)
        self.assertEqual(m["T0001"], "大正藏")
        self.assertEqual(m["T0099"], "大正藏")
        self.assertEqual(m["K0016"], "高麗藏")
        self.assertEqual(m["F0016"], "房山石經")

    def test_work_file_map(self):
        m = work_file_map(self.path)
        self.assertEqual(m["T0001"], {"edition": "大正藏", "seq": 1, "label": "T01 大正藏 T0001-0098"})
        self.assertEqual(m["T0002"]["seq"], 1)
        self.assertEqual(m["T0099"]["seq"], 2)
        # 直属经取书名（去 work 号与括号）
        self.assertEqual(m["F0016"]["label"], "大王觀世音經")
        self.assertEqual(m["F0016"]["edition"], "房山石經")


if __name__ == "__main__":
    unittest.main()
