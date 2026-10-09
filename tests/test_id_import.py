# -*- coding: utf-8 -*-
"""批量 ID 导入纯逻辑：token 归一、行解析、分类、HTML/网页文本。"""
import unittest
from unittest import mock

from cbeta_publish.collection import id_import as ii


class TokenTest(unittest.TestCase):
    def test_split_token(self):
        self.assertEqual(ii.split_token("T0001:2-3"), ("T0001", "2-3"))
        self.assertEqual(ii.split_token("T0001：2-3"), ("T0001", "2-3"))
        self.assertEqual(ii.split_token("T0001_001"), ("T0001", "1"))
        self.assertEqual(ii.split_token("T0001:1_002"), ("T0001", "1_002"))
        self.assertEqual(ii.split_token("T0001"), ("T0001", None))
        self.assertEqual(ii.split_token(""), ("", None))

    def test_normalize_token(self):
        self.assertEqual(ii.normalize_token("T0001"), "T0001")
        self.assertEqual(ii.normalize_token("t0349"), "T0349")
        self.assertEqual(ii.normalize_token("TXA001"), "TXa001")
        self.assertEqual(ii.normalize_token("T0349:2-3"), "T0349")
        self.assertEqual(ii.normalize_token("T0001_001"), "T0001")
        self.assertEqual(ii.normalize_token("T01n0001"), "T0001")
        self.assertEqual(ii.normalize_token("T05n0220_001"), "T0220")
        self.assertEqual(ii.normalize_token("T01n0001.xml"), "T0001")

    def test_normalize_invalid(self):
        for bad in ("", "T01", "ZZ9999", "阿含經", "T01 阿含部", "  "):
            self.assertEqual(ii.normalize_token(bad), "", bad)

    def test_juan_token(self):
        self.assertEqual(ii.juan_token("T0349", "2-3"), "T0349:2-3")
        self.assertEqual(ii.juan_token("T0349", "34-36,40"), "T0349:34-36+40")
        self.assertEqual(ii.juan_token("T0349", "34-36、40"), "T0349:34-36+40")
        self.assertEqual(ii.juan_token("T0001", ""), "T0001")

    def test_token_juan(self):
        self.assertEqual(ii.token_juan("T0349:2-3"), "2-3")
        self.assertEqual(ii.token_juan("T11n0310_050"), "50")
        self.assertEqual(ii.token_juan("T11n0310_050.xml"), "50")
        self.assertEqual(ii.token_juan("T0001"), "")

    def test_long_basename_juan(self):
        self.assertEqual(ii.normalize_token("T11n0310_050"), "T0310")
        self.assertEqual(ii.normalize_token("T11n0310_050.xml"), "T0310")


class ParseLinesTest(unittest.TestCase):
    def test_skip_comments_and_blanks(self):
        text = "# 注释\n// 注释\n\n   \nT0001 甲\n"
        self.assertEqual(ii.parse_id_lines(text), [("T0001", "甲")])

    def test_note_stripping(self):
        text = "\n".join([
            "T0349 彌勒菩薩所問本願經",
            "T0001 - 長阿含經",
            "T0002:2-3 卷范围",
            "T0003,注释甲",
            "T0004:34-36,40",
        ])
        self.assertEqual(ii.parse_id_lines(text), [
            ("T0349", "彌勒菩薩所問本願經"),
            ("T0001", "長阿含經"),
            ("T0002:2-3", "卷范围"),
            ("T0003", "注释甲"),
            ("T0004:34-36,40", ""),   # 卷范围含逗号，不误切为注释
        ])

    def test_bom_and_csv(self):
        self.assertEqual(ii.parse_id_lines("\ufeffT0001\t注"),
                         [("T0001", "注")])


class ClassifyTest(unittest.TestCase):
    def test_status(self):
        rows = [("T0001", "甲"), ("T0001", "乙"), ("T0999", "丙"), ("bad", "丁")]
        got = ii.classify(rows, work_exists=lambda w: w == "T0001")
        self.assertEqual([r.status for r in got],
                         [ii.STATUS_OK, ii.STATUS_DUP,
                          ii.STATUS_UNKNOWN, ii.STATUS_INVALID])
        self.assertEqual(got[0].work_id, "T0001")
        self.assertEqual(got[3].work_id, "")

    def test_no_catalog_check(self):
        got = ii.classify([("T0999", "")])
        self.assertEqual(got[0].status, ii.STATUS_OK)

    def test_same_work_diff_juan_not_dup(self):
        got = ii.classify([("T0220:1", ""), ("T0220:2", ""), ("T0220:1", "")])
        self.assertEqual([r.status for r in got],
                         [ii.STATUS_OK, ii.STATUS_OK, ii.STATUS_DUP])
        self.assertEqual([r.juan for r in got], ["1", "2", "1"])


class HtmlToTextTest(unittest.TestCase):
    def test_strip_and_blocks(self):
        html = ("<html><head><style>x{}</style></head><body>"
                "<p>甲 &amp; 乙</p><p>丙</p><script>y</script></body></html>")
        self.assertEqual(ii.html_to_text(html), "甲 & 乙\n丙")

    def test_blank_compress(self):
        self.assertEqual(ii.html_to_text("<p>甲</p>\n\n\n<p>乙</p>"), "甲\n乙")


class FetchTextTest(unittest.TestCase):
    class _Resp:
        def __init__(self, data, ctype):
            self._data = data
            self.headers = {"Content-Type": ctype}

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_reject_non_http(self):
        for u in ("", "ftp://x", "file:///a", "not a url"):
            self.assertEqual(ii.fetch_text(u), "")

    def test_charset_and_fallback(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=self._Resp("甲".encode("utf-8"),
                                                "text/html; charset=utf-8")):
            self.assertEqual(ii.fetch_text("https://x"), "甲")
        # 无 charset 声明，gbk 字节 → 回退 gbk
        with mock.patch("urllib.request.urlopen",
                        return_value=self._Resp("甲".encode("gbk"), "text/html")):
            self.assertEqual(ii.fetch_text("https://x"), "甲")

    def test_network_error_empty(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("boom")):
            self.assertEqual(ii.fetch_text("https://x"), "")


if __name__ == "__main__":
    unittest.main()
