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
        "buddha": {"file": "assets/images/1.tif", "enabled": True},
        "weituo": {"file": "assets/images/2.tif", "enabled": True},
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
        # 尾部=封底图+封底空白（图后不再垫空白）
        n, toc, doc = self._run("print", True)
        self.assertEqual(n, 12)
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

    def test_cover_group_line_truncates(self):
        # 封面组行超宽截断加 …（一行模式长串不溢出）；短行原样
        import copy
        from cbeta_publish.books import ebook_merger as m
        a = self.dir / "A.pdf"
        doc = pymupdf.open()
        doc.new_page(width=595, height=842).insert_text((100, 100), "A")
        doc.save(a)
        doc.close()
        out = self.dir / "gtrunc" / "o.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        long_group = "寶" * 120
        m._cover_pdf(a, "書名｜" + long_group, out, organizer="",
                     config={"enabled": True})
        txt = pymupdf.open(out)[0].get_text().replace("\x00", "")
        self.assertIn("書名", txt)
        self.assertTrue(any("…" in ln and "寶" in ln
                            for ln in txt.split("\n")), txt[:200])
        out2 = self.dir / "gshort" / "o.pdf"
        out2.parent.mkdir(parents=True, exist_ok=True)
        m._cover_pdf(a, "書名｜短組", out2, organizer="",
                     config={"enabled": True})
        txt2 = pymupdf.open(out2)[0].get_text().replace("\x00", "")
        self.assertIn("短組", txt2)
        self.assertNotIn("…", txt2)

    def test_toc_entries_numbered(self):
        # PDF 目录经书加序号（全局连续、自适应补零；目录标题本身不加）
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            tp = d / "toc.pdf"
            m._toc_pdf(["T%04d" % i for i in range(1, 13)], a, tp, config={})
            lines = [l.strip() for l in pymupdf.open(tp)[0].get_text().split("\n")
                     if l.strip()]
            self.assertEqual(lines[0], "目录")
            self.assertEqual(lines[1], "01. T0001")
            self.assertIn("12. T0012", lines)
            self.assertFalse(any(l.startswith("0. ") for l in lines))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_cover_title_quarter_height(self):
        # 封面丛书名基线在 1/4 高度；组行/整理者与旧基准像素级一致
        from cbeta_publish.books import ebook_merger as m
        a = self.dir / "A.pdf"
        doc = pymupdf.open()
        doc.new_page(width=595, height=842).insert_text((100, 100), "A")
        doc.save(a)
        doc.close()

        def words(out, config):
            out.parent.mkdir(parents=True, exist_ok=True)
            m._cover_pdf(a, "書名｜短組", out, organizer="編者",
                         config=config)
            return pymupdf.open(out)[0].get_text("words")

        def xs(ws, key):
            return sorted(round(w[0], 1) for w in ws if key in w[4])

        def ys(ws, key):
            return sorted(round(w[1], 1) for w in ws if key in w[4])

        old_cfg = {"enabled": True, "positions": {
            "title_y_ratio": 0.30, "group_y_ratio": 0.30}}
        new_words = words(self.dir / "qnew" / "o.pdf", {"enabled": True})
        old_words = words(self.dir / "qold" / "o.pdf", old_cfg)
        # 抬高约 5% 页高（0.30→0.25）
        self.assertAlmostEqual(ys(old_words, "書名")[0] - ys(new_words, "書名")[0],
                               842 * 0.05, delta=3.0)
        for key in ("短組", "編者"):
            self.assertEqual(ys(new_words, key), ys(old_words, key))
            self.assertEqual(xs(new_words, key), xs(old_words, key))

    def test_cover_title_pos_migration(self):
        # 旧缺省 0.30＋无 group 键 → 迁到 0.25/0.30；显式改过的不碰
        from cbeta_publish.gui.main_window import MainWindow
        c1 = {"cover": {"positions": {"title_y_ratio": 0.30}}}
        MainWindow._migrate_cover_title_pos(c1)
        self.assertEqual(c1["cover"]["positions"],
                         {"title_y_ratio": 0.25, "group_y_ratio": 0.30})
        c2 = {"cover": {"positions": {"title_y_ratio": 0.20}}}
        MainWindow._migrate_cover_title_pos(c2)
        self.assertEqual(c2["cover"]["positions"], {"title_y_ratio": 0.20})
        c3 = {}
        MainWindow._migrate_cover_title_pos(c3)
        self.assertEqual(c3, {})


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
        self.assertAlmostEqual(intro_spans["Sigma"][0], toc_spans["1. One"][0])
        self.assertAlmostEqual(intro_spans["Sigma"][1][1], toc_spans["1. One"][1][1])
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

    def test_intro_section_path_header_splits_lines(self):
        # 部类/刊本分组标题含路径（" / "）时每段独立成行（用目录条目字体）
        out = self.dir / "intro-path" / "intro.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        _intro_pdf(
            {"title": "Intro", "summary": [],
             "sections": [("13 中觀部類 / 三論宗 / 肇論／疏", ["T1858 肇論"])]},
            self.srcs[0], out, config={},
        )
        page = pymupdf.open(out)[0]
        texts = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                t = "".join(span["text"] for span in line.get("spans", [])).strip()
                if t:
                    texts.append(t)
        self.assertIn("13 中觀部類", texts)
        self.assertIn("三論宗", texts)
        self.assertIn("肇論／疏", texts)

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

    def test_cover_group_path_splits_levels(self):
        # 封面：collection_name 形如「丛书｜部类 / 刊本 / 子目」时，分组路径每段一行，
        # 字体字号沿用目录条目（远小于封面标题）。
        import copy
        from cbeta_publish.books.ebook_merger import _cover_pdf
        c = copy.deepcopy(COVER)
        c["mode"] = "reading"
        p = self.dir / "group" / "c.pdf"
        p.parent.mkdir(parents=True, exist_ok=True)
        _cover_pdf(self.srcs[0], "測試叢書｜13 中觀部類 / 三論宗 / 肇論／疏",
                   p, organizer="編", config=c)
        spans = []
        for b in pymupdf.open(p)[0].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip():
                        spans.append((s["text"].strip(), s["size"]))
        texts = [t for t, _ in spans]
        for lv in ("13 中觀部類", "三論宗", "肇論／疏"):
            self.assertIn(lv, texts)
        title_sz = next(sz for t, sz in spans if t == "測試叢書")
        lv_sz = next(sz for t, sz in spans if t == "三論宗")
        self.assertLess(lv_sz, title_sz)   # 分组行用目录条目字号

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


