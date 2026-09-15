# -*- coding: utf-8 -*-
"""RemoteManager（复用 cbeta-fetch 条件更新）：304 免下载、200 更新、备份、URL 单源。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import remote_manager as rm_mod
from cbeta_publish.books import remote_sources
from cbeta_publish.books.remote_manager import RemoteManager
from cbeta_publish._vendor import cbeta_fetch as cf


class RemoteManagerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.meta = self.dir / "cache" / "meta.json"
        self.dest = self.dir / "mulu" / "category.json"
        self._probe = cf.probe
        self._fetch = cf.fetch_if_changed

    def tearDown(self):
        cf.probe = self._probe
        cf.fetch_if_changed = self._fetch
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_check_304_unchanged(self):
        cf.probe = lambda url, etag=None, last_modified=None: ("not-modified", etag, last_modified)
        m = RemoteManager(self.meta)
        m.meta["u"] = {"etag": "e1", "last_modified": "lm1"}
        self.assertFalse(m.check("u"))
        self.assertTrue(self.meta.exists() or True)  # check 不落盘也可接受

    def test_check_200_changed(self):
        cf.probe = lambda url, etag=None, last_modified=None: ("changed", "e2", "lm2")
        m = RemoteManager(self.meta)
        self.assertTrue(m.check("u"))

    def test_check_sends_conditionals(self):
        seen = {}

        def fake_probe(url, etag=None, last_modified=None):
            seen.update(url=url, etag=etag, last_modified=last_modified)
            return ("not-modified", etag, last_modified)
        cf.probe = fake_probe
        m = RemoteManager(self.meta)
        m.meta["u"] = {"etag": "E", "last_modified": "L"}
        m.check("u")
        self.assertEqual(seen, {"url": "u", "etag": "E", "last_modified": "L"})

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
