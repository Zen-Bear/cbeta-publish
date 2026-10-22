# -*- coding: utf-8 -*-
"""发布包出厂化脚本 ``packaging/sanitize_dist.py`` 的行为。"""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "sanitize_dist", ROOT / "packaging" / "sanitize_dist.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SanitizeDistTest(unittest.TestCase):
    def setUp(self):
        self.mod = _load_module()
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "config").mkdir()
        (self.dir / "xml2pdf" / "presets").mkdir(parents=True)
        (self.dir / "mulu" / "backup" / "last").mkdir(parents=True)
        (self.dir / "mulu" / "backup" / "original").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, rel, obj):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return p

    def test_clears_official_library_root_and_is_idempotent(self):
        p = self._write("config/app.default.json",
                        {"official_library": {"root": "E:\\CBETA\\2026r2",
                                              "overrides": {}},
                         "output_dir": "collections_books"})
        self.assertTrue(self.mod.sanitize_config_default(self.dir))
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(d["official_library"]["root"], "")
        self.assertEqual(d["output_dir"], "collections_books")     # 其它键不动
        self.assertFalse(self.mod.sanitize_config_default(self.dir))   # 幂等

    def test_removes_backup_config_snapshots_only(self):
        self._write("mulu/backup/last/app.json", {"mulu_dir": "E:\\dev\\x"})
        self._write("mulu/backup/original/app.json", {"mulu_dir": "E:/dev/x"})
        self._write("mulu/backup/config/last/app.json", {"mulu_dir": "E:\\dev\\x"})
        self._write("mulu/backup/config/original/app.json", {"mulu_dir": "E:/dev/x"})
        kept = self._write("mulu/backup/last/bulei.txt", {"a": 1})
        got = self.mod.remove_backup_config(self.dir)
        self.assertEqual(len(got), 4)
        self.assertFalse((self.dir / "mulu/backup/last/app.json").exists())
        self.assertFalse((self.dir / "mulu/backup/original/app.json").exists())
        self.assertFalse((self.dir / "mulu/backup/config/last/app.json").exists())
        self.assertFalse((self.dir / "mulu/backup/config/original/app.json").exists())
        self.assertTrue(kept.exists())                             # 其它快照保留

    def test_clears_absolute_paths_in_preset(self):
        p = self._write("xml2pdf/presets/A5 霞鹜文楷.json", {
            "source": {"xml_dir": "", "cbeta_ebook": "E:/dev/cbeta/xml",
                       "baselines": {"txt": "", "pdf": "E:\\CBETA\\2026r2\\pdf"},
                       "baselines_root": r"\\server\share",
                       "out_dir": "relative/out"},
            "annotations": {"file": "E:\\dev\\a.txt"},
            "formats": ["pdf"],
        })
        self.assertEqual(self.mod.sanitize_preset(p), 4)
        d = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(d["source"]["cbeta_ebook"], "")
        self.assertEqual(d["source"]["baselines"]["pdf"], "")
        self.assertEqual(d["source"]["baselines_root"], "")
        self.assertEqual(d["source"]["out_dir"], "relative/out")   # 相对路径不动
        self.assertEqual(d["annotations"]["file"], "")
        self.assertEqual(d["formats"], ["pdf"])                    # 其它键不动
        self.assertEqual(self.mod.sanitize_preset(p), 0)           # 幂等

    def test_keeps_relative_and_unparsable_preset(self):
        rel = self._write("xml2pdf/presets/rel.json",
                          {"source": {"xml_dir": "xml", "baselines_root": "b"}})
        self.assertEqual(self.mod.sanitize_preset(rel), 0)
        commented = self.dir / "xml2pdf" / "presets" / "commented.json"
        commented.write_text('{\n // 注释\n "a": 1\n}', encoding="utf-8")
        self.assertEqual(self.mod.sanitize_preset(commented), 0)
        self.assertIn("// 注释", commented.read_text(encoding="utf-8"))   # 原样保留

    def test_main_requires_dist_dir(self):
        self.assertEqual(self.mod.main(["sanitize_dist.py"]), 2)
        self.assertEqual(self.mod.main(["sanitize_dist.py", str(self.dir.parent)]), 1)
        self.assertEqual(self.mod.main(["sanitize_dist.py", str(self.dir)]), 0)


if __name__ == "__main__":
    unittest.main()
