# -*- coding: utf-8 -*-
"""朝代目录解析测试（含嵌套/单根「選擇全部」下钻）。"""
import json
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.catalog.dynasty_service import (load_dynasty, dynasty_titles,
                                                    work_dynasty_map, dominant_dynasty,
                                                    group_authors_by_dynasty)

SAMPLE = [
    {"title": "選擇全部", "children": [
        {"key": "東漢", "title": "東漢 25 CE ~ 220 CE", "children": [
            {"key": "T0013", "title": "T0013 長阿含十報法經 (2卷)【後漢 安世高譯】"},
            {"key": "T0014", "title": "T0014 人本欲生經 (1卷)【後漢 安世高譯】"},
        ]},
        {"key": "唐", "title": "唐 618 CE ~ 907 CE", "children": [
            {"key": "T0220", "title": "T0220 大般若波羅蜜多經 (600卷)【唐 玄奘譯】"},
        ]},
    ]},
]


class DynastyServiceTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "dynasty-works.json"
        self.path.write_text(json.dumps(SAMPLE, ensure_ascii=False), encoding="utf-8")

    def test_load(self):
        d = load_dynasty(self.path)
        self.assertEqual([t for t, _ in d], ["東漢 25 CE ~ 220 CE", "唐 618 CE ~ 907 CE"])
        self.assertEqual(len(d[0][1]), 2)
        self.assertEqual(d[0][1][0][0], "T0013")

    def test_titles(self):
        self.assertEqual(len(dynasty_titles(self.path)), 2)

    def test_missing_file(self):
        self.assertEqual(load_dynasty(self.dir / "nope.json"), [])


class AuthorDynastyTest(unittest.TestCase):
    def setUp(self):
        roots = load_dynasty(_write(SAMPLE))
        self.dmap = work_dynasty_map(roots)
        self.order = [t for t, _ in roots]

    def test_work_map(self):
        self.assertEqual(self.dmap["T0013"], "東漢 25 CE ~ 220 CE")
        self.assertEqual(self.dmap["T0220"], "唐 618 CE ~ 907 CE")

    def test_dominant(self):
        self.assertEqual(dominant_dynasty(["T0013", "T0014"], self.dmap), "東漢 25 CE ~ 220 CE")
        # 2 票唐 vs 1 票東漢 → 唐
        self.assertEqual(dominant_dynasty(["T0220", "T0013", "T0220"], self.dmap), "唐 618 CE ~ 907 CE")
        self.assertEqual(dominant_dynasty(["ZZ9999"], self.dmap), "未詳")
        self.assertEqual(dominant_dynasty([], self.dmap), "未詳")

    def test_group_authors(self):
        anson = {"title": "安世高", "children": [{"key": "T0013"}, {"key": "T0014"}]}
        xuanzang = {"title": "玄奘", "children": [{"key": "T0220"}]}
        unknown = {"title": "無名", "children": [{"key": "ZZ9999"}]}
        pairs = group_authors_by_dynasty([xuanzang, unknown, anson], self.dmap, self.order)
        self.assertEqual([t for t, _ in pairs],
                         ["東漢 25 CE ~ 220 CE", "唐 618 CE ~ 907 CE", "未詳"])
        self.assertEqual([a["title"] for a in pairs[0][1]], ["安世高"])
        self.assertEqual([a["title"] for a in pairs[2][1]], ["無名"])


def _write(data):
    d = Path(tempfile.mkdtemp())
    p = d / "dynasty-works.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


if __name__ == "__main__":
    unittest.main()
