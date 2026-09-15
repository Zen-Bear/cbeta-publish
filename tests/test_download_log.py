# -*- coding: utf-8 -*-
"""下载记录面板：以 \\r 前缀的进度行应替换上一行，使「下载 X ...」与「完成 X」合成一行。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.books.download_worker import REPLACE_LAST  # noqa: E402
from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    col = tmp / "collections" / "custom"
    col.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class DownloadLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _lines(self):
        doc = self.win.log_view.document()
        return [doc.findBlockByNumber(i).text()
                for i in range(doc.blockCount()) if doc.findBlockByNumber(i).text()]

    def test_replace_last_merges_into_one_line(self):
        win = self.win
        win.log_view.clear()
        win._add_record("下载 TX0015.epub ...")
        win._add_record(REPLACE_LAST + "下载 TX0015.epub ...完成 319KB")
        lines = self._lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertEqual(lines[0], "✓ 下载 TX0015.epub ...完成 319KB")

    def test_replace_without_previous_appends(self):
        win = self.win
        win.log_view.clear()
        win._add_record(REPLACE_LAST + "下载 T0001.pdf ...完成 1KB")
        lines = self._lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("完成 1KB", lines[0])

    def test_several_files_one_line_each(self):
        win = self.win
        win.log_view.clear()
        for w in ("T0001", "T0002"):
            win._add_record(f"下载 {w}.pdf ...")
            win._add_record(REPLACE_LAST + f"下载 {w}.pdf ...完成 5KB")
        lines = self._lines()
        self.assertEqual(len(lines), 2, lines)

    def test_progress_dialog_merges_lines(self):
        from PySide6.QtWidgets import QTextBrowser
        win = self.win
        dlg, update, st = win._make_progress("下载", 2)
        try:
            update(0, "下载 T0001.pdf ...")
            update(1, REPLACE_LAST + "下载 T0001.pdf ...完成 5KB")
            log = dlg.findChildren(QTextBrowser)[0]
            doc = log.document()
            lines = [doc.findBlockByNumber(i).text()
                     for i in range(doc.blockCount()) if doc.findBlockByNumber(i).text()]
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("完成 5KB", lines[0])
        finally:
            dlg.close()


class DownloadMissingTest(unittest.TestCase):
    """合并/ZIP/导出 前置：弹进度窗下载缺失书。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _patch(self, ok_works):
        from cbeta_publish.books import official_ebook_source as oes
        real = oes.download_ebook

        def fake(w, fmt, dest_dir):
            if w not in ok_works:
                return None
            p = oes.dest_path(w, fmt, dest_dir)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x" * 2048)
            return p
        oes.download_ebook = fake
        return lambda: setattr(oes, "download_ebook", real)

    def test_all_ok_returns_true(self):
        restore = self._patch({"T0001", "T0002"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T0002", "pdf")],
                                            self.tmp / "eb", title="下载")
        finally:
            restore()
        self.assertTrue(ok)
        self.assertTrue((self.tmp / "eb" / "pdf" / "T" / "T0001.pdf").exists())

    def test_partial_failure_returns_false(self):
        restore = self._patch({"T0001"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T9999", "pdf")],
                                            self.tmp / "eb2", title="下载")
        finally:
            restore()
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
