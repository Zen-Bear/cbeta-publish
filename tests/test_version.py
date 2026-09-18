# -*- coding: utf-8 -*-
"""软件名与版本：单一来源（cbeta_publish/__init__），窗口标题带上版本。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish import APP_ID, APP_NAME, __version__  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class VersionTest(unittest.TestCase):
    def test_metadata(self):
        self.assertTrue(APP_NAME.strip())
        self.assertEqual(APP_ID, "cbeta-publish")
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_window_title_has_name_and_version(self):
        _ensure_app()
        from cbeta_publish.gui.main_window import MainWindow
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "collections" / "custom").mkdir(parents=True)
            (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
            (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
            cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
            cfg["mulu_dir"] = str(ROOT / "mulu")
            cfg["collections_dir"] = str(tmp / "collections")
            cfg["update_interval"] = "manual"
            cfg["_config_path"] = str(tmp / "app.json")
            win = MainWindow(cfg)
            title = win.windowTitle()
            self.assertIn(APP_NAME, title)
            self.assertIn(__version__, title)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
