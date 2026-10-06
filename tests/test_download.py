# -*- coding: utf-8 -*-
"""官方源更新检测：dest_path / is_unchanged（离线）；worker 跳过/更新/失败/取消。"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import official_ebook_source as oes
from cbeta_publish.books.official_ebook_source import (dest_path, is_unchanged, ebook_url,
                                             canon_of, zip_dest_dir, download_ebook)


class SourceMetaTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_head_probe_404(self):
        # HEAD 探针：404/410 确定不存在；2xx 存在；超时/405/其它不定
        import urllib.error
        import urllib.request
        real = urllib.request.urlopen

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def boom_404(*a, **k):
            raise urllib.error.HTTPError("u", 404, "x", {}, None)

        def boom_500(*a, **k):
            raise urllib.error.HTTPError("u", 500, "x", {}, None)

        def boom_timeout(*a, **k):
            raise TimeoutError("t")

        try:
            urllib.request.urlopen = boom_404
            self.assertTrue(oes._head_absent_404("http://x"))
            urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
                urllib.error.HTTPError("u", 410, "x", {}, None))
            self.assertTrue(oes._head_absent_404("http://x"))
            urllib.request.urlopen = lambda *a, **k: _Resp()
            self.assertFalse(oes._head_absent_404("http://x"))
            urllib.request.urlopen = boom_500
            self.assertFalse(oes._head_absent_404("http://x"))
            urllib.request.urlopen = boom_timeout
            self.assertFalse(oes._head_absent_404("http://x"))
        finally:
            urllib.request.urlopen = real

    def test_download_ebook_404_skips_download(self):
        # 404 直接抛 RemoteNotFound，不调 cf.download（省 3 次重试）
        import urllib.request
        import urllib.error
        from cbeta_publish.books import official_ebook_source as _o
        real_open = urllib.request.urlopen
        real_dl = _o.cf.download
        called = []

        def boom_404(*a, **k):
            raise urllib.error.HTTPError("u", 404, "x", {}, None)
        urllib.request.urlopen = boom_404
        _o.cf.download = lambda *a, **k: called.append(a) or True
        try:
            with self.assertRaises(_o.RemoteNotFound):
                _o.download_ebook("T9999", "pdf", self.dir, None)
            self.assertEqual(called, [])
        finally:
            urllib.request.urlopen = real_open
            _o.cf.download = real_dl

    def test_dest_path(self):
        self.assertEqual(dest_path("T0001", "pdf", self.dir),
                         self.dir / "pdf" / "T0001.pdf")
        self.assertEqual(dest_path("A1057", "epub", self.dir),
                         self.dir / "epub" / "A1057.epub")
        self.assertTrue(ebook_url("pdf", "T", "T0001").endswith("/pdf/T/T0001.pdf"))

    def test_id_case_normalization(self):
        # 字母后缀/前缀的编号：canon 大写（拼 URL 用）、编号保留原大小写；落盘无 canon 层
        self.assertEqual(canon_of("TXA001"), "TX")
        self.assertEqual(canon_of("T0128A"), "T")
        self.assertEqual(canon_of("jb005"), "J")
        self.assertEqual(dest_path("TXA001", "pdf", self.dir),
                         self.dir / "pdf" / "TXa001.pdf")
        self.assertEqual(dest_path("T0128A", "epub", self.dir),
                         self.dir / "epub" / "T0128a.epub")
        self.assertEqual(dest_path("jb005", "pdf", self.dir),
                         self.dir / "pdf" / "JB005.pdf")

    def test_zip_format_layout_and_download(self):
        self.assertEqual(zip_dest_dir("T0099", "docx", self.dir),
                         self.dir / "docx" / "T0099")
        calls = {}
        real = oes.cf.download

        def fake_download(url, dest, unzip=False):
            calls.update(url=url, dest=dest, unzip=unzip)
            Path(dest).mkdir(parents=True, exist_ok=True)
            (Path(dest) / "T0099_001.docx").write_bytes(b"x")
            return True
        oes.cf.download = fake_download
        try:
            out = download_ebook("T0099", "docx", self.dir)
        finally:
            oes.cf.download = real
        self.assertEqual(calls["unzip"], True)
        self.assertTrue(out and out.is_dir())
        self.assertTrue((out / "T0099_001.docx").exists())

    def test_download_file_uses_shared_layer(self):
        calls = {}
        real = oes.cf.download

        def fake_download(url, dest, unzip=False):
            calls.update(url=url, dest=dest, unzip=unzip)
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_bytes(b"pdf")
            return True
        oes.cf.download = fake_download
        try:
            out = download_ebook("T0349", "pdf", self.dir)
        finally:
            oes.cf.download = real
        self.assertEqual(calls["unzip"], False)
        self.assertTrue(calls["url"].endswith("/pdf/T/T0349.pdf"))
        self.assertEqual(out, dest_path("T0349", "pdf", self.dir))

    def _mk(self, name, size, mtime):
        p = self.dir / name
        p.write_bytes(b"x" * size)
        os.utime(p, (mtime, mtime))
        return p

    def test_unchanged(self):
        p = self._mk("a.pdf", 100, 1000.0)
        info = {"url": "u", "size": 100, "mtime": 999.0, "etag": None}
        self.assertTrue(is_unchanged(info, p))

    def test_size_diff(self):
        p = self._mk("a.pdf", 100, 1000.0)
        self.assertFalse(is_unchanged({"url": "u", "size": 101, "mtime": 999.0, "etag": None}, p))

    def test_remote_newer(self):
        p = self._mk("a.pdf", 100, 1000.0)
        self.assertFalse(is_unchanged({"url": "u", "size": 100, "mtime": 2000.0, "etag": None}, p))

    def test_no_info(self):
        p = self._mk("a.pdf", 100, 1000.0)
        self.assertFalse(is_unchanged(None, p))
        self.assertFalse(is_unchanged({"url": "u", "size": None, "mtime": None, "etag": "e"}, p))

    def test_missing_file(self):
        self.assertFalse(is_unchanged({"url": "u", "size": 100, "mtime": 1.0, "etag": None},
                                      self.dir / "no.pdf"))

    def test_txt_endpoint_is_dir_type(self):
        # 纯 txt（一部一档 text/{id}.txt.zip）走 publish 自有扩展（vendor 不动），目录型落盘
        from cbeta_publish.books import official_ebook_source as oes
        self.assertTrue(ebook_url("txt", "T", "T0001").endswith("/text/T0001.txt.zip"))
        self.assertIn("txt", oes._ZIP_FORMATS)
        self.assertEqual(oes.local_path("T0001", "txt", self.dir),
                         self.dir / "txt" / "T0001")
        with self.assertRaises(ValueError):
            ebook_url("bogus", "T", "T0001")


class DownloadWorkerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "pdf").mkdir(parents=True)
        (self.dir / "pdf" / "T0001.pdf").write_bytes(b"x" * 100)
        (self.dir / "pdf" / "T0003.pdf").write_bytes(b"y" * 50)
        self._real_remote = oes.remote_info
        self._real_dl = oes.download_ebook

    def tearDown(self):
        oes.remote_info = self._real_remote
        oes.download_ebook = self._real_dl
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self, works):
        from cbeta_publish.books.download_worker import DownloadWorker
        msgs = []
        done = {}
        w = DownloadWorker(works, ["pdf"], self.dir)
        w.progress.connect(msgs.append)
        w.finished_all.connect(lambda ok, total, failed: done.update(ok=ok, total=total, failed=list(failed)))
        w.run()
        return msgs, done

    def test_skip_update_fail(self):
        def fake_remote(work, fmt):
            if work == "T0001":
                return {"url": "u", "size": 100, "mtime": 1.0, "etag": None}
            if work == "T0003":
                return {"url": "u", "size": 999, "mtime": 2.0, "etag": None}
            return None

        def fake_dl(work, fmt, dest_dir, config=None, force=False):
            if work in ("T0002", "T0003"):
                p = oes.dest_path(work, fmt, dest_dir)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"z" * 10)
                return p
            return None

        oes.remote_info = fake_remote
        oes.download_ebook = fake_dl
        msgs, done = self._run(["T0001", "T0002", "T0003", "T0004"])
        self.assertEqual(done, {"ok": 3, "total": 4, "failed": ["T0004.pdf"]})
        text = [m.lstrip("\r") for m in msgs]
        self.assertTrue(any(m.startswith("跳过 T0001") for m in text), text)
        # 「下载 …」与「完成/更新 …」合并为一行（完成行以 \r 前缀要求替换上一行）
        self.assertTrue(any(m.startswith("下载 T0002.pdf ...完成 ") for m in text), text)
        self.assertTrue(any(m.startswith("下载 T0003.pdf ...更新 ") for m in text), text)
        self.assertTrue(any(m.startswith("下载 T0004.pdf ...失败") for m in text), text)
        from cbeta_publish.books.download_worker import REPLACE_LAST
        self.assertTrue(any(m.startswith(REPLACE_LAST) for m in msgs), msgs)

    def test_worker_marks_not_found(self):
        # download_ebook 抛 RemoteNotFound → 失败项记"不存在"，其余照常
        from cbeta_publish.books.download_worker import DownloadWorker
        from cbeta_publish.books.official_ebook_source import RemoteNotFound
        msgs = []
        done = {}
        w = DownloadWorker(["T0001", "T0002"], ["pdf"], self.dir)
        oes.remote_info = lambda work, fmt: None

        def fake_dl(work, fmt, dest_dir, config=None, force=False):
            if work == "T0002":
                raise RemoteNotFound("http://x/T0002.pdf")
            p = oes.dest_path(work, fmt, dest_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"z" * 10)
            return p

        oes.download_ebook = fake_dl
        w.progress.connect(msgs.append)
        w.finished_all.connect(lambda ok, total, failed: done.update(
            ok=ok, total=total, failed=list(failed)))
        w.run()
        self.assertEqual(done, {"ok": 1, "total": 2, "failed": ["T0002.pdf 不存在"]})
        text = [m.lstrip("\r") for m in msgs]
        self.assertTrue(any(m.startswith("下载 T0002.pdf ...不存在") for m in text), text)

    def test_stop_breaks(self):
        from cbeta_publish.books.download_worker import DownloadWorker
        attempted = []
        msgs = []
        done = {}
        w = DownloadWorker(["T0001", "T0002"], ["pdf"], self.dir)
        oes.remote_info = lambda work, fmt: None

        def fake_dl(work, fmt, dest_dir, config=None, force=False):
            attempted.append(work)
            w._stop = True
            return None

        oes.download_ebook = fake_dl
        w.progress.connect(msgs.append)
        w.finished_all.connect(lambda ok, total, failed: done.update(ok=ok, total=total, failed=list(failed)))
        w.run()
        self.assertEqual(attempted, ["T0001"])
        self.assertEqual(done["total"], 2)
        self.assertEqual(done["ok"] + len(done["failed"]), 1)

    def test_base_exception_still_finishes(self):
        # download_ebook 抛 SystemExit 等 BaseException 也必须发出 finished_all，
        # 否则主线程嵌套事件循环永不退出（界面挂死）
        from cbeta_publish.books.download_worker import DownloadWorker
        oes.remote_info = lambda work, fmt: None

        def boom(work, fmt, dest_dir, config=None, force=False):
            raise SystemExit(2)

        oes.download_ebook = boom
        done = {}
        w = DownloadWorker(["T0001"], ["pdf"], self.dir)
        w.finished_all.connect(lambda ok, total, failed: done.update(ok=ok, total=total, failed=list(failed)))
        w.run()
        self.assertEqual(done, {"ok": 0, "total": 1, "failed": ["T0001.pdf"]})

    def test_pairs_mode_downloads_only_given_combos(self):
        # 明确 pairs（缺书集合）：只下这些组合，不展开为 works × fmts
        from cbeta_publish.books.download_worker import DownloadWorker
        oes.remote_info = lambda work, fmt: None
        tried = []

        def fake_dl(work, fmt, dest_dir, config=None, force=False):
            tried.append((work, fmt))
            p = oes.dest_path(work, fmt, dest_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"z" * 10)
            return p
        oes.download_ebook = fake_dl
        msgs = []
        done = {}
        w = DownloadWorker(dest_dir=self.dir, pairs=[("T0002", "pdf"), ("T0002", "epub")])
        w.progress.connect(msgs.append)
        w.finished_all.connect(lambda ok, total, failed: done.update(ok=ok, total=total, failed=list(failed)))
        w.run()
        self.assertEqual(tried, [("T0002", "pdf"), ("T0002", "epub")])
        self.assertEqual(done, {"ok": 2, "total": 2, "failed": []})
        self.assertEqual(len([m for m in msgs if m.startswith("\r")]), 2)


class OfficialLibraryTest(unittest.TestCase):
    """官方电子书本地库：自动探测、本查找、拷贝进缓存、下载本地优先、基线 seeding。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        lib = self.dir / "lib"
        (lib / "cbeta_epub_2026r2" / "T").mkdir(parents=True)
        (lib / "cbeta_epub_2026r2" / "T" / "T0001.epub").write_bytes(b"E" * 10)
        (lib / "cbeta_docx_2026r2" / "T" / "T0001").mkdir(parents=True)
        (lib / "cbeta_docx_2026r2" / "T" / "T0001" / "T0001_001.docx").write_bytes(b"D" * 20)
        (lib / "cbeta-text-with-notes" / "T" / "T0001").mkdir(parents=True)
        (lib / "cbeta-text-with-notes" / "T" / "T0001" / "T0001_001.txt").write_bytes(b"T" * 30)
        (lib / "cbeta-text-with-notes" / "T" / "T0001" / "T0001.yaml").write_bytes(b"y")
        (lib / "cbeta-text" / "T" / "T0001").mkdir(parents=True)
        (lib / "cbeta-text" / "T" / "T0001" / "T0001_001.txt").write_bytes(b"P" * 40)
        self.cfg = {"official_library": {"root": str(lib), "overrides": {}}}
        self.lib = lib

    def tearDown(self):
        oes.refresh_library_map()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_resolve_map(self):
        mapping, notes = oes.resolve_library_map(str(self.lib), {})
        self.assertEqual(mapping["epub"]["pattern"], "single")
        self.assertEqual(mapping["docx"]["pattern"], "juan")
        self.assertEqual(mapping["txt_notes"]["pattern"], "juan")
        self.assertEqual(mapping["txt"]["pattern"], "juan")
        self.assertEqual(mapping["txt"]["dir"].name, "cbeta-text")
        self.assertEqual(mapping["txt_notes"]["dir"].name, "cbeta-text-with-notes")
        self.assertNotIn("pdf", mapping)
        self.assertTrue(any("epub" in n for n in notes))

    def test_resolve_missing_root(self):
        mapping, notes = oes.resolve_library_map(str(self.dir / "nope"), {})
        self.assertEqual(mapping, {})
        mapping2, _ = oes.resolve_library_map("", {})
        self.assertEqual(mapping2, {})

    def test_resolve_override(self):
        (self.lib / "myepub").mkdir()
        (self.lib / "myepub" / "T").mkdir()
        (self.lib / "myepub" / "T" / "T0002.epub").write_bytes(b"E")
        mapping, _ = oes.resolve_library_map(str(self.lib), {"epub": "myepub"})
        self.assertEqual(mapping["epub"]["dir"].name, "myepub")
        cfg_ov = {"official_library": {"root": str(self.lib),
                                       "overrides": {"epub": "myepub"}}}
        self.assertEqual(oes.find_in_library("T0002", "epub", cfg_ov)[0].name,
                         "T0002.epub")

    def test_find_and_copy(self):
        self.assertEqual([p.name for p in oes.find_in_library("T0001", "epub", self.cfg)],
                         ["T0001.epub"])
        got = [p.name for p in oes.find_in_library("T0001", "docx", self.cfg)]
        self.assertEqual(got, ["T0001_001.docx"])
        # 纯 txt 与带注 txt 分流，不混
        self.assertEqual([p.name for p in oes.find_in_library("T0001", "txt", self.cfg)],
                         ["T0001_001.txt"])
        tn = oes.find_in_library("T0001", "txt_notes", self.cfg)
        self.assertEqual([p.name for p in tn], ["T0001_001.txt"])
        self.assertIn("cbeta-text-with-notes", str(tn[0]))
        self.assertIn("cbeta-text", str(oes.find_in_library("T0001", "txt", self.cfg)[0]))
        self.assertEqual(oes.find_in_library("T9999", "epub", self.cfg), [])
        self.assertEqual(oes.find_in_library("T0001", "pdf", self.cfg), [])
        dest = self.dir / "cache"
        e = oes.copy_from_library("T0001", "epub", dest, self.cfg)
        self.assertEqual(e, dest / "epub" / "T0001.epub")
        self.assertTrue(e.is_file())
        d = oes.copy_from_library("T0001", "docx", dest, self.cfg)
        self.assertEqual((d / "T0001_001.docx").read_bytes(), b"D" * 20)
        t = oes.copy_from_library("T0001", "txt", dest, self.cfg)
        self.assertEqual((t / "T0001_001.txt").read_bytes(), b"P" * 40)
        # 幂等：已存在同大小跳过
        self.assertEqual(oes.copy_from_library("T0001", "epub", dest, self.cfg), e)
        self.assertIsNone(oes.copy_from_library("T9999", "epub", dest, self.cfg))

    def test_copy_from_library_force_overwrites_same_size(self):
        dest = self.dir / "cacheF"
        e = oes.copy_from_library("T0001", "epub", dest, self.cfg)
        self.assertEqual(e.read_bytes(), b"E" * 10)
        # 换库内容：同大小不同内容
        (self.lib / "cbeta_epub_2026r2" / "T" / "T0001.epub").write_bytes(b"Z" * 10)
        # 非 force：同大小跳过 → 仍旧内容
        oes.copy_from_library("T0001", "epub", dest, self.cfg)
        self.assertEqual((dest / "epub" / "T0001.epub").read_bytes(), b"E" * 10)
        # force：强制覆盖
        oes.copy_from_library("T0001", "epub", dest, self.cfg, force=True)
        self.assertEqual((dest / "epub" / "T0001.epub").read_bytes(), b"Z" * 10)

    def test_copy_from_library_force_overwrites_dir_same_size(self):
        dest = self.dir / "cacheFD"
        oes.copy_from_library("T0001", "docx", dest, self.cfg)
        f = dest / "docx" / "T0001" / "T0001_001.docx"
        self.assertEqual(f.read_bytes(), b"D" * 20)
        (self.lib / "cbeta_docx_2026r2" / "T" / "T0001" / "T0001_001.docx").write_bytes(b"W" * 20)
        oes.copy_from_library("T0001", "docx", dest, self.cfg)
        self.assertEqual(f.read_bytes(), b"D" * 20)
        oes.copy_from_library("T0001", "docx", dest, self.cfg, force=True)
        self.assertEqual(f.read_bytes(), b"W" * 20)

    def test_download_prefers_library_without_network(self):
        real = oes.cf.download

        def boom(url, dest, **k):
            raise AssertionError(f"network must not be used: {url}")

        oes.cf.download = boom
        try:
            out = oes.download_ebook("T0001", "epub", self.dir / "cache2", self.cfg)
        finally:
            oes.cf.download = real
        self.assertTrue(out and out.is_file())
        self.assertEqual(out.read_bytes(), b"E" * 10)

    def test_worker_reports_library_source(self):
        from cbeta_publish.books.download_worker import DownloadWorker
        oes_remote, oes_dl = oes.remote_info, oes.download_ebook
        oes.remote_info = lambda work, fmt: None
        msgs, done = [], {}
        try:
            w = DownloadWorker(["T0001"], ["epub"], self.dir / "cache3", config=self.cfg)
            w.progress.connect(msgs.append)
            w.finished_all.connect(
                lambda ok, total, failed: done.update(ok=ok, total=total, failed=list(failed)))
            w.run()
        finally:
            oes.remote_info, oes.download_ebook = oes_remote, oes_dl
        self.assertEqual(done, {"ok": 1, "total": 1, "failed": []})
        text = [m.lstrip("\r") for m in msgs]
        self.assertTrue(any(m.startswith("本地库 T0001.epub ...完成 ") for m in text), text)
        self.assertTrue((self.dir / "cache3" / "epub" / "T0001.epub").is_file())

    def test_seed_baselines(self):
        wdir = self.dir / "work" / "T0001 中論"
        wdir.mkdir(parents=True)
        got = oes.seed_baselines_from_library("T0001", ["docx", "txt_notes", "epub"],
                                              wdir, self.cfg)
        self.assertEqual(sorted(got), ["docx", "epub", "txt_notes"])
        self.assertTrue((wdir / "docx" / "T0001_001.docx").is_file())
        self.assertTrue((wdir / "txt" / "T0001_001.txt").is_file())
        self.assertFalse((wdir / "txt" / "T0001.yaml").is_file())  # 非基线不取
        # 已有不覆盖；缺目录跳过
        (wdir / "docx" / "T0001_001.docx").write_bytes(b"KEEP")
        got2 = oes.seed_baselines_from_library("T0001", ["docx"], wdir, self.cfg)
        self.assertEqual((wdir / "docx" / "T0001_001.docx").read_bytes(), b"KEEP")
        self.assertIn("docx", got2)
        self.assertEqual(oes.seed_baselines_from_library("T0001", ["docx"],
                                                         self.dir / "nodir", self.cfg), {})
        # epub 单文件落 epub/ 子目录
        self.assertTrue((wdir / "epub").is_dir())


if __name__ == "__main__":
    unittest.main()