class CoverNumberedImageTest(unittest.TestCase):
    """封面图编号约定：1.*=封面图（前）/2.*=封底图（后），后缀不限；
    显式配置有效优先，否则 images/ → default/。"""

    def test_find_numbered_any_suffix(self):
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            (d / "1.tif").write_bytes(b"x")
            (d / "2.JPG").write_bytes(b"x")
            (d / "3.png").write_bytes(b"x")
            (d / "note.txt").write_bytes(b"x")
            self.assertEqual(m.find_numbered_image(d, "1"), d / "1.tif")
            self.assertEqual(m.find_numbered_image(d, "2"), d / "2.JPG")
            self.assertIsNone(m.find_numbered_image(d, "9"))
            self.assertIsNone(m.find_numbered_image(d / "nope", "1"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_resolve_prefers_explicit_then_numbered(self):
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            (d / "1.png").write_bytes(b"x")
            exp = d / "custom.jpg"
            exp.write_bytes(b"x")
            cfg = {"buddha": {"file": str(exp), "enabled": True},
                   "weituo": {"file": "", "enabled": True}}
            # 打补丁只改目录：显式优先
            self.assertEqual(m.resolve_cover_image(cfg, "buddha"), exp)
            # weituo 无显式 → 编号（换目录隔离）
            real_imgs = m.IMAGES_DIR
            m.IMAGES_DIR = d
            try:
                got = m.resolve_cover_image({"weituo": {"file": "", "enabled": True}}, "weituo")
                self.assertIsNone(got)  # d 下只有 1.*，weituo 要 2.*
                got2 = m.resolve_cover_image({"buddha": {"file": "", "enabled": True}}, "buddha")
                self.assertEqual(got2, d / "1.png")
                off = m.resolve_cover_image({"buddha": {"file": "", "enabled": False}}, "buddha")
                self.assertIsNone(off)
            finally:
                m.IMAGES_DIR = real_imgs
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_resolve_real_defaults(self):
        # 仓内默认对：images/1.tif（封面）/2.tif（封底）必须能解出
        from cbeta_publish.books import ebook_merger as m
        f1 = m.resolve_cover_image({}, "buddha")
        f2 = m.resolve_cover_image({}, "weituo")
        self.assertTrue(f1 is not None and f1.is_file(), f1)
        self.assertTrue(f2 is not None and f2.is_file(), f2)
        self.assertEqual(f1.stem, "1")
        self.assertEqual(f2.stem, "2")


class ImageEmbedNoRecodeTest(unittest.TestCase):
    """图片直接嵌入不转码：JPEG 原字节 DCT 直通；tif 尺寸一致无损。"""

    def test_jpg_passthrough_dct(self):
        import pymupdf
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            try:
                from PIL import Image as _PILImage
            except ImportError:
                self.skipTest("no PIL")
            _PILImage.new("RGB", (64, 48), (200, 30, 30)).save(d / "t.jpg", "JPEG")
            src = d / "a.pdf"
            p = pymupdf.open()
            p.new_page(width=595, height=842)
            p.save(src)
            p.close()
            out = d / "img.pdf"
            m._image_pdf(src, d / "t.jpg", out)
            doc = pymupdf.open(out)
            imgs = doc[0].get_images(full=True)
            self.assertEqual(len(imgs), 1)
            filt = doc.xref_get_key(imgs[0][0], "Filter")
            self.assertIn("DCTDecode", str(filt))
            self.assertEqual((imgs[0][2], imgs[0][3]), (64, 48))
            doc.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_tif_embeds_same_size(self):
        import pymupdf
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            src = d / "a.pdf"
            p = pymupdf.open()
            p.new_page(width=595, height=842)
            p.save(src)
            p.close()
            tif = Path("assets/images/1.tif")
            if not tif.is_file():
                self.skipTest("no images/1.tif")
            with pymupdf.open(tif) as im:
                iw, ih = im[0].rect.width, im[0].rect.height
            out = d / "img.pdf"
            m._image_pdf(src, tif, out)
            doc = pymupdf.open(out)
            imgs = doc[0].get_images(full=True)
            self.assertEqual(len(imgs), 1)
            self.assertEqual((imgs[0][2], imgs[0][3]), (int(iw), int(ih)))
            doc.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


class EditNoteTest(unittest.TestCase):
    """编辑说明：TXT 解析、PDF/EPUB 渲染、合并接线（说明页之前、仅首组由调用方控制）。"""

    def _txt(self, d, text=""):
        p = d / "note.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_parse_tags_and_title(self):
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            p = self._txt(d, "<title>編者序\n<h1>凡例</h1>\n\n<center><h2>卷上</h2>\n"
                             "<b>重點</b>\n正文行\n<right>落款</right>\n")
            r = m.parse_editnote_file(p)
            self.assertEqual(r["title"], "編者序")
            self.assertEqual(r["lines"],
                             [("h1", "left", "凡例"), ("gap", "left", ""),
                              ("h2", "center", "卷上"), ("b", "left", "重點"),
                              ("body", "left", "正文行"), ("body", "right", "落款")])
            self.assertIsNone(m.parse_editnote_file(d / "nope.txt"))
            e = self._txt(d, "\n\n")
            self.assertIsNone(m.parse_editnote_file(e))
            t = self._txt(d, "只有正文\n")
            r2 = m.parse_editnote_file(t)
            self.assertEqual(r2["title"], "编辑说明")  # 无 title 行取默认
            self.assertEqual(r2["lines"], [("body", "left", "只有正文")])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_trailing_align_close(self):
        # 行尾 </center>/</right> 被消费不漏进正文；对齐以前缀为准
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            p = self._txt(d, "<title>T\n<center><h5>題</h5></center>\n"
                             "<right><b>款</b></right>\n正文</center>\n")
            r = m.parse_editnote_file(p)
            self.assertEqual(r["lines"],
                             [("h5", "center", "題"),
                              ("b", "right", "款"),
                              ("body", "left", "正文")])
            # 纯标签残留行（单独的 <center>/</center>）直接跳过，不占行
            p2 = self._txt(d, "<title>T\n甲\n<center>\n</center>\n乙\n")
            r2 = m.parse_editnote_file(p2)
            self.assertEqual(r2["lines"],
                             [("body", "left", "甲"),
                              ("body", "left", "乙")])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pb_marker_parse(self):
        # <pb>/<pb/> 独占一行（大小写不限）为分页标记；行内夹字不认；
        # 纯 mark 文件视同无内容
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            p = self._txt(d, "<title>T\n甲\n<pb>\n<PB/>\n乙<pb>丙\n")
            r = m.parse_editnote_file(p)
            self.assertEqual(r["lines"],
                             [("body", "left", "甲"), ("pb", "left", ""),
                              ("pb", "left", ""), ("body", "left", "乙<pb>丙")])
            self.assertIsNone(m.parse_editnote_file(
                self._txt(d, "<title>T\n\n<pb>\n")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_pb_breaks(self):
        # PDF <pb> 真分页；首行/尾部/连续 mark 不多页
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            cfg = {"styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}

            def pages_of(text):
                p = self._txt(d, text)
                e = d / "en.pdf"
                n = m._editnote_pdf(m.parse_editnote_file(p), a, e, config=cfg)
                doc = pymupdf.open(e)
                ts = [pg.get_text().replace("\x00", "") for pg in doc]
                doc.close()
                return n, ts

            n, ts = pages_of("<title>T\n甲\n<pb>\n乙\n")
            self.assertEqual(n, 2)
            self.assertIn("甲", ts[0])
            self.assertNotIn("乙", ts[0])
            self.assertIn("乙", ts[1])
            # 首行/尾部/连续 mark 不产生空白页
            self.assertEqual(pages_of("<title>T\n<pb>\n甲\n")[0], 1)
            self.assertEqual(pages_of("<title>T\n甲\n<pb>\n")[0], 1)
            self.assertEqual(pages_of("<title>T\n甲\n<pb>\n<pb>\n乙\n")[0], 2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_renders_before_intro_order(self):
        # 编辑说明 PDF 在说明页之前：front 顺序 + 书签都有
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842).insert_text((100, 100), "A")
            doc.save(a)
            doc.close()
            p = self._txt(d, "<title>編者序\n<h1>凡例</h1>\n正文\n")
            parsed = m.parse_editnote_file(p)
            intro = {"title": "说明", "summary": ["共 1 部"], "sections": []}
            out = d / "out" / "m.pdf"
            out.parent.mkdir(parents=True, exist_ok=True)
            cfg = {"mode": "reading", "enabled": True,
                   "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}
            parts = m.merge_pdfs([a], out, titles=["A"], collection_name="c",
                                 organizer="x", cover_config=cfg, intro=intro,
                                 editnote=parsed)
            self.assertEqual(len(parts), 1)
            doc = pymupdf.open(parts[0])
            toc = [t[1] for t in doc.get_toc()]
            self.assertIn("編者序", toc)
            self.assertIn("说明", toc)
            self.assertLess(toc.index("編者序"), toc.index("说明"))
            doc.close()
            # 无 editnote 时旧行为不变（无此书签）
            out2 = d / "out" / "m2.pdf"
            parts2 = m.merge_pdfs([a], out2, titles=["A"], collection_name="c",
                                  organizer="x", cover_config=cfg, intro=intro)
            doc2 = pymupdf.open(parts2[0])
            self.assertNotIn("編者序", [t[1] for t in doc2.get_toc()])
            doc2.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_spaces_and_gaps_preserved(self):
        # 行首空格与空行保留：缩进行原样，连续空行不断
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            p = self._txt(d, "<h1>题</h1>\n    缩进两字\n\n\n下段\n")
            r = m.parse_editnote_file(p)
            self.assertEqual(r["lines"],
                             [("h1", "left", "题"),
                              ("body", "left", "    缩进两字"),
                              ("gap", "left", ""), ("gap", "left", ""),
                              ("body", "left", "下段")])
            # 全角空格（中文常用缩进）与制表符同样保留（制表按 4 空格展开）
            p2 = self._txt(d, "　　全角缩进\n\tTAB缩进\n")
            r2 = m.parse_editnote_file(p2)
            self.assertEqual(r2["lines"],
                             [("body", "left", "　　全角缩进"),
                              ("body", "left", "    TAB缩进")])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_tagged_indent_rules(self):
        # 标签行空格规则：标签后半角空格是分隔符（去掉），全角/制表是缩进（保留）；
        # 标签前的空白一律保留；h1–h5 均为分级标题
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            p = self._txt(d, "<title>T\n<h1>凡例</h1>\n<h1> 分隔符</h1>\n"
                             "<h1>　全角缩进</h1>\n<h2>\tTAB缩进</h2>\n"
                             "  <b>标签前缩进</b>\n<b>重点</b>\n"
                             "<h4>四级</h4>\n<h5>五级</h5>\n")
            r = m.parse_editnote_file(p)
            self.assertEqual(r["lines"],
                             [("h1", "left", "凡例"),
                              ("h1", "left", "分隔符"),
                              ("h1", "left", "　全角缩进"),
                              ("h2", "left", "    TAB缩进"),
                              ("b", "left", "  标签前缩进"),
                              ("b", "left", "重点"),
                              ("h4", "left", "四级"),
                              ("h5", "left", "五级")])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_heading_size_ladder(self):
        # PDF：h1–h5 字号逐级缩小（相对 h1：1/0.85/0.8/0.7/0.6），h5 仍大于正文
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            p = self._txt(d, "<title>T\n<h1>一</h1>\n<h2>二</h2>\n<h3>三</h3>\n"
                             "<h4>四</h4>\n<h5>五</h5>\n正文六\n")
            parsed = m.parse_editnote_file(p)
            e = d / "en.pdf"
            m._editnote_pdf(parsed, a, e, config={
                "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                           "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}})
            doc = pymupdf.open(e)
            sizes = {}
            for b in doc[0].get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        for key in ("一", "二", "三", "四", "五", "正文六"):
                            if key in s.get("text", ""):
                                sizes[key] = round(s.get("size", 0), 1)
            doc.close()
            self.assertEqual(set(sizes),
                             {"一", "二", "三", "四", "五", "正文六"})
            h1 = sizes["一"]
            for key, ratio in (("一", 1.0), ("二", 0.85), ("三", 0.8),
                               ("四", 0.7), ("五", 0.6)):
                self.assertAlmostEqual(sizes[key] / h1, ratio, delta=0.02,
                                       msg=key)
            self.assertGreater(sizes["五"], sizes["正文六"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_latn_fallback_roundtrip(self):
        # PDF：梵文转写 ā/ś/ṛ 等不画成空白（无 U+0000），行精确回读；
        # 拉丁回退字体嵌入（中西文混排分 run 绘制）
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            line = ("《大乘起信论》，梵文Mahāyāna śraddhotpada śāstra，"
                    "又称《起信论》")
            p = self._txt(d, "<title>T\n" + line + "\n")
            parsed = m.parse_editnote_file(p)
            e = d / "en.pdf"
            m._editnote_pdf(parsed, a, e, config={
                "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                           "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}})
            doc = pymupdf.open(e)
            texts = doc[0].get_text().split("\n")
            self.assertIn(line, texts)
            self.assertNotIn(chr(0), "".join(texts))
            fonts = {f[3].split("+")[-1] for f in doc[0].get_fonts()}
            self.assertTrue({"SimHei"} <= fonts)
            # 回退字体确有其名（Tahoma/Arial/Segoe UI/雅黑/Noto 之一）
            self.assertTrue(any(n.startswith(p) for n in fonts for p in
                                ("Tahoma", "Arial", "SegoeUI",
                                 "MicrosoftYaHei", "NotoSans")))
            # 词间距均匀（无被缺字形撑宽的空格）
            ws = [w for w in doc[0].get_text("words") if "大乘" in w[4] or "梵文" in w[4] or "stra" in w[4] or "raddhotpada" in w[4]]
            gaps = [ws[i + 1][0] - ws[i][2] for i in range(len(ws) - 1)]
            self.assertGreater(len(gaps), 0)
            self.assertLess(max(gaps) - min(gaps), 1.0)
            doc.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_intro_toc_bg_painted_all_pages(self):
        # 说明/目录背景色：显式色每页都刷；缺省跟随封面 background
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            cfg = {"styles": {
                "intro_background": {"color": [10, 20, 30]},
                "toc_background": {"color": [40, 50, 60]},
                "toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}
            secs = [("G%d" % i, ["r%d" % j for j in range(30)]) for i in range(6)]
            ip = d / "intro.pdf"
            self.assertGreater(m._intro_pdf(
                {"title": "说明", "summary": [], "sections": secs},
                a, ip, config=cfg), 1)
            for pg in pymupdf.open(ip):
                r, g, b = pg.get_pixmap(dpi=20).pixel(2, 2)
                self.assertTrue(abs(r - 10) <= 2 and abs(g - 20) <= 2
                                and abs(b - 30) <= 2)
            tp = d / "toc.pdf"
            m._toc_pdf(["T%04d" % i for i in range(120)], a, tp, config=cfg)
            tdoc = pymupdf.open(tp)
            self.assertGreater(len(tdoc), 1)
            for pg in tdoc:
                r, g, b = pg.get_pixmap(dpi=20).pixel(2, 2)
                self.assertTrue(abs(r - 40) <= 2 and abs(g - 50) <= 2
                                and abs(b - 60) <= 2)
            # 缺省链：无 intro/toc 键 → 跟随封面 background；全无 → 米色
            self.assertEqual(m._page_bg({}, "intro_background"), [250, 245, 230])
            self.assertEqual(
                m._page_bg({"styles": {"background": {"color": [1, 2, 3]}}},
                           "toc_background"), [1, 2, 3])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_body_uses_base_size(self):
        # PDF 编辑说明正文用独立字号（sizes.editnote_body，缺省 12，不跟页面基准）
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            p = self._txt(d, "<title>T\n正文行\n")
            parsed = m.parse_editnote_file(p)
            cfg = {"sizes": {"body_a4": 16},
                   "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}

            def body_size(config):
                e = d / "en.pdf"
                m._editnote_pdf(parsed, a, e, config=config)
                doc = pymupdf.open(e)
                out = None
                for b in doc[0].get_text("dict")["blocks"]:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            if "正文行" in s.get("text", ""):
                                out = round(s.get("size", 0), 1)
                doc.close()
                return out
            self.assertEqual(body_size(cfg), 12.0)   # 缺省 12（body_a4=16 不影响）
            cfg2 = dict(cfg)
            cfg2["sizes"] = {"body_a4": 16, "editnote_body": 18}
            self.assertEqual(body_size(cfg2), 18.0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_heading_indent_rendered(self):
        # PDF：<h1> 全角缩进随行保留，且与汉字同字体绘制（真全角占幅；
        # 全角空格含在词内故 x0 与平首行相同，不能用 x0 断言）
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            p = self._txt(d, "<title>T\n<h1>平标题</h1>\n<h1>　缩进标题</h1>\n")
            parsed = m.parse_editnote_file(p)
            e = d / "en.pdf"
            m._editnote_pdf(parsed, a, e, config={
                "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                           "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}})
            doc = pymupdf.open(e)
            spans = {}
            for b in doc[0].get_text("dict")["blocks"]:
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        for key in ("平标题", "缩进标题"):
                            if key in s.get("text", ""):
                                spans[key] = s
            doc.close()
            self.assertEqual(set(spans), {"平标题", "缩进标题"})
            self.assertTrue(spans["缩进标题"]["text"].startswith("　"))
            # 同一字体绘制汉字与全角空格 ⇒ 缩进占幅真实
            self.assertEqual(spans["缩进标题"]["font"], spans["平标题"]["font"])
            self.assertNotEqual(spans["缩进标题"]["font"], "")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_gap_survives_page_break(self):
        # PDF：空行恰在分页边界时不被吞（换页后仍保留空白高度）
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            cfg = {"styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}

            def h1_page_y(nfill, gap):
                lines = (["<title>T"] +
                         ["filler%03d padding text" % i for i in range(nfill)] +
                         ([""] if gap else []) + ["<h1>Target</h1>"])
                p = self._txt(d, "\n".join(lines) + "\n")
                parsed = m.parse_editnote_file(p)
                e = d / "en.pdf"
                m._editnote_pdf(parsed, a, e, config=cfg)
                found = None
                doc = pymupdf.open(e)
                for pi in range(len(doc)):
                    for b in doc[pi].get_text("dict")["blocks"]:
                        for l in b.get("lines", []):
                            t = "".join(s["text"] for s in l["spans"])
                            if "Target" in t:
                                found = (pi + 1, round(l["bbox"][1], 1))
                doc.close()
                return found
            pair = None
            for n in range(25, 60):
                nogap = h1_page_y(n, False)
                withgap = h1_page_y(n, True)
                if (nogap and withgap and nogap[0] == withgap[0] == 2):
                    pair = (nogap, withgap)
                    break
            self.assertIsNotNone(pair, "no page-break boundary found in scan")
            # 有空行版本标题更靠下（差值即一个空行高度），不是顶格
            self.assertGreater(pair[1][1] - pair[0][1], 5.0)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_pdf_indent_rendered(self):
        # PDF 行首缩进真实绘制：缩进行首词 x0 大于平首行；全角空格随词保留
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842)
            doc.save(a)
            doc.close()
            p = self._txt(d, "<title>T\n平首行\n    半角缩进\n　　全角缩进\n")
            parsed = m.parse_editnote_file(p)
            e = d / "en.pdf"
            m._editnote_pdf(parsed, a, e, config={
                "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                           "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}})
            doc = pymupdf.open(e)
            x0 = {}
            for w in doc[0].get_text("words"):
                for key in ("平首行", "半角缩进", "全角缩进"):
                    if key in w[4]:
                        x0[key] = (w[0], w[4])
            doc.close()
            self.assertEqual(set(x0), {"平首行", "半角缩进", "全角缩进"})
            self.assertGreater(x0["半角缩进"][0], x0["平首行"][0])
            # 全角空格是实体字形：随词保留在文本串前端（占幅已体现在字形 advances）
            self.assertTrue(x0["全角缩进"][1].startswith("　　"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_multipage_editnote_bookmarks_exact(self):
        # 多页编辑说明：说明/目录/正文书签精确指向内容页（非常规文件序号）；
        # 打印模式说明落奇数页、无多余空白页
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842).insert_text((100, 100), "BODY-A")
            doc.save(a)
            doc.close()
            lines = ["<title>編者序"] + \
                ["说明正文第%02d行内容填充" % i for i in range(1, 80)]
            p = self._txt(d, "\n".join(lines) + "\n")
            parsed = m.parse_editnote_file(p)
            intro = {"title": "说明", "summary": ["共 1 部"], "sections": []}
            out = d / "out" / "m.pdf"
            out.parent.mkdir(parents=True, exist_ok=True)
            cfg = {"mode": "print", "enabled": True,
                   "images": {"buddha": {"enabled": False},
                              "weituo": {"enabled": False}},
                   "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}
            parts = m.merge_pdfs([a], out, titles=["A經"], collection_name="c",
                                 organizer="x", cover_config=cfg, intro=intro,
                                 editnote=parsed)
            self.assertEqual(len(parts), 1)
            doc = pymupdf.open(parts[0])
            texts = [pg.get_text() for pg in doc]
            bm = {t[1]: t[2] for t in doc.get_toc()}

            def page_of(marker):
                return next(i + 1 for i, t in enumerate(texts) if marker in t)
            # 书签页即内容页（精确相等，不是估算）
            self.assertEqual(bm["編者序"], page_of("編者序"))
            self.assertEqual(bm["说明"], page_of("共 1 部"))
            self.assertEqual(bm["目录"], page_of("目录"))
            self.assertEqual(bm["A經"], page_of("BODY-A"))
            # 打印模式：说明/目录/正文均从奇数页起
            self.assertEqual(bm["说明"] % 2, 1)
            self.assertEqual(bm["目录"] % 2, 1)
            self.assertEqual(bm["A經"] % 2, 1)
            # 目录页印的正文页码与书签一致；目录内链跳到同一页
            self.assertIn(str(bm["A經"]), texts[bm["目录"] - 1])
            gotos = [l["page"] + 1 for pg in doc for l in pg.get_links()
                     if l["kind"] == 1]
            self.assertIn(bm["A經"], gotos)
            doc.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_intro_starts_on_odd_page(self):
        # 打印模式：编辑说明后仍保证说明页从奇数页起；书签页码随之正确
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842).insert_text((100, 100), "A")
            doc.save(a)
            doc.close()
            p = self._txt(d, "<title>編者序\n<h1>凡例</h1>\n正文\n")
            parsed = m.parse_editnote_file(p)
            intro = {"title": "说明", "summary": ["共 1 部"], "sections": []}
            out = d / "out" / "m.pdf"
            out.parent.mkdir(parents=True, exist_ok=True)
            cfg = {"mode": "print", "enabled": True,
                   "styles": {"toc_title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf"}}}
            parts = m.merge_pdfs([a], out, titles=["A"], collection_name="c",
                                 organizer="x", cover_config=cfg, intro=intro,
                                 editnote=parsed)
            doc = pymupdf.open(parts[0])
            toc = {t[1]: t[2] for t in doc.get_toc()}
            self.assertIn("说明", toc)
            self.assertEqual(toc["说明"] % 2, 1)   # 奇数页起
            self.assertIn("編者序", toc)
            self.assertLess(toc["編者序"], toc["说明"])
            doc.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


class CoverDateTextTest(unittest.TestCase):
    """封面日期行：缺省{date}=今天；可写任意文字；留空不绘制；整理者与日期同字体。"""

    def test_resolve_cover_date(self):
        import datetime
        from cbeta_publish.books import ebook_merger as m
        today = datetime.date.today().isoformat()
        self.assertEqual(m._resolve_cover_date({}), today)
        self.assertEqual(m._resolve_cover_date({"date_text": "{date}"}), today)
        self.assertEqual(m._resolve_cover_date({"date_text": "丙午年秋"}), "丙午年秋")
        self.assertEqual(m._resolve_cover_date({"date_text": "印行於 {date}"}),
                         f"印行於 {today}")
        self.assertEqual(m._resolve_cover_date({"date_text": ""}), "")
        self.assertEqual(m._resolve_cover_date({"date_text": "   "}), "")

    def _cover_text(self, date_text):
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842).insert_text((100, 100), "A")
            doc.save(a)
            doc.close()
            out = d / "o.pdf"
            cfg = {"enabled": True, "organizer": "測試整理",
                   "imprint": "測試系列", "date_text": date_text,
                   "styles": {"title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "organizer": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "date": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "cbeta": {"font": "C:/Windows/Fonts/simhei.ttf"}}}
            m._cover_pdf(a, "測試書", out, organizer="測試整理", config=cfg)
            doc = pymupdf.open(out)
            txt = "\n".join(p.get_text() for p in doc)
            doc.close()
            return txt
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_custom_date_rendered(self):
        self.assertIn("丙午年秋", self._cover_text("丙午年秋"))

    def test_empty_date_skipped(self):
        import datetime
        txt = self._cover_text("")
        self.assertNotIn(datetime.date.today().isoformat(), txt)

    def test_organizer_uses_date_font(self):
        # 整理者行与日期行字体一致：取两行 span 的嵌入字体名（去子集前缀）断言相等
        import tempfile
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.pdf"
            doc = pymupdf.open()
            doc.new_page(width=595, height=842).insert_text((100, 100), "A")
            doc.save(a)
            doc.close()
            out = d / "o.pdf"
            cfg = {"enabled": True, "organizer": "測試整理",
                   "imprint": "測試系列", "date_text": "丙午年秋",
                   "styles": {"title": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "organizer": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "date": {"font": "C:/Windows/Fonts/simhei.ttf"},
                              "cbeta": {"font": "C:/Windows/Fonts/simhei.ttf"}}}
            m._cover_pdf(a, "測試書", out, organizer="測試整理", config=cfg)
            doc = pymupdf.open(out)
            fonts = {}

            def base(n):
                return n.split("+", 1)[-1] if "+" in n else n
            for p in doc:
                for b in p.get_text("dict")["blocks"]:
                    for l in b.get("lines", []):
                        for s in l.get("spans", []):
                            t = s.get("text", "")
                            if "測試整理" in t:
                                fonts["org"] = base(s.get("font", ""))
                            if "丙午年秋" in t:
                                fonts["date"] = base(s.get("font", ""))
            doc.close()
            self.assertIn("org", fonts)
            self.assertIn("date", fonts)
            self.assertEqual(fonts["org"], fonts["date"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class CoverWrapTest(unittest.TestCase):
    """封面标题优先断点折行（mock 字宽：CJK=10，ASCII=5）。"""

    def _w(self, s):
        return sum(10 if ord(c) > 127 else 5 for c in s)

    def test_break_before_paren(self):
        from cbeta_publish.books.ebook_merger import _wrap_cjk_lines
        got = _wrap_cjk_lines("《藏要》第一辑（十一经三律十一论）", self._w, 100)
        self.assertEqual(got, ["《藏要》第一辑", "（十一经三律十一论）"])

    def test_break_after_ideographic_comma(self):
        from cbeta_publish.books.ebook_merger import _wrap_cjk_lines
        got = _wrap_cjk_lines("甲、乙、丙丁戊己庚", self._w, 60)
        self.assertEqual(got[0], "甲、乙、")
        self.assertTrue(all(g for g in got))

    def test_no_break_before_closing(self):
        # 行首不留 `）`
        from cbeta_publish.books.ebook_merger import _wrap_cjk_lines
        got = _wrap_cjk_lines("甲乙丙丁戊）己", self._w, 55)
        self.assertFalse(any(g.startswith("）") for g in got))

    def test_em_dash_kept_together(self):
        # 破折号对不断开：每行含偶数个 `—`
        from cbeta_publish.books.ebook_merger import _wrap_cjk_lines
        got = _wrap_cjk_lines("甲乙——丙丁戊己庚", self._w, 55)
        self.assertTrue(all(g.count("—") % 2 == 0 for g in got))
        self.assertEqual("".join(got).count("—"), 2)

    def test_fits_single_line(self):
        from cbeta_publish.books.ebook_merger import _wrap_cjk_lines
        self.assertEqual(_wrap_cjk_lines("甲乙", self._w, 100), ["甲乙"])
        self.assertEqual(_wrap_cjk_lines("", self._w, 100), [])


if __name__ == "__main__":
    unittest.main()
