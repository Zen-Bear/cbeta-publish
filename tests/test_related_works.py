# -*- coding: utf-8 -*-
"""按题名关联作品（related_works）：书名段匹配、体裁后缀、别名撞名不认领。"""
import unittest

from cbeta_publish.creators import related_works as rw


class RelatedWorksTest(unittest.TestCase):
    def test_book_part_strips_key_and_author_block(self):
        self.assertEqual(rw.book_part("X1420 楚石梵琦禪師語錄 (20卷)【(門人)祖光…等編】"),
                         "楚石梵琦禪師語錄 (20卷)")
        self.assertEqual(rw.book_part("T0001 長阿含經 (22卷)【後秦 佛陀耶舍譯】"),
                         "長阿含經 (22卷)")
        self.assertEqual(rw.book_part("T0128a 須摩提女經 (1卷)"), "須摩提女經 (1卷)")
        self.assertEqual(rw.book_part(""), "")
        self.assertEqual(rw.book_part(None), "")

    def test_matches_needs_suffix_right_after_name(self):
        # 命中：名字后面紧接体裁词
        self.assertEqual(rw.matches("楚石梵琦禪師語錄 (20卷)", ["梵琦", "楚石梵琦"]),
                         "楚石梵琦")          # 命中多个取最长
        self.assertEqual(rw.matches("六祖大師法寶壇經", ["六祖"]), "六祖")
        self.assertEqual(rw.matches("為霖道霈禪師還山錄", ["為霖", "為霖道霈"]), "為霖道霈")
        # 不命中：名字后面不是体裁词（大般若經／觀自在／功德莊嚴經 这类同名噪声）
        self.assertIsNone(rw.matches("大般若經關法 (6卷)", ["般若"]))
        self.assertIsNone(rw.matches("觀自在菩薩祕密法經", ["自在"]))
        self.assertIsNone(rw.matches("大聖文殊師利菩薩佛剎功德莊嚴經", ["功德"]))
        # 单字名不比
        self.assertIsNone(rw.matches("禪師語錄", ["禪"]))

    def test_matches_venerable_suffix(self):
        # 2026-10-18：「尊者」入后缀——紫柏尊者全集/別集 归真可、阿底峽尊者傳 归阿底峽
        self.assertEqual(rw.matches("紫柏尊者全集 (29卷)", ["真可", "紫柏", "紫栢"]), "紫柏")
        self.assertEqual(rw.matches("紫柏尊者別集 (4卷)", ["真可", "紫柏"]), "紫柏")
        self.assertEqual(rw.matches("阿底峽尊者傳 (1卷)", ["阿底峽"]), "阿底峽")
        # 「集／別集」不入后缀：天竺別集是遵式的（「天竺」指天竺寺）、空谷集是釋景隆的
        self.assertIsNone(rw.matches("天竺別集 (3卷)", ["佛陀跋陀羅", "天竺"]))
        self.assertIsNone(rw.matches("空谷集 (3卷)", ["道澄", "空谷"]))

    def test_names_index_drops_short_and_duplicate(self):
        idx = rw.names_index({"A1": {"regular_name": "梵琦",
                                     "aliases_all": ["梵琦", "楚", "", "楚石"]}})
        self.assertEqual(idx, {"A1": ["梵琦", "楚石"]})
        self.assertEqual(rw.names_index({}), {})
        self.assertEqual(rw.names_index({"A1": {"regular_name": "", "aliases_all": ["甲"]}}), {})

    def test_related_index_finds_work_by_title(self):
        alias = {"A1": {"regular_name": "梵琦", "aliases_all": ["楚石梵琦", "楚石"]}}
        works = {"X1420": "X1420 楚石梵琦禪師語錄 (20卷)【(門人)祖光．文玹 等編】",
                 "B0087": "B0087 合訂天台三聖二和詩集 (1卷)【寒山．豐干．拾得原詩】"}
        idx = rw.related_index(alias, works)
        self.assertEqual([(w, n) for w, _t, n in idx["A1"]], [("X1420", "楚石梵琦")])
        # 已归属的作品仍在索引里（是否剔除由调用方决定）
        self.assertEqual(len(idx["A1"]), 1)

    def test_related_index_skips_alias_that_is_another_regular_name(self):
        # 明代無相号太虛（别名表记「太虛」）：不能拿它认领民國太虛大師的作品
        alias = {"A1": {"regular_name": "無相", "aliases_all": ["太虛", "大虗相"]},
                 "A2": {"regular_name": "太虛", "aliases_all": ["太虛大師"]}}
        works = {"TX0001": "TX0001 太虛大師全書．第一編　佛法總學 (34卷)【民國 釋太虛著】"}
        idx = rw.related_index(alias, works)
        self.assertNotIn("A1", idx)
        self.assertEqual([w for w, _t, _n in idx["A2"]], ["TX0001"])
        # 本名照比：無相 自己的「無相禪師語錄」仍命中
        idx2 = rw.related_index({"A1": {"regular_name": "無相"}},
                                {"X9999": "X9999 無相禪師語錄 (2卷)"})
        self.assertEqual([w for w, _t, _n in idx2["A1"]], ["X9999"])

    def test_related_index_venerable_titles_go_to_named_author(self):
        # 全量实测（2026-10-18）「尊者」新增仅这 3 部：紫柏全集/別集→真可、阿底峽尊者傳→阿底峽
        alias = {"A1": {"regular_name": "真可", "aliases_all": ["紫柏", "紫栢", "達觀"]},
                 "A2": {"regular_name": "阿底峽"},
                 "A3": {"regular_name": "佛陀跋陀羅", "aliases_all": ["天竺"]}}
        works = {"X1452": "X1452 紫柏尊者全集 (29卷)【明 德清閱】",
                 "X1453": "X1453 紫柏尊者別集 (4卷)【明 錢謙益纂閱】",
                 "B0072": "B0072 阿底峽尊者傳 (1卷)",
                 "X0951": "X0951 天竺別集 (3卷)【宋 遵式述　慧觀重編】"}
        idx = rw.related_index(alias, works)
        self.assertEqual([(w, n) for w, _t, n in idx["A1"]],
                         [("X1452", "紫柏"), ("X1453", "紫柏")])
        self.assertEqual([w for w, _t, _n in idx["A2"]], ["B0072"])
        self.assertNotIn("A3", idx)     # 「別集」不入后缀，「天竺」不认领

    def test_related_index_empty_inputs(self):
        self.assertEqual(rw.related_index({}, {"X1": "X1 太虛大師全書"}), {})
        self.assertEqual(rw.related_index({"A1": {"regular_name": "太虛"}}, {}), {})
        self.assertEqual(rw.related_index({"A1": {"regular_name": "太虛"}},
                                          {"X1": "X1 金剛經 (1卷)【姚秦 鳩摩羅什譯】"}), {})

    def test_known_false_positive_left_in_place(self):
        # 已知误配（用户暂不处理）：傳燈→《續傳燈錄》「傳燈」后紧接「錄」
        idx = rw.related_index({"A1": {"regular_name": "傳燈"}},
                               {"T2077": "T2077 續傳燈錄 (36卷)【明 居頂輯】"})
        self.assertEqual([w for w, _t, _n in idx["A1"]], ["T2077"])


if __name__ == "__main__":
    unittest.main()
