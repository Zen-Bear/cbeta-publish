# -*- coding: utf-8 -*-
"""合并打印/阅读模式测试：页面序列、书签、目录链接（图像有/无）。"""
import shutil
import tempfile
import unittest
from pathlib import Path

import pymupdf

from cbeta_publish.books.ebook_merger import _intro_pdf, _toc_pdf, merge_pdfs

COVER = {
    "organizer": "测试",
    "mode": "print",
    "images": {
        "buddha": {"file": "assets/images/buddha.jpg", "enabled": True},
        "weituo": {"file": "assets/images/weituo.jpg", "enabled": True},
    },
}


class MergeModeTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.srcs = []
        for name in ("A", "B"):
            d = pymupdf.open()
            d.new_page(width=595, height=842).insert_text((100, 100), name)
            p = self.dir / f"{name}.pdf"
            d.save(p)
            self.srcs.append(p)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self, mode, enabled):
        import copy
        c = copy.deepcopy(COVER)
        c["mode"] = mode
        c["images"]["buddha"]["enabled"] = enabled
        c["images"]["weituo"]["enabled"] = enabled
        out = self.dir / f"{mode}_{enabled}" / "o.pdf"
        parts = merge_pdfs(self.srcs, out, titles=["A", "B"], collection_name="c",
                           organizer="x", cover_config=c)
        doc = pymupdf.open(parts[0])
        return len(doc), doc.get_toc(), doc

    def test_print_with_images(self):
        n, toc, doc = self._run("print", True)
        self.assertEqual(n, 13)
        self.assertEqual([t[2] for t in toc], [1, 5, 7, 9])
        # 目录页链接指向正文首页
        toc_idx = next(t[2] for t in toc if t[1] == "目录") - 1
        self.assertEqual(sorted(l.get("page", -1) + 1 for l in doc[toc_idx].get_links()), [7, 9])

    def test_print_without_images(self):
        n, toc, _ = self._run("print", False)
        self.assertEqual(n, 9)
        self.assertEqual([t[2] for t in toc], [1, 3, 5, 7])

    def test_reading_with_images(self):
        n, toc, _ = self._run("reading", True)
        self.assertEqual(n, 6)
        self.assertEqual([t[2] for t in toc], [1, 3, 4, 5])

    def test_reading_without_images(self):
        n, toc, _ = self._run("reading", False)
        self.assertEqual(n, 4)
        self.assertEqual([t[2] for t in toc], [1, 2, 3, 4])

    def test_bookmark_anchors_page_top(self):
        # 书签跳转必须落在页顶附近（页顶 1pt 内），不能是默认的页顶下 36pt
        import copy
        from cbeta_publish.books.ebook_merger import BOOKMARK_TOP_MARGIN
        c = copy.deepcopy(COVER)
        c["mode"] = "reading"
        c["images"]["buddha"]["enabled"] = False
        c["images"]["weituo"]["enabled"] = False
        out = self.dir / "anchor" / "o.pdf"
        parts = merge_pdfs(self.srcs, out, titles=["A", "B"], collection_name="c",
                           organizer="x", cover_config=c)
        doc = pymupdf.open(parts[0])
        full = doc.get_toc(simple=False)
        self.assertTrue(len(full) >= 3)
        for lvl, title, page, link in full:
            self.assertAlmostEqual(link["to"].y, BOOKMARK_TOP_MARGIN, places=3, msg=title)
        # 裸合并路径同样精确到页顶
        out2 = self.dir / "anchor_bare" / "o.pdf"
        parts2 = merge_pdfs(self.srcs, out2, titles=["A", "B"], collection_name="c",
                            organizer="x", cover_config={"enabled": False})
        doc2 = pymupdf.open(parts2[0])
        for lvl, title, page, link in doc2.get_toc(simple=False):
            self.assertAlmostEqual(link["to"].y, BOOKMARK_TOP_MARGIN, places=3, msg=title)


    def test_cover_date_matches_cbeta_size(self):
        # PDF 封面日期字号与左上角 CBETA 一致
        import copy
        import datetime
        c = copy.deepcopy(COVER)
        out = self.dir / "datecheck" / "o.pdf"
        parts = merge_pdfs(self.srcs, out, titles=["A", "B"], collection_name="c",
                           organizer="x", cover_config=c)
        doc = pymupdf.open(parts[0])
        h = doc[0].rect.height
        datestr = datetime.date.today().isoformat()
        date_size = None
        top_sizes = set()
        d = doc[0].get_text("dict")
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    t = s["text"].strip()
                    if not t:
                        continue
                    if datestr in t:
                        date_size = s["size"]
                    if s["bbox"][1] < h * 0.12:
                        top_sizes.add(round(s["size"], 2))
        self.assertIsNotNone(date_size)
        self.assertEqual(len(top_sizes), 1)
        self.assertAlmostEqual(date_size, next(iter(top_sizes)), places=1)


    def test_split_pages(self):
        # 小阈值触发分册；0 表示不分册
        def _src(name, pages):
            d = pymupdf.open()
            for i in range(pages):
                d.new_page(width=595, height=842).insert_text((100, 100), f"{name}-{i}")
            p = self.dir / f"{name}.pdf"
            d.save(p)
            return p
        a = _src("A", 3)
        b = _src("B", 3)
        cfg = {"enabled": False}
        out = self.dir / "split" / "o.pdf"
        parts = merge_pdfs([a, b], out, titles=["A", "B"], collection_name="c",
                           organizer="x", cover_config=cfg, split_pages=3)
        self.assertEqual(len(parts), 2)
        self.assertEqual([p.name for p in parts], ["o.pdf", "o_part2.pdf"])
        self.assertEqual(sum(len(pymupdf.open(p)) for p in parts), 6)
        out2 = self.dir / "nosplit" / "o.pdf"
        parts2 = merge_pdfs([a, b], out2, titles=["A", "B"], collection_name="c",
                            organizer="x", cover_config=cfg, split_pages=0)
        self.assertEqual(len(parts2), 1)
        self.assertEqual(len(pymupdf.open(parts2[0])), 6)

    def test_bare_no_cover_pages(self):
        # 关闭封面/封底：直接拼接，无封面/空白/目录页；原书书签降一级
        def _src(name, entries):
            d = pymupdf.open()
            for i in range(2):
                d.new_page(width=595, height=842).insert_text((100, 100), f"{name}-{i}")
            d.set_toc([[1, e, i + 1] for i, e in enumerate(entries)])
            p = self.dir / f"{name}.pdf"
            d.save(p)
            return p
        a = _src("A", ["a1", "a2"])
        b = _src("B", ["b1"])
        out = self.dir / "bare" / "o.pdf"
        parts = merge_pdfs([a, b], out, titles=["A", "B"], collection_name="c",
                           organizer="x", cover_config={"enabled": False})
        doc = pymupdf.open(parts[0])
        self.assertEqual(len(doc), 4)
        toc = doc.get_toc()
        self.assertEqual(
            [(t[0], t[1], t[2]) for t in toc],
            [(1, "A", 1), (2, "a1", 1), (2, "a2", 2),
             (1, "B", 3), (2, "b1", 3)])


    def test_intro_page_inserted_and_toc_shifted(self):
        # 说明页：封面之后、目录之前；目录/正文页码顺延
        import copy
        c = copy.deepcopy(COVER)
        c["mode"] = "reading"
        c["images"]["buddha"]["enabled"] = False
        c["images"]["weituo"]["enabled"] = False
        intro = {"title": "说明", "summary": ["本丛书共收录 2 部", "部類分布：阿含部類 2"],
                 "sections": [("01 阿含部類（2 部）", ["T0001 長阿含經", "T0002 七佛經"])]}

        def _run(i):
            out = self.dir / f"intro_{i}" / "o.pdf"
            return merge_pdfs(self.srcs, out, titles=["A", "B"], collection_name="c",
                              organizer="x", cover_config=c, intro=(intro if i else None))

        base = pymupdf.open(_run(0)[0])
        withi = pymupdf.open(_run(1)[0])
        # 无目录链接的阅读模式：intro 1 页 -> 总页数 +1
        self.assertEqual(len(withi), len(base) + 1)
        # intro 位于第 2 页，且含说明文字与清单（PDF 抽取可能在 CJK 间插空字节）
        page2 = withi[1].get_text().replace("\x00", "")
        self.assertIn("说明", page2)
        self.assertIn("T0001", page2)
        # 书签：封面 -> 说明 -> 目录 -> 正文
        toc = withi.get_toc()
        self.assertEqual(toc[0][:3], [1, "封面", 1])
        self.assertEqual(toc[1][:3], [1, "说明", 2])
        self.assertEqual(toc[2][:3], [1, "目录", 3])

    def test_intro_uses_toc_text_metrics(self):
        metrics_dir = self.dir / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        toc_out = metrics_dir / "toc.pdf"
        intro_out = metrics_dir / "intro.pdf"
        _toc_pdf(["One"], self.srcs[0], toc_out, config={}, page_nums=None)
        _intro_pdf(
            {"title": "Intro", "summary": ["Sigma"], "sections": [("Section", ["Item"])]},
            self.srcs[0], intro_out, config={},
        )

        def spans(page):
            found = {}
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span["text"].strip()
                        if text and text not in found:
                            found[text] = (span["size"], span["bbox"])
            return found

        toc_spans = spans(pymupdf.open(toc_out)[0])
        intro_spans = spans(pymupdf.open(intro_out)[0])
        self.assertAlmostEqual(intro_spans["Intro"][0], toc_spans["目录"][0])
        self.assertAlmostEqual(intro_spans["Intro"][1][1], toc_spans["目录"][1][1])
        self.assertAlmostEqual(intro_spans["Sigma"][0], toc_spans["One"][0])
        self.assertAlmostEqual(intro_spans["Sigma"][1][1], toc_spans["One"][1][1])
        self.assertAlmostEqual(intro_spans["Item"][0], intro_spans["Sigma"][0])


    def test_intro_body_line_spacing_matches_epub(self):
        out = self.dir / "intro-spacing" / "intro.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        _intro_pdf(
            {
                "title": "Intro",
                "summary": ["Sigma", "Sigma"],
                "sections": [("Section", ["Item", "Item"])],
            },
            self.srcs[0], out, config={},
        )
        page = pymupdf.open(out)[0]
        rows = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line.get("spans", [])).strip()
                rows.append((text, line["bbox"]))
        sigmas = [bbox for text, bbox in rows if text == "Sigma"]
        items = [bbox for text, bbox in rows if text == "Item"]
        self.assertEqual(len(sigmas), 2)
        self.assertEqual(len(items), 2)
        # EPUB 段落边距与默认行高换算后，PDF 正文与子项分别约为 1.5 与 1.35 倍字号。
        self.assertAlmostEqual(sigmas[1][1] - sigmas[0][1], 13 * 1.2, places=1)
        self.assertAlmostEqual(items[1][1] - items[0][1], 13 * 1.35, places=1)

    def test_intro_section_prespacing(self):
        out = self.dir / "intro-blank" / "intro.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        _intro_pdf(
            {
                "title": "Intro",
                "summary": ["Sigma", "部類分布：阿含部類 2"],
                "sections": [("Section", ["Item"])],
            },
            self.srcs[0], out, config={},
        )
        page = pymupdf.open(out)[0]
        rows = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line.get("spans", [])).strip()
                rows.append((text, line["bbox"]))
        by_text = {}
        for text, bbox in rows:
            by_text.setdefault(text.replace("\x00", ""), bbox)
        dist = by_text["部類分布：阿含部類 2"]
        section = by_text["Section"]
        # 部类标题段前 0.5em；“部類分布”后不再另空行
        self.assertAlmostEqual(section[1] - dist[1], 13 * 1.2 + 13 * 0.5, places=1)


    def test_progress_callback_and_cancel(self):
        from cbeta_publish.books.ebook_merger import MergeCancelled
        calls = []
        out = self.dir / "prog" / "o.pdf"
        merge_pdfs(self.srcs, out, titles=["A", "B"], collection_name="c",
                   organizer="x", cover_config={"enabled": False},
                   progress=lambda d, n, l: (calls.append((d, n, l)), True)[1])
        self.assertEqual([c[0] for c in calls], [0, 1])
        self.assertTrue(all(c[1] == 2 for c in calls))
        self.assertEqual([c[2] for c in calls], ["A（A.pdf）", "B（B.pdf）"])

        def stop(d, n, l):
            return False
        with self.assertRaises(MergeCancelled):
            merge_pdfs(self.srcs, self.dir / "progc" / "o.pdf", titles=["A", "B"],
                       collection_name="c", organizer="x",
                       cover_config={"enabled": False}, progress=stop)

    def test_cover_margins_and_positions(self):
        import copy
        from cbeta_publish.books.ebook_merger import _cover_pdf
        c = copy.deepcopy(COVER)
        c["mode"] = "reading"
        c["sizes"] = {"body_a4": 12, "margins": {"a4": {"left": 40, "right": 40, "top": 30, "bottom": 40}}}
        c["positions"] = {"title_y_ratio": 0.30, "organizer_y_ratio": 0.84, "date_y_ratio": 0.90}
        p1 = self.dir / "cv1" / "c.pdf"
        p1.parent.mkdir(parents=True, exist_ok=True)
        _cover_pdf(self.srcs[0], "测试", p1, organizer="编", config=c)
        d1 = pymupdf.open(p1)[0]
        def _spans(page):
            out = []
            for b in page.get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        if s["text"].strip():
                            out.append((s["text"].strip(), s["bbox"]))
            return out

        sp1 = _spans(d1)
        cbeta = next((bb for t, bb in sp1 if t.startswith("CBETA")), None)
        # 顶部 CBETA 的 x 应为 margins.left
        self.assertIsNotNone(cbeta)
        self.assertAlmostEqual(cbeta[0], 40, places=0)
        # 标题 x 居中于 [left, width-right]
        title = next((bb for t, bb in sp1 if t == "测试"), None)
        self.assertIsNotNone(title)
        self.assertAlmostEqual((title[0] + title[2]) / 2, 595 / 2, places=0)
        # 改 title_y_ratio -> 标题 y 变化
        c2 = copy.deepcopy(c)
        c2["positions"]["title_y_ratio"] = 0.50
        p2 = self.dir / "cv2" / "c.pdf"
        p2.parent.mkdir(parents=True, exist_ok=True)
        _cover_pdf(self.srcs[0], "测试", p2, organizer="编", config=c2)
        d2 = pymupdf.open(p2)[0]
        t2 = next((bb for t, bb in _spans(d2) if t == "测试"), None)
        self.assertIsNotNone(t2)
        # 0.50 比 0.30 更靠下（页面自上而下 y 更大）
        self.assertGreater(t2[1], title[1])

    def test_cover_imprint_configurable(self):
        import copy
        from cbeta_publish.books.ebook_merger import _cover_pdf
        c = copy.deepcopy(COVER)
        c["mode"] = "reading"
        c["imprint"] = "MY IMPRINT"
        p = self.dir / "imprint" / "c.pdf"
        p.parent.mkdir(parents=True, exist_ok=True)
        _cover_pdf(self.srcs[0], "测试", p, organizer="编", config=c)
        txt = pymupdf.open(p)[0].get_text().replace("\x00", "")
        self.assertIn("MY IMPRINT", txt)
        self.assertNotIn("CBETA", txt)


class ReregisterFontTest(unittest.TestCase):
    """同名换字体路径必须即时生效（reportlab 对同名重注册静默忽略，
    否则改封面字体后必须重启）。"""

    def test_same_name_new_path(self):
        from cbeta_publish.books import ebook_merger as m
        from reportlab.pdfbase import pdfmetrics
        f1 = Path("C:/Windows/Fonts/simhei.ttf")
        f2 = Path("C:/Windows/Fonts/msyh.ttc")
        for f in (f1, f2):
            if not f.exists():
                self.skipTest(f"missing {f}")
        n1 = m._register_font("T_RegTest", str(f1))
        n2 = m._register_font("T_RegTest", str(f2))
        self.assertNotEqual(n1, n2)
        self.assertIn(n2, pdfmetrics.getRegisteredFontNames())
        # 同一路径重复注册复用（不再重复解析大字库）
        self.assertEqual(m._register_font("T_RegTest", str(f2)), n2)


if __name__ == "__main__":
    unittest.main()
