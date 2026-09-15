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

    def test_dest_path(self):
        self.assertEqual(dest_path("T0001", "pdf", self.dir),
                         self.dir / "pdf" / "T" / "T0001.pdf")
        self.assertEqual(dest_path("A1057", "epub", self.dir),
                         self.dir / "epub" / "A" / "A1057.epub")
        self.assertTrue(ebook_url("pdf", "T", "T0001").endswith("/pdf/T/T0001.pdf"))

    def test_id_case_normalization(self):
        # 字母后缀/前缀的编号：canon 大写、编号保留原大小写
        self.assertEqual(canon_of("TXA001"), "TX")
        self.assertEqual(canon_of("T0128A"), "T")
        self.assertEqual(canon_of("jb005"), "J")
        self.assertEqual(dest_path("TXA001", "pdf", self.dir),
                         self.dir / "pdf" / "TX" / "TXa001.pdf")
        self.assertEqual(dest_path("T0128A", "epub", self.dir),
                         self.dir / "epub" / "T" / "T0128a.epub")
        self.assertEqual(dest_path("jb005", "pdf", self.dir),
                         self.dir / "pdf" / "J" / "JB005.pdf")

    def test_zip_format_layout_and_download(self):
        self.assertEqual(zip_dest_dir("T0099", "docx", self.dir),
                         self.dir / "docx" / "T" / "T0099")
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


class DownloadWorkerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "pdf" / "T").mkdir(parents=True)
        (self.dir / "pdf" / "T" / "T0001.pdf").write_bytes(b"x" * 100)
        (self.dir / "pdf" / "T" / "T0003.pdf").write_bytes(b"y" * 50)
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

        def fake_dl(work, fmt, dest_dir):
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
        self.assertTrue(any(m.startswith("跳过 T0001") for m in msgs), msgs)
        self.assertTrue(any(m.startswith("完成 T0002") for m in msgs), msgs)
        self.assertTrue(any(m.startswith("更新 T0003") for m in msgs), msgs)
        self.assertTrue(any(m.startswith("失败 T0004") for m in msgs), msgs)

    def test_stop_breaks(self):
        from cbeta_publish.books.download_worker import DownloadWorker
        attempted = []
        msgs = []
        done = {}
        w = DownloadWorker(["T0001", "T0002"], ["pdf"], self.dir)
        oes.remote_info = lambda work, fmt: None

        def fake_dl(work, fmt, dest_dir):
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


if __name__ == "__main__":
    unittest.main()
