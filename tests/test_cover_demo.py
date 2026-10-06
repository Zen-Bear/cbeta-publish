# -*- coding: utf-8 -*-
"""封面布局演示生成器冒烟：能生成 PDF，纸张/页数/封面内容符合预期。

只读 `assets/images/` 与 `cbeta_publish.books.ebook_merger`，写临时目录，
不触真实配置/丛书数据。
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "docs" / "封面布局演示" / "gen_cover_demo.py"


def _load_gen():
    spec = importlib.util.spec_from_file_location("cover_demo_gen", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCoverDemo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_gen()

    def test_build_a4(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "demo.pdf"
            self.mod.build(out, paper="a4")
            self.assertTrue(out.is_file())
            doc = pymupdf.open(str(out))
            try:
                # 前言 + 封面/空白/封面图/编辑说明/说明/目录/正文（补偶页）/封底图/封底 + 对照表
                self.assertEqual(len(doc), 16)
                self.assertGreaterEqual(len(doc), 10)
                # 纸张为 A4
                r = doc[1].rect
                self.assertAlmostEqual(r.width, 595.28, delta=1)
                self.assertAlmostEqual(r.height, 841.89, delta=1)
                # 封面页含示例丛书名（第 0 页为前言）
                self.assertIn("大乘五部典籍", doc[1].get_text())
            finally:
                doc.close()

    def test_build_a5_paper_size(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "demo_a5.pdf"
            self.mod.build(out, paper="a5")
            doc = pymupdf.open(str(out))
            try:
                r = doc[1].rect
                self.assertAlmostEqual(r.width, 419.53, delta=1)
                self.assertAlmostEqual(r.height, 595.28, delta=1)
            finally:
                doc.close()


if __name__ == "__main__":
    unittest.main()
