# -*- coding: utf-8 -*-
"""缓存统计与清理（cache_manager）。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books.cache_manager import dir_stats, human, clean


class CacheManagerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_stats_and_clean(self):
        (self.dir / "T").mkdir()
        (self.dir / "T" / "a.pdf").write_bytes(b"x" * 100)
        (self.dir / "T" / "b.pdf").write_bytes(b"y" * 50)
        st = dir_stats(self.dir)
        self.assertEqual(st, {"files": 2, "bytes": 150})
        r = clean(self.dir)
        self.assertEqual(r, {"removed_files": 2, "removed_bytes": 150})
        self.assertTrue(self.dir.exists())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_missing_dir(self):
        p = self.dir / "nope"
        self.assertEqual(dir_stats(p), {"files": 0, "bytes": 0})
        self.assertEqual(clean(p)["removed_files"], 0)

    def test_human(self):
        self.assertEqual(human(0), "0 B")
        self.assertEqual(human(512), "512 B")
        self.assertTrue(human(1536).endswith("KB"))


if __name__ == "__main__":
    unittest.main()
