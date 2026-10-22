# -*- coding: utf-8 -*-
"""配置路径归一（打包版相对路径）与损坏自动恢复。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.paths import (app_root, normalize_config_paths,
                                 read_user_config)


class NormalizePathsTest(unittest.TestCase):
    def test_relative_keys_become_absolute(self):
        cfg = {
            "mulu_dir": "mulu",
            "collections_dir": "collections",
            "official_ebooks_dir": "cbeta_ebooks",
            "cbeta_ebooks_dir": "cbeta_ebooks2",
            "output_dir": "collections_books",      # 已有 _out_dir 解析，不动
            "xml2pdf": {"path": "xml2pdf", "cbeta_ebook": "cbeta_xml"},
        }
        normalize_config_paths(cfg)
        self.assertEqual(cfg["mulu_dir"], str(app_root() / "mulu"))
        self.assertEqual(cfg["collections_dir"], str(app_root() / "collections"))
        self.assertEqual(cfg["official_ebooks_dir"], str(app_root() / "cbeta_ebooks"))
        self.assertEqual(cfg["cbeta_ebooks_dir"], str(app_root() / "cbeta_ebooks2"))
        self.assertEqual(cfg["xml2pdf"]["path"], str(app_root() / "xml2pdf"))
        self.assertEqual(cfg["output_dir"], "collections_books")
        self.assertEqual(cfg["xml2pdf"]["cbeta_ebook"], "cbeta_xml")

    def test_idempotent_and_absolute_kept(self):
        cfg = {"mulu_dir": "mulu", "xml2pdf": {"path": "xml2pdf"}}
        normalize_config_paths(cfg)
        first = dict(cfg)
        normalize_config_paths(cfg)
        self.assertEqual(cfg, first)
        abs_cfg = {"mulu_dir": str(app_root() / "elsewhere")}
        normalize_config_paths(abs_cfg)
        self.assertEqual(abs_cfg["mulu_dir"], str(app_root() / "elsewhere"))


class ReadUserConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cfg-"))
        self.cfg = self.dir / "app.json"
        self.dflt = self.dir / "app.default.json"
        self.dflt.write_text(json.dumps({"mulu_dir": "mulu", "ui": {}}),
                             encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_missing_copies_template(self):
        cfg, bak = read_user_config(self.cfg, self.dflt)
        self.assertIsNone(bak)
        self.assertEqual(cfg["mulu_dir"], "mulu")

    def test_corrupt_backs_up_and_recovers(self):
        self.cfg.write_text("{ broken", encoding="utf-8")
        cfg, bak = read_user_config(self.cfg, self.dflt)
        self.assertIsNotNone(bak)
        self.assertTrue(bak.exists())
        self.assertTrue(bak.name.startswith("app.json.bak-"))
        self.assertEqual(bak.read_text(encoding="utf-8"), "{ broken")
        self.assertEqual(cfg["mulu_dir"], "mulu")
        # 恢复正常后再读：不再产生备份
        cfg2, bak2 = read_user_config(self.cfg, self.dflt)
        self.assertIsNone(bak2)
        self.assertEqual(cfg2, cfg)


if __name__ == "__main__":
    unittest.main()
