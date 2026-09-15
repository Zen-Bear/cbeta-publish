# -*- coding: utf-8 -*-
"""vendor 副本防漂移：`_vendor/cbeta_fetch.py` 的 sha256/version 与 SOURCE.txt 一致。"""
import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "cbeta_publish" / "_vendor"


class VendorSyncTest(unittest.TestCase):
    def test_source_meta(self):
        src = VENDOR / "cbeta_fetch.py"
        meta = VENDOR / "SOURCE.txt"
        self.assertTrue(src.is_file(), src)
        self.assertTrue(meta.is_file(), meta)
        text = meta.read_text(encoding="utf-8")
        want = dict(
            line.strip().split("=", 1)
            for line in text.splitlines() if "=" in line
        )
        h = hashlib.sha256(src.read_bytes()).hexdigest()
        self.assertEqual(h, want.get("sha256"), "vendor 副本被手改？请用 tools/sync_into.py 同步")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', src.read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual(m.group(1), want.get("version"))

    def test_module_imports(self):
        from cbeta_publish._vendor import cbeta_fetch as cf
        self.assertTrue(callable(cf.probe_info))
        self.assertTrue(callable(cf.canonical_work_id))
        self.assertIn("pdf", cf.DEFAULT_DOWNLOADS)


if __name__ == "__main__":
    unittest.main()
