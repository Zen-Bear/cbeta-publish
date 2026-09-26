# -*- coding: utf-8 -*-
"""EPUB 合并：封面、排除源自带页、书签、临时目录清理。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from ebooklib import epub

from cbeta_publish.books.ebook_merger import merge_epubs


def make_src(path: Path, stem: str, juans: int = 1):
    b = epub.EpubBook()
    b.set_identifier(stem)
    b.set_title(stem)
    b.set_language("zh")
    css = epub.EpubItem(uid="css", file_name="cbeta.css",
                        media_type="text/css", content=b"body{}")
    b.add_item(css)
    img = epub.EpubItem(uid="coverimg", file_name="images/cover.jpg",
                        media_type="image/jpeg", content=b"\xff\xd8\xff\xd9")
    b.add_item(img)
    items = []
    for name in ("titlepage", "toc", "front"):
        it = epub.EpubHtml(title=name, file_name=f"{name}.xhtml", lang="zh")
        it.content = f"<html><body><h1>{name}</h1></body></html>"
        b.add_item(it)
        items.append(it)
    for i in range(1, juans + 1):
        it = epub.EpubHtml(title=f"juan{i}", file_name=f"juans/{i:03d}.xhtml", lang="zh")
        it.content = f"<html><body><p>{stem} juan {i}</p></body></html>"
        b.add_item(it)
        items.append(it)
    back = epub.EpubHtml(title="back", file_name="back.xhtml", lang="zh")
    back.content = "<html><body><p>back</p></body></html>"
    b.add_item(back)
    items.append(back)
    b.add_item(epub.EpubNcx())
    b.add_item(epub.EpubNav())
    b.spine = ["nav"] + items
    b.toc = tuple(items)
    epub.write_epub(str(path), b)


class MergeEpubTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.a = cls.dir / "A.epub"
        cls.bb = cls.dir / "B.epub"
        make_src(cls.a, "A", juans=1)
        make_src(cls.bb, "B", juans=2)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _merge(self):
        out = self.dir / "out" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            organizer="编者", titles=["甲", "乙"])
        self.assertEqual(len(parts), 1)
        return parts[0]

    def test_cover_first_and_sources_excluded(self):
        book = epub.read_epub(str(self._merge()))
        ids = [getattr(s, "get_id", lambda: s)() for s in book.spine]
        ids = [x[0] if isinstance(x, tuple) else x for x in ids]
        names = [it.get_name() for it in book.get_items()]
        # 封面 + nav + A(封面页+编辑说明+1卷) + B(封面页+2卷+后记)
        self.assertEqual(ids[0], "chapter_0")
        self.assertEqual(ids[1], "nav")
        self.assertEqual(len(ids), 9)
        # 保留每本封面页(titlepage)，排除每本目录
        self.assertTrue(any(n.endswith("titlepage.xhtml") for n in names), names)
        self.assertFalse(any(n.endswith("toc.xhtml") for n in names), names)
        # 编辑说明只保留第一本，后记只保留最后一本
        fronts = [n for n in names if n.endswith("front.xhtml")]
        self.assertEqual(fronts, ["A/front.xhtml"], fronts)
        backs = [n for n in names if n.endswith("back.xhtml")]
        self.assertEqual(backs, ["B/back.xhtml"], backs)

    def test_resources_and_relative_paths(self):
        import zipfile
        out = self._merge()
        book = epub.read_epub(str(out))
        names = {it.get_name() for it in book.get_items()}
        # 样式与封面图保留，且加书前缀以维持相对路径
        self.assertTrue(any(n.endswith("cbeta.css") for n in names))
        self.assertTrue(any(n.endswith("images/cover.jpg") for n in names))
        # 正文重新挂上本册样式表链接
        z = zipfile.ZipFile(out)
        juan = next(n for n in z.namelist() if n.endswith("juans/001.xhtml"))
        raw = z.read(juan).decode("utf-8", "replace")
        self.assertIn("cbeta.css", raw)

    def test_toc_bookmarks_per_work(self):
        book = epub.read_epub(str(self._merge()))
        links = []

        def walk(t):
            for x in t:
                if isinstance(x, tuple):
                    walk(x[1])
                else:
                    links.append((x.title, x.href))

        walk(book.toc)
        self.assertEqual([t for t, _ in links], ["封面", "丛书目录", "1. 甲", "2. 乙"])

    def test_font_fallback_prefers_black_before_song(self):
        from cbeta_publish.books import ebook_merger

        self.assertEqual(
            ebook_merger._FALLBACK_FONTS,
            [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
            ],
        )

    def test_collection_cover_styled(self):
        import zipfile
        out = self._merge()
        z = zipfile.ZipFile(out)
        cover = z.read("EPUB/cover.xhtml").decode("utf-8", "replace")
        # 丛书封面自包含内联样式，不依赖页高类 CSS，不重叠
        self.assertIn("margin-top:1.5em", cover)
        self.assertIn("margin-top:19em", cover)
        self.assertNotIn("margin-top:20.5em", cover)
        self.assertIn("text-align:center", cover)
        self.assertIn("丛书", cover)
        self.assertIn("编者", cover)
        self.assertNotIn("position:absolute", cover)
        nav = z.read("EPUB/nav.xhtml").decode("utf-8", "replace")
        self.assertIn("cover.css", nav)

    def test_toc_page(self):
        import zipfile
        out = self._merge()
        z = zipfile.ZipFile(out)
        nav = z.read("EPUB/nav.xhtml").decode("utf-8", "replace")
        self.assertIn("丛书目录", nav)
        css = z.read("EPUB/cover.css").decode("utf-8", "replace")
        self.assertIn("margin-top:3em", css)
        self.assertIn("margin-left:2em", css)
        self.assertIn("text-decoration:none", css.replace(" ", ""))
        self.assertIn("font-weight:bold", css.replace(" ", ""))
        self.assertIn("margin-bottom", css)

    def test_split_items(self):
        # 小阈值触发分册；0 表示不分册
        out = self.dir / "split" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            organizer="编者", titles=["甲", "乙"], split_items=1)
        self.assertGreater(len(parts), 1)
        out2 = self.dir / "nosplit" / "col.epub"
        out2.parent.mkdir(parents=True, exist_ok=True)
        parts2 = merge_epubs([self.a, self.bb], out2, collection_name="丛书",
                             organizer="编者", titles=["甲", "乙"], split_items=0)
        self.assertEqual(len(parts2), 1)

    def _merge_bare(self):
        out = self.dir / "outbare" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            organizer="编者", titles=["甲", "乙"],
                            cover_config={"enabled": False})
        self.assertEqual(len(parts), 1)
        return parts[0]

    def test_bare_no_cover_and_nested_toc(self):
        # 关闭封面/封底：纯拼接，不删除不增加任何内容页，无目录页；
        # 书签（侧边栏）：每书一条，原书目录降一级嵌套
        book = epub.read_epub(str(self._merge_bare()))
        names = [it.get_name() for it in book.get_items()]
        self.assertFalse(any(n.endswith("cover.xhtml") for n in names), names)
        self.assertTrue(any(n.endswith("A/titlepage.xhtml") for n in names), names)
        self.assertTrue(any(n.endswith("A/toc.xhtml") for n in names), names)
        self.assertTrue(any(n.endswith("A/front.xhtml") for n in names), names)
        self.assertTrue(any(n.endswith("B/back.xhtml") for n in names), names)
        ids = [getattr(s, "get_id", lambda: s)() for s in book.spine]
        ids = [x[0] if isinstance(x, tuple) else x for x in ids]
        self.assertNotIn("nav", ids)
        links = []

        def walk(t, depth=0):
            for x in t:
                if isinstance(x, tuple):
                    walk([x[0]], depth)
                    walk(x[1], depth + 1)
                else:
                    links.append((depth, x.title, x.href))

        walk(book.toc)
        top = [l for l in links if l[0] == 0]
        self.assertEqual([t for _, t, _ in top], ["1. 甲", "2. 乙"])
        kids = [l for l in links if l[0] == 1]
        self.assertTrue(any(h.startswith("A/") for _, _, h in kids), kids)
        self.assertTrue(any(h.startswith("B/") for _, _, h in kids), kids)

    def test_bare_no_intro(self):
        # 裸合并不增加说明页
        out = self.dir / "outbare2" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            titles=["甲", "乙"], cover_config={"enabled": False},
                            intro={"title": "说明", "summary": ["x"], "sections": []})
        import zipfile
        names = zipfile.ZipFile(parts[0]).namelist()
        self.assertFalse(any(n.endswith("intro.xhtml") for n in names), names)

    def test_cover_mode_intro_before_nav(self):
        out = self.dir / "outintro" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        intro = {"title": "说明", "summary": ["本丛书共收录 2 部"],
                 "sections": [("01 阿含部類（2 部）", ["T0001 長阿含經"])]}
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            organizer="编者", titles=["甲", "乙"], intro=intro)
        import zipfile
        z = zipfile.ZipFile(parts[0])
        self.assertIn("EPUB/intro.xhtml", z.namelist())
        raw = z.read("EPUB/intro.xhtml").decode("utf-8", "replace")
        self.assertIn("说明", raw)
        self.assertIn("T0001", raw)
        book = epub.read_epub(str(parts[0]))
        ids = [getattr(s, "get_id", lambda: s)() for s in book.spine]
        ids = [x[0] if isinstance(x, tuple) else x for x in ids]
        # 封面 -> 说明 -> 目录
        self.assertEqual(ids[0], "chapter_0")
        self.assertEqual(ids[1], "chapter_1")
        self.assertEqual(ids[2], "nav")
        links = []

        def walk(t):
            for x in t:
                if isinstance(x, tuple):
                    walk([x[0]])
                    walk(x[1])
                else:
                    links.append((x.title, x.href))

        walk(book.toc)
        self.assertEqual([t for t, _ in links], ["封面", "丛书目录", "说明", "1. 甲", "2. 乙"])

    def test_cover_config_ratio_and_color(self):
        # E2：EPUB 封面字号取 styles.ratio（em）、颜色取 styles.color；
        # 整理者字号与日期一致（取 date 比率），颜色仍用 organizer 的
        import zipfile
        out = self.dir / "oute2" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        cfg = {"enabled": True, "styles": {
            "title": {"ratio": 3.0, "color": [0, 0, 0]},
            "cbeta": {"ratio": 1.0, "color": [51, 51, 51]},
            "organizer": {"ratio": 1.35, "color": [10, 20, 30]},
            "date": {"ratio": 1.0, "color": [100, 100, 100]},
        }}
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            organizer="编者", titles=["甲", "乙"], cover_config=cfg)
        raw = zipfile.ZipFile(parts[0]).read("EPUB/cover.xhtml").decode("utf-8", "replace")
        self.assertIn("font-size:3.0em", raw)
        self.assertIn("font-size:1.0em", raw)   # 整理者/日期同字号
        self.assertIn("color:#0a141e", raw)     # 整理者颜色不变

    def test_progress_callback_and_cancel(self):
        from cbeta_publish.books.ebook_merger import MergeCancelled
        calls = []
        out = self.dir / "prog" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        merge_epubs([self.a, self.bb], out, collection_name="丛书", organizer="编",
                    titles=["甲", "乙"], cover_config={"enabled": False},
                    progress=lambda d, n, l: (calls.append((d, n, l)), True)[1])
        self.assertEqual([c[0] for c in calls], [1, 2])
        self.assertTrue(all(c[1] == 2 for c in calls))
        with self.assertRaises(MergeCancelled):
            merge_epubs([self.a, self.bb], self.dir / "progc" / "col.epub",
                        collection_name="丛书", organizer="编", titles=["甲", "乙"],
                        cover_config={"enabled": False}, progress=lambda d, n, l: False)

    def test_cover_imprint_configurable(self):
        import zipfile
        out = self.dir / "outimprint" / "col.epub"
        out.parent.mkdir(parents=True, exist_ok=True)
        cfg = {"enabled": True, "imprint": "MY IMPRINT"}
        parts = merge_epubs([self.a, self.bb], out, collection_name="丛书",
                            organizer="编者", titles=["甲", "乙"], cover_config=cfg)
        raw = zipfile.ZipFile(parts[0]).read("EPUB/cover.xhtml").decode("utf-8", "replace")
        self.assertIn("MY IMPRINT", raw)
        self.assertNotIn("CBETA", raw)

    def test_tmp_cover_cleaned(self):
        self.assertFalse((self.dir / "out" / "_tmp_cover").exists())


class MergeEpubEditNoteTest(unittest.TestCase):
    """编辑说明 EPUB：editnote.xhtml 在 intro 之前；toc/spine 顺序正确。"""

    def test_editnote_only_first_part(self):
        # 切散时编辑说明只进第一个合并文件（说明页保持每文件都有）
        from cbeta_publish.books.ebook_merger import parse_editnote_file
        d = Path(tempfile.mkdtemp())
        try:
            t = d / "note.txt"
            t.write_text("<title>編者序\n正文\n", encoding="utf-8")
            parsed = parse_editnote_file(t)
            intro = {"title": "说明", "summary": [], "sections": []}
            a = d / "A.epub"
            b = d / "B.epub"
            make_src(a, "A", juans=1)
            make_src(b, "B", juans=1)
            out = d / "out" / "col.epub"
            out.parent.mkdir(parents=True, exist_ok=True)
            parts = merge_epubs([a, b], out, collection_name="丛书", organizer="编",
                                titles=["甲", "乙"], cover_config={"enabled": True},
                                intro=intro, editnote=parsed, split_items=4)
            self.assertEqual(len(parts), 2)
            n1 = {it.get_name() for it in epub.read_epub(str(parts[0])).get_items()}
            n2 = {it.get_name() for it in epub.read_epub(str(parts[1])).get_items()}
            self.assertIn("editnote.xhtml", n1)
            self.assertNotIn("editnote.xhtml", n2)
            self.assertIn("intro.xhtml", n1)
            self.assertIn("intro.xhtml", n2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_editnote_before_intro(self):
        import zipfile
        from cbeta_publish.books.ebook_merger import parse_editnote_file
        d = Path(tempfile.mkdtemp())
        try:
            t = d / "note.txt"
            t.write_text("<title>編者序\n<h1>凡例</h1>\n<center>卷上</center>\n正文\n",
                         encoding="utf-8")
            parsed = parse_editnote_file(t)
            intro = {"title": "说明", "summary": ["共 1 部"], "sections": []}
            a = d / "A.epub"
            make_src(a, "A", juans=1)
            out = d / "out" / "col.epub"
            out.parent.mkdir(parents=True, exist_ok=True)
            parts = merge_epubs([a], out, collection_name="丛书", organizer="编",
                                titles=["甲"], cover_config={"enabled": True},
                                intro=intro, editnote=parsed)
            self.assertEqual(len(parts), 1)
            book = epub.read_epub(str(parts[0]))
            ids = [getattr(s, "get_id", lambda: s)() for s in book.spine]
            ids = [x[0] if isinstance(x, tuple) else x for x in ids]
            names = [it.get_name() for it in book.get_items()]
            self.assertIn("editnote.xhtml", names)
            # spine：cover → editnote → intro → nav → 正文（按文件名定位）
            id2name = {}
            for it in book.get_items():
                try:
                    id2name[it.get_id()] = it.get_name()
                except Exception:
                    pass
            order = [id2name.get(i, "") for i in ids]
            ie = next(i for i, n in enumerate(order) if n == "editnote.xhtml")
            ii = next(i for i, n in enumerate(order) if n == "intro.xhtml")
            ic = next(i for i, n in enumerate(order) if n == "cover.xhtml")
            self.assertLess(ic, ie)
            self.assertLess(ie, ii)
            raw = zipfile.ZipFile(parts[0]).read("EPUB/editnote.xhtml").decode("utf-8", "replace")
            self.assertIn("<h1", raw)
            self.assertIn("text-align:center", raw)
            self.assertIn("編者序", raw)
            # 无 editnote 时旧行为不变
            out2 = d / "out2" / "col.epub"
            out2.parent.mkdir(parents=True, exist_ok=True)
            parts2 = merge_epubs([a], out2, collection_name="丛书", organizer="编",
                                 titles=["甲"], cover_config={"enabled": True}, intro=intro)
            book2 = epub.read_epub(str(parts2[0]))
            names2 = [it.get_name() for it in book2.get_items()]
            self.assertNotIn("editnote.xhtml", names2)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_editnote_heading_tags_h1_to_h5(self):
        # EPUB：h1–h5 用原生标签＋逐级字号（1.90/1.615/1.52/1.33/1.14em）
        from cbeta_publish.books.ebook_merger import _epub_editnote_page
        parsed = {"title": "T", "lines": [
            ("h1", "left", "一"), ("h2", "left", "二"), ("h3", "left", "三"),
            ("h4", "left", "四"), ("h5", "left", "五"), ("body", "left", "六")]}
        html = _epub_editnote_page(parsed).content
        for tag, fs in (("h1", "1.90em"), ("h2", "1.61em"), ("h3", "1.52em"),
                        ("h4", "1.33em"), ("h5", "1.14em")):
            self.assertIn(f"<{tag} ", html)
            self.assertIn(f"font-size:{fs}", html)

    def test_editnote_body_compact(self):
        # 正文 <p> 收紧段间距与行高（与说明页一致），否则阅读器默认
        # p{margin:1em 0} 会让逐行成段的文字显得双倍行距；标题保持阅读器默认
        from cbeta_publish.books.ebook_merger import _epub_editnote_page
        parsed = {"title": "T", "lines": [
            ("body", "left", "正文行"), ("b", "left", "重点"),
            ("h1", "left", "标题"), ("gap", "left", "")]}
        html = _epub_editnote_page(parsed).content
        self.assertIn("<p style=\"font-size:1.00em;text-indent:0;"
                      "margin:0.3em 0;line-height:1.2\">正文行</p>", html)
        self.assertIn("margin:0.3em 0;line-height:1.2\"><b>重点</b></p>", html)
        h1 = html.split("<h1", 2)[2]
        self.assertNotIn("margin:0.3em", h1.split(">", 1)[0])

    def test_editnote_gap_one_line(self):
        # 空行约一倍字高：无边距＋单倍行高（nbsp 防吞段）
        from cbeta_publish.books.ebook_merger import _epub_editnote_page
        parsed = {"title": "T", "lines": [
            ("body", "left", "上"), ("gap", "left", ""),
            ("body", "left", "下")]}
        html = _epub_editnote_page(parsed).content
        self.assertIn("<p style=\"margin:0;line-height:1.0;\">&#160;</p>", html)
        self.assertNotIn("margin:0.4em", html)

    def test_editnote_heading_compact_margin(self):
        # 标题行显式紧凑边距：否则阅读器默认下边距（按标题字号算）
        # 会把紧跟的空行/正文撑高；下沿与正文同节奏（0.3em）
        from cbeta_publish.books.ebook_merger import _epub_editnote_page
        parsed = {"title": "T", "lines": [
            ("h1", "left", "大標"), ("h5", "left", "小標"),
            ("gap", "left", ""), ("body", "left", "文")]}
        html = _epub_editnote_page(parsed).content
        self.assertIn("margin:0.8em 0 0.3em", html)
        for tag, text in (("h1", "大標"), ("h5", "小標")):
            # 内容标题（页首标题除外）：紧凑边距、非正文样式
            seg = [p.split(">", 1)[0] for p in html.split("<%s " % tag)
                   if text in p.split(">", 1)[1]][0]
            self.assertIn("margin:0.8em 0 0.3em", seg, seg)
            self.assertNotIn("margin:0.3em 0;line-height", seg, seg)

    def test_editnote_pb_break_div(self):
        # EPUB 不切文件：<pb> 输出空 break-div（break-before 在前、
        # page-break-before 紧跟兼容），无残留高度；其余内容逐字一致
        import zipfile
        from cbeta_publish.books.ebook_merger import (
            parse_editnote_file, _epub_editnote_page)
        d = Path(tempfile.mkdtemp())
        try:
            parsed = {"title": "T", "lines": [
                ("body", "left", "上"), ("pb", "left", ""),
                ("body", "left", "下")]}
            html = _epub_editnote_page(parsed).content
            self.assertIn("<div style=\"break-before:page;"
                          "page-break-before:always;\"></div>", html)
            self.assertIn(">上</p>", html)
            self.assertIn(">下</p>", html)
            # 进整书：仍单 editnote.xhtml，无 editnote2
            t = d / "note.txt"
            t.write_text("<title>T\n上\n<pb>\n下\n", encoding="utf-8")
            from cbeta_publish.books.ebook_merger import merge_epubs
            a = d / "A.epub"
            make_src(a, "A", juans=1)
            out = d / "out" / "col.epub"
            out.parent.mkdir(parents=True, exist_ok=True)
            parts = merge_epubs([a], out, titles=["甲"],
                                cover_config={"enabled": True},
                                editnote=parse_editnote_file(t))
            names = zipfile.ZipFile(parts[0]).namelist()
            self.assertIn("EPUB/editnote.xhtml", names)
            self.assertFalse([n for n in names if "editnote2" in n], names)
            raw = zipfile.ZipFile(parts[0]).read(
                "EPUB/editnote.xhtml").decode("utf-8", "replace")
            self.assertIn("break-before:page;page-break-before:always", raw)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_editnote_no_reader_indent(self):
        # 阅读器常给 <p> 默认首行缩进 2em：我们显式 text-indent:0，
        # 只显示作者手写的缩进（半角→&#160;，全角原样保留），不叠加成 4 格
        import zipfile
        from cbeta_publish.books.ebook_merger import parse_editnote_file
        d = Path(tempfile.mkdtemp())
        try:
            t = d / "note.txt"
            t.write_text("<title>編者序\n    半角缩进\n　　全角缩进\n",
                         encoding="utf-8")
            parsed = parse_editnote_file(t)
            intro = {"title": "说明", "summary": [], "sections": []}
            a = d / "A.epub"
            make_src(a, "A", juans=1)
            out = d / "out" / "col.epub"
            out.parent.mkdir(parents=True, exist_ok=True)
            parts = merge_epubs([a], out, collection_name="丛书", organizer="编",
                                 titles=["甲"], cover_config={"enabled": True},
                                 intro=intro, editnote=parsed)
            raw = zipfile.ZipFile(parts[0]).read("EPUB/editnote.xhtml").decode("utf-8", "replace")
            self.assertIn("text-indent:0", raw)
            # ebooklib 落盘把 &#160; 转成 nbsp 字面量（同义）：半角缩进 4 个 nbsp
            nbsp = chr(0xA0)
            self.assertIn(nbsp * 4 + "半角缩进", raw)
            self.assertIn("　　全角缩进", raw)
            self.assertNotIn(nbsp + "　", raw)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class MergeEpubTocNumberTest(unittest.TestCase):
    """EPUB 目录序号：只给经书条目加（封面/丛书目录/编辑说明/说明不加）；
    全局连续（切分各 part 接续），自适应补零。"""

    def _nav(self, part):
        import zipfile
        return zipfile.ZipFile(part).read("EPUB/nav.xhtml").decode("utf-8", "replace")

    def test_books_numbered_others_not(self):
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.epub"
            b = d / "B.epub"
            make_src(a, "A", juans=1)
            make_src(b, "B", juans=1)
            out = d / "out" / "col.epub"
            out.parent.mkdir(parents=True, exist_ok=True)
            parts = merge_epubs([a, b], out, collection_name="丛书",
                                organizer="编者", titles=["甲", "乙"],
                                cover_config={"enabled": True},
                                intro={"title": "说明", "summary": [], "sections": []})
            self.assertEqual(len(parts), 1)
            nav = self._nav(parts[0])
            self.assertIn("1. 甲", nav)
            self.assertIn("2. 乙", nav)
            for plain in ("封面</a>", "丛书目录</a>", ">说明</a>"):
                self.assertIn(plain, nav)
            self.assertNotIn("1. 封面", nav)
            self.assertNotIn("1. 丛书目录", nav)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_bare_and_split_numbering(self):
        from cbeta_publish.books import ebook_merger as m
        d = Path(tempfile.mkdtemp())
        try:
            a = d / "A.epub"
            b = d / "B.epub"
            make_src(a, "A", juans=1)
            make_src(b, "B", juans=1)
            # bare 路径（封面关闭）：纯经书条目，照样编号
            out = d / "out" / "bare.epub"
            out.parent.mkdir(parents=True, exist_ok=True)
            parts = m.merge_epubs([a, b], out, titles=["甲", "乙"],
                                  cover_config={"enabled": False})
            nav = self._nav(parts[0])
            self.assertIn("1. 甲", nav)
            self.assertIn("2. 乙", nav)
            # 切分：全局接续（part2 从 2 开始）
            out2 = d / "out2" / "col.epub"
            out2.parent.mkdir(parents=True, exist_ok=True)
            parts2 = m.merge_epubs([a, b], out2, titles=["甲", "乙"],
                                   cover_config={"enabled": True},
                                   split_items=1)
            self.assertEqual(len(parts2), 2)
            self.assertIn("1. 甲", self._nav(parts2[0]))
            self.assertNotIn("2. 乙", self._nav(parts2[0]))
            self.assertIn("2. 乙", self._nav(parts2[1]))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_seq_title_unit(self):
        from cbeta_publish.books.ebook_merger import _epub_seq_title
        self.assertEqual(_epub_seq_title(3, 8, "X"), "3. X")
        self.assertEqual(_epub_seq_title(3, 12, "X"), "03. X")
        self.assertEqual(_epub_seq_title(7, 105, "X"), "007. X")


if __name__ == "__main__":
    unittest.main()
