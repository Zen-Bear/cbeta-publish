# -*- coding: utf-8 -*-
"""部类索引与说明页汇总（不依赖网络/GUI）。"""
import unittest

from cbeta_publish.catalog.bulei_index import build_index, summarize, _bulei_label
from cbeta_publish.catalog.bulei_parser import BuleiNode


def _tree():
    # 顶层部類 -> 类别组 -> 叶（work）
    def leaf(t):
        return BuleiNode(level=3, title=t, raw=t)
    def group(t, kids):
        return BuleiNode(level=2, title=t, raw=t, children=kids)
    def top(t, kids):
        return BuleiNode(level=1, title=t, raw=t, children=kids)
    a = top("01 阿含部類 T01-02 etc.", [
        group("T0001-25 長阿含類 T01", [
            leaf("T0001 長阿含經 (22卷)"),
            leaf("T0002 七佛經 (1卷)"),
        ]),
    ])
    b = top("06 寶積部類 T11-12 etc.", [
        group("T0310 大寶積經 T11", [leaf("T0310 大寶積經 (120卷)")]),
    ])
    return [a, b]


class BuleiIndexTest(unittest.TestCase):
    def test_build_index(self):
        idx = build_index(_tree())
        self.assertEqual(idx["T0001"]["bulei"], "01 阿含部類 T01-02 etc.")
        self.assertEqual(idx["T0310"]["bulei"], "06 寶積部類 T11-12 etc.")
        self.assertTrue(idx["T0001"]["pitaka"])

    def test_bulei_label(self):
        self.assertEqual(_bulei_label("01 阿含部類 T01-02,25,33 etc."), "阿含部類")
        self.assertEqual(_bulei_label("01 阿含部類 T01-02,25,33 etc.", with_num=True), "01 阿含部類")
        self.assertEqual(_bulei_label("10 密教部類 T18-21,39,46, X01-02 etc."), "密教部類")

    def test_summarize(self):
        s = summarize(["T0001", "T0002", "T0310", "ZZ9999"], _tree())
        self.assertEqual(s["summary"][0], "本丛书共收录 4 部")
        self.assertTrue(any("ZZ9999" in r for _, rows in s["sections"] for r in rows))
        headers = [h for h, _ in s["sections"]]
        self.assertTrue(any(h.startswith("01 阿含部類") for h in headers), headers)
        self.assertTrue(any("未歸類" in h for h in headers), headers)
        # 阿含部類含 2 部
        a = next(rows for h, rows in s["sections"] if h.startswith("01 "))
        self.assertEqual(len(a), 2)
        self.assertTrue(all(r.startswith("T00") for r in a))

    def test_summarize_empty(self):
        s = summarize([], _tree())
        self.assertEqual(s["total"] if "total" in s else s["summary"][0], "本丛书共收录 0 部")
        self.assertEqual(s["sections"], [])

    def test_dedupe(self):
        s = summarize(["T0001", "T0001", "T0001"], _tree())
        self.assertEqual(s["summary"][0], "本丛书共收录 1 部")

    def test_title_of_override_matches_toc(self):
        # 目录页用 title_of；说明页给同一解析器时行标签应完全一致（不含作者）
        s = summarize(["T0001", "T0310"], _tree(),
                      title_of=lambda w: {"T0001": "T0001 長阿含經",
                                          "T0310": "T0310 大寶積經"}.get(w, w))
        rows = [r for _, rr in s["sections"] for r in rr]
        self.assertIn("T0001 長阿含經", rows)
        self.assertIn("T0310 大寶積經", rows)
        self.assertFalse(any("卷" in r for r in rows))
        self.assertFalse(any("【" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
