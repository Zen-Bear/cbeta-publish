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
        self.assertEqual([t for t, _ in links], ["封面", "丛书目录", "甲", "乙"])

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
        self.assertEqual([t for _, t, _ in top], ["甲", "乙"])
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
        self.assertEqual([t for t, _ in links], ["封面", "丛书目录", "说明", "甲", "乙"])

    def test_cover_config_ratio_and_color(self):
        # E2：EPUB 封面字号取 styles.ratio（em）、颜色取 styles.color
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
        self.assertIn("font-size:1.35em", raw)
        self.assertIn("color:#0a141e", raw)

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


if __name__ == "__main__":
    unittest.main()
