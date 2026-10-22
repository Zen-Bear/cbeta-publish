# -*- coding: utf-8 -*-
"""原子写：成功覆盖、失败保留旧文件、不残留 tmp。"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cbeta_publish.utils.atomic import atomic_write_json, atomic_write_text


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="atomic-"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_json_roundtrip_and_overwrite(self):
        p = self.dir / "sub" / "a.json"
        atomic_write_json(p, {"x": 1, "名": "值"})
        self.assertEqual(p.read_text(encoding="utf-8"), '{\n  "x": 1,\n  "名": "值"\n}')
        atomic_write_json(p, {"x": 2})
        self.assertIn('"x": 2', p.read_text(encoding="utf-8"))

    def test_failure_keeps_original_and_cleans_tmp(self):
        p = self.dir / "a.txt"
        p.write_text("old", encoding="utf-8")
        with mock.patch("cbeta_publish.utils.atomic.os.replace",
                        side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                atomic_write_text(p, "new")
        self.assertEqual(p.read_text(encoding="utf-8"), "old")
        self.assertEqual([f.name for f in self.dir.iterdir()], ["a.txt"])

    def test_tmp_name_unique(self):
        # 不能再用固定 name.tmp：并发写不同目标时互不干扰
        a = self.dir / "a.json"
        b = self.dir / "b.json"
        atomic_write_json(a, {"a": 1})
        atomic_write_json(b, {"b": 2})
        self.assertTrue(a.is_file() and b.is_file())
        self.assertEqual([f.name for f in self.dir.iterdir() if f.name.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
