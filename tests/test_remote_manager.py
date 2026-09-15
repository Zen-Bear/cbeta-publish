# -*- coding: utf-8 -*-
"""RemoteManager（复用 cbeta-fetch 条件更新）：304 免下载、200 更新、备份、URL 单源。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import remote_manager as rm_mod
from cbeta_publish.books import remote_sources
from cbeta_publish.books.remote_manager import RemoteManager, _clean_etag
from cbeta_publish._vendor import cbeta_fetch as cf


class CleanEtagTest(unittest.TestCase):
    """服务端 gzip 表示的 ETag 带 `-gzip` 后缀（cbdata），发条件头前须去掉，
    否则与实体表示不匹配 → 恒 200、每次都误报「有更新」（实测 304 vs 200）。"""

    def test_strip_gzip_suffix(self):
        self.assertEqual(_clean_etag('"ed6b0-658aaebd64e00-gzip"'), '"ed6b0-658aaebd64e00"')

    def test_keep_weak_prefix(self):
        self.assertEqual(_clean_etag('W/"abc-gzip"'), 'W/"abc"')

    def test_untouched_when_no_suffix(self):
        self.assertEqual(_clean_etag('"plain"'), '"plain"')
        self.assertEqual(_clean_etag('W/"abc"'), 'W/"abc"')
        self.assertIsNone(_clean_etag(None))
        self.assertEqual(_clean_etag(""), "")

    def test_cond_sends_cleaned_etag(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        try:
            m = RemoteManager(d / "meta.json")
            m.meta["u"] = {"etag": '"e-gzip"', "last_modified": "lm"}
            self.assertEqual(m._cond("u"), ('"e"', "lm"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class RemoteManagerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.meta = self.dir / "cache" / "meta.json"
        self.dest = self.dir / "mulu" / "category.json"
        self._probe = cf.probe_info
        self._fetch = cf.fetch_if_changed

    def tearDown(self):
        cf.probe_info = self._probe
        cf.fetch_if_changed = self._fetch
        shutil.rmtree(self.dir, ignore_errors=True)

    def _m(self, local=None):
        m = RemoteManager(self.meta)
        m._local_for = staticmethod(lambda url: local)
        return m

    @staticmethod
    def _probe_rv(status="changed", etag=None, lm=None, size=None):
        return {"status": status, "etag": etag, "last_modified": lm, "size": size}

    def test_check_304_unchanged(self):
        cf.probe_info = lambda url, etag=None, last_modified=None: self._probe_rv("not-modified")
        m = self._m()
        m.meta["u"] = {"etag": "e1", "last_modified": "lm1"}
        self.assertFalse(m.check("u"))

    def test_check_200_changed_without_local(self):
        cf.probe_info = lambda url, etag=None, last_modified=None: self._probe_rv("changed", "e2", "lm2")
        self.assertTrue(self._m().check("u"))

    def test_check_sends_conditionals(self):
        seen = {}

        def fake_probe(url, etag=None, last_modified=None):
            seen.update(url=url, etag=etag, last_modified=last_modified)
            return self._probe_rv("not-modified")
        cf.probe_info = fake_probe
        m = self._m()
        m.meta["u"] = {"etag": "E", "last_modified": "L"}
        m.check("u")
        self.assertEqual(seen, {"url": "u", "etag": "E", "last_modified": "L"})

    def test_check_size_equal_is_unchanged(self):
        # 服务端不 304（cbdata ETag 失配 / GitHub raw 忽略条件头）：
        # 远端大小与本地一致 → 视为未更新
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        self.dest.write_bytes(b"x" * 100)
        cf.probe_info = lambda url, etag=None, last_modified=None: self._probe_rv("changed", '"abc"', None, 100)
        self.assertFalse(self._m(self.dest).check("u"))

    def test_check_no_local_is_changed(self):
        cf.probe_info = lambda url, etag=None, last_modified=None: self._probe_rv("changed", '"abc"', None, 100)
        self.assertTrue(self._m(None).check("u"))

    def test_check_size_diff_is_changed(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        self.dest.write_bytes(b"x" * 100)
        cf.probe_info = lambda url, etag=None, last_modified=None: self._probe_rv("changed", '"abc"', None, 101)
        self.assertTrue(self._m(self.dest).check("u"))

    def test_fetch_downloaded_updates_meta(self):
        def fake_fetch(url, dest, etag=None, last_modified=None):
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            Path(dest).write_text("{}", encoding="utf-8")
            return ("downloaded", "e-new", "lm-new")
        cf.fetch_if_changed = fake_fetch
        m = RemoteManager(self.meta)
        self.assertTrue(m.fetch("u", self.dest))
        self.assertEqual(m.meta["u"], {"etag": "e-new", "last_modified": "lm-new"})
        self.assertTrue(json.loads(self.meta.read_text(encoding="utf-8"))["u"]["etag"] == "e-new")

    def test_fetch_not_modified(self):
        cf.fetch_if_changed = lambda url, dest, etag=None, last_modified=None: ("not-modified", etag, last_modified)
        m = RemoteManager(self.meta)
        self.assertFalse(m.fetch("u", self.dest))

    def test_fetch_failed(self):
        cf.fetch_if_changed = lambda url, dest, etag=None, last_modified=None: ("failed", None, None)
        m = RemoteManager(self.meta)
        self.assertFalse(m.fetch("u", self.dest))

    def test_local_for_maps_sources(self):
        from cbeta_publish.books.remote_sources import SOURCES, local_path
        key, cat, url, rel = SOURCES[0]
        self.assertEqual(RemoteManager._local_for(url), local_path(rel))
        self.assertIsNone(RemoteManager._local_for("https://example.com/none.json"))


class RemoteSourcesTest(unittest.TestCase):
    def test_urls_single_source(self):
        for key, cat, url, rel in remote_sources.SOURCES:
            self.assertIn(url, cf.REMOTE_URLS.values(), key)
        # url_of 与展开表一致
        self.assertEqual(remote_sources.url_of("category"), cf.REMOTE_URLS["category_json"])
        self.assertEqual(remote_sources.url_of("sutra_mapping"), cf.REMOTE_URLS["sutra_mapping"])

    def test_all_shared_keys_exist(self):
        for _key, _cat, _url, shared in remote_sources._SPEC:
            self.assertIn(shared, cf.REMOTE_URLS, shared)


if __name__ == "__main__":
    unittest.main()
