# -*- coding: utf-8 -*-
"""丛书独立分册配置 `merge{mode,depth,name_template}` 与 `_coll_merge_cfg`。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.collection.collection_model import Collection, normalize_collection  # noqa: E402
from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class NormalizeMergeTest(unittest.TestCase):
    def test_valid_normalized(self):
        d = normalize_collection({"work_ids": [], "merge": {
            "mode": "catalog", "depth": 9, "name_template": "X"}})
        self.assertEqual(d["merge"], {"mode": "catalog", "depth": 5,
                                      "name_template": "X"})

    def test_invalid_mode_and_depth(self):
        d = normalize_collection({"work_ids": [], "merge": {
            "mode": "bogus", "depth": "zz"}})
        self.assertEqual(d["merge"]["mode"], "none")
        self.assertEqual(d["merge"]["depth"], 2)

    def test_absent_key_stays_absent(self):
        d = normalize_collection({"work_ids": []})
        self.assertNotIn("merge", d)

    def test_collection_to_dict_roundtrip(self):
        c = Collection("id", "名", "custom", works=["T0001"])
        self.assertNotIn("merge", c.to_dict())
        c.merge = {"mode": "author", "depth": 2, "name_template": "T"}
        self.assertEqual(c.to_dict()["merge"], c.merge)


class CollMergeCfgTest(unittest.TestCase):
    def setUp(self):
        _ensure_app()
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "collections" / "custom").mkdir(parents=True)
        cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
        cfg["mulu_dir"] = str(ROOT / "mulu")
        cfg["collections_dir"] = str(self.tmp / "collections")
        cfg["update_interval"] = "manual"
        cfg["_config_path"] = str(self.tmp / "app.json")
        cfg["merge"] = {"mode": "author", "depth": 3, "name_template": "G"}
        self.win = MainWindow(cfg)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_follow_global_when_absent(self):
        self.assertEqual(self.win._coll_merge_cfg({"name": "x"}),
                         ("author", 3, "G"))

    def test_override_when_present(self):
        d = {"name": "x", "merge": {"mode": "dynasty", "depth": 1,
                                    "name_template": "C"}}
        self.assertEqual(self.win._coll_merge_cfg(d), ("dynasty", 1, "C"))

    def test_template_falls_back_to_global(self):
        d = {"name": "x", "merge": {"mode": "volume", "depth": 2,
                                    "name_template": ""}}
        self.assertEqual(self.win._coll_merge_cfg(d), ("volume", 2, "G"))


if __name__ == "__main__":
    unittest.main()
