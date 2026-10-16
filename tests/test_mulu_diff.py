# -*- coding: utf-8 -*-
"""目录源差异（mulu_diff）：经的新增/删除/改名、经号归一化、跨源合并、摘要/明细排版。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import mulu_diff as md


def _tree(works):
    """构造 category/dynasty/vol 形树：叶子带 key/title。"""
    return [{"title": "選擇全部", "key": "root",
             "children": [{"title": f"{k} 书名{k}", "key": k} for k in works]}]


class MuluDiffTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pair(self, name, old_text, new_text):
        old = self.tmp / "old" / name
        new = self.tmp / "new" / name
        for p, t in ((old, old_text), (new, new_text)):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(t, encoding="utf-8")
        return old, new

    def test_norm_key_strips_leading_zeros(self):
        self.assertEqual(md.norm_key("T0001"), "T1")
        self.assertEqual(md.norm_key("T0128a"), "T128a")
        self.assertEqual(md.norm_key("B0001"), "B1")
        self.assertEqual(md.norm_key("T" + "0220"), "T220")   # mapping 的藏+号
        self.assertEqual(md.norm_key(""), "")
        self.assertEqual(md.norm_key("書名"), "")

    def test_tree_added_removed_renamed(self):
        old, new = self._pair(
            "category.json",
            json.dumps(_tree(["T0001", "T0002", "T0003"]), ensure_ascii=False),
            json.dumps(_tree(["T0001", "T0003", "T0004"]), ensure_ascii=False))
        d = md.diff_source("category", old, new)
        self.assertEqual([k for k, _t in d["added"]], ["T4"])
        self.assertEqual([k for k, _t in d["removed"]], ["T2"])
        self.assertEqual(d["counts"], (1, 1, 0))
        # 改名：同 key 标题变化
        old2, new2 = self._pair(
            "category.json",
            json.dumps([{"title": "選擇全部", "children": [
                {"title": "T0001 舊名", "key": "T0001"}]}], ensure_ascii=False),
            json.dumps([{"title": "選擇全部", "children": [
                {"title": "T0001 新名", "key": "T0001"}]}], ensure_ascii=False))
        d2 = md.diff_source("category", old2, new2)
        self.assertEqual(d2["counts"], (0, 0, 1))
        self.assertEqual(d2["renamed"][0][1:], ("T0001 舊名", "T0001 新名"))

    def test_titles_source_takes_key_from_title(self):
        # SutraList：叶子无 key，经号取标题首词；B0001 与 mapping 的 B1 归一化后同号
        old, new = self._pair(
            "SutraList.json",
            json.dumps([{"title": "藏", "children": [
                {"title": "T0001 長阿含經"}]}], ensure_ascii=False),
            json.dumps([{"title": "藏", "children": [
                {"title": "T0001 長阿含經"},
                {"title": "B0001 新書"}]}], ensure_ascii=False))
        d = md.diff_source("sutralist", old, new)
        self.assertEqual(d["counts"], (1, 0, 0))
        self.assertEqual(d["added"][0], ("B1", "B0001 新書"))

    def test_mapping_source_title_with_author(self):
        old, new = self._pair(
            "sutra_mapping.txt",
            "T,05,0001,22,1,0001a01,長阿含經,後秦 佛陀耶舍譯\n",
            "T,05,0001,22,1,0001a01,長阿含經,後秦 佛陀耶舍譯\n"
            "G,127,2352,10,1,0257a01,楞伽阿跋多羅寶經科解,明 真貴述\n")
        d = md.diff_source("sutra_mapping", old, new)
        self.assertEqual(d["counts"], (1, 0, 0))
        self.assertEqual(d["added"][0],
                         ("G2352", "G2352 楞伽阿跋多羅寶經科解（明 真貴述）"))

    def test_bulei_skips_volume_leaf_and_range_lines(self):
        # 部类树文本：只认纯经号行首；卷叶 `T0220_401..537`、区间标签 `T0001-25` 都不算
        old, new = self._pair(
            "bulei.txt",
            "T0001 長阿含經22卷\n",
            "T0001 長阿含經22卷\n"
            "\tT0220_401..537 大般若經 (卷401-537)\n"
            "T0001-25 長阿含經 etc. T01\n"
            "G2352 楞伽阿跋多羅寶經科解\n")
        d = md.diff_source("bulei_txt", old, new)
        self.assertEqual(d["counts"], (1, 0, 0))
        self.assertEqual(d["added"][0][0], "G2352")

    def test_missing_side_or_unknown_key_returns_none(self):
        old, new = self._pair("category.json", "[]", "[]")
        self.assertIsNone(md.diff_source("category", self.tmp / "nope.json", new))
        self.assertIsNone(md.diff_source("category", old, self.tmp / "nope.json"))
        self.assertIsNone(md.diff_source("creators_alias", old, new))   # 未纳入经清单的源

    def test_merge_works_dedupes_and_prefers_priority(self):
        diffs = {
            "category": {"added": [("T1", "T0001 範圍清單名")], "removed": [],
                         "renamed": [], "counts": (1, 0, 0)},
            "sutralist": {"added": [("T1", "T0001 經錄名"), ("B1", "B0001 新書")],
                          "removed": [], "renamed": [], "counts": (2, 0, 0)},
        }
        merged = md.merge_works(diffs, "added")
        # 按经号排序（B1 在 T1 前）；同号取优先级最高源（category）的标题
        self.assertEqual(merged, [("B1", "B0001 新書"), ("T1", "T0001 範圍清單名")])

    def test_summary_and_detail_text(self):
        diffs = {
            "category": {"key": "category",
                         "added": [("T220", "T0220 大般若波羅蜜多經 (600卷)【唐 玄奘譯】")],
                         "removed": [], "renamed": [], "counts": (1, 0, 0)},
            "vol": {"key": "vol", "added": [], "removed": [], "renamed": [],
                    "counts": (0, 0, 0)},
        }
        lines = md.summary_lines(diffs, label_of={"category": "category.json（部类）",
                                                  "vol": "vol.json（刊本）"})
        self.assertEqual(lines[0], "—— 目录变更（对比上次更新前的备份）——")
        self.assertIn("category.json（部类）：新增 1、删除 0、改名 0", lines)
        self.assertIn("vol.json（刊本）：无变化", lines)
        self.assertIn("新增经 1 部：T0220 大般若波羅蜜多經 (600卷)【唐 玄奘譯】", lines)
        txt = md.detail_text(diffs)
        self.assertIn("合计（跨源去重）：新增经 1 部", txt)
        self.assertIn("+ T0220 大般若波羅蜜多經 (600卷)【唐 玄奘譯】", txt)
        self.assertIn("（无变化）", txt)

    def test_summary_without_backup(self):
        self.assertIn("无可对比项", md.summary_lines({})[0])
        self.assertIn("没有可对比的备份", md.detail_text({}))

    def test_summary_limits_listed_titles(self):
        added = [(f"T{i}", f"T{i:04d} 書") for i in range(1, 31)]
        diffs = {"category": {"key": "category", "added": added, "removed": [],
                              "renamed": [], "counts": (30, 0, 0)}}
        lines = md.summary_lines(diffs, limit=20)
        self.assertIn("新增经 30 部：", "".join(lines))
        self.assertIn("…（共 30 部，点「查看目录变更…」看全部）", "".join(lines))


if __name__ == "__main__":
    unittest.main()
