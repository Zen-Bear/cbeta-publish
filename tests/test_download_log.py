# -*- coding: utf-8 -*-
"""下载弹窗：以 \\r 前缀的进度行应替换上一行，使「下载 X ...」与「完成 X」合成一行。

原「下载记录」页签已移除：下载/更新按钮改为弹窗进度（`_make_progress`）。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTextBrowser  # noqa: E402

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

    def _dialog_lines(self, dlg):
        log = dlg.findChildren(QTextBrowser)[0]
        doc = log.document()
        return [doc.findBlockByNumber(i).text()
                for i in range(doc.blockCount()) if doc.findBlockByNumber(i).text()]

    def test_replace_last_merges_into_one_line(self):
        dlg, update, st = self.win._make_progress("下载", 1)
        try:
            update(0, "下载 TX0015.epub ...")
            update(1, REPLACE_LAST + "下载 TX0015.epub ...完成 319KB")
            lines = self._dialog_lines(dlg)
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("完成 319KB", lines[0])
        finally:
            dlg.close()

    def test_replace_without_previous_appends(self):
        dlg, update, st = self.win._make_progress("下载", 1)
        try:
            update(1, REPLACE_LAST + "下载 T0001.pdf ...完成 1KB")
            lines = self._dialog_lines(dlg)
            self.assertEqual(len(lines), 1, lines)
            self.assertIn("完成 1KB", lines[0])
        finally:
            dlg.close()

    def test_several_files_one_line_each(self):
        dlg, update, st = self.win._make_progress("下载", 2)
        try:
            for w in ("T0001", "T0002"):
                update(0, f"下载 {w}.pdf ...")
                update(1, REPLACE_LAST + f"下载 {w}.pdf ...完成 5KB")
            lines = self._dialog_lines(dlg)
            self.assertEqual(len(lines), 2, lines)
        finally:
            dlg.close()

    def test_no_download_record_tab(self):
        # 「下载记录」页签及 log_view 已删除（下载走弹窗）
        win = self.win
        self.assertFalse(hasattr(win, "log_view"))
        names = [win.tab_bottom.tabText(i) for i in range(win.tab_bottom.count())]
        self.assertNotIn("下载记录", names)

    def test_tabs_are_book_info_then_coll_info(self):
        # 右下页签：① 书籍信息 ② 丛书信息（原「下载记录」已删除）
        win = self.win
        tb = win.tab_bottom
        self.assertEqual(tb.count(), 2)
        self.assertEqual([tb.tabText(i) for i in range(2)], ["书籍信息", "丛书信息"])
        self.assertTrue(tb.widget(0).isAncestorOf(win.detail))
        self.assertTrue(tb.widget(1).isAncestorOf(win.lbl_coll_info))

    def test_click_book_activates_book_tab(self):
        # 三栏点书 → 显示书籍信息并切到「书籍信息」页签；点分组节点 → 清空且不切页签
        win = self.win
        win.tab_bottom.setCurrentIndex(1)
        win.nav_combo.setCurrentText("刊本")
        _ensure_app().processEvents()
        ed = win.tree.topLevelItem(0)
        win._on_tree_preview(ed, 0)
        self.assertEqual(win.detail.text(), "")
        self.assertEqual(win.tab_bottom.currentIndex(), 1)
        vol = next((ed.child(i) for i in range(ed.childCount()) if ed.child(i).childCount()), None)
        if vol is not None:
            win._on_tree_preview(vol.child(0), 0)
            self.assertIn("T", win.detail.text())
            self.assertEqual(win.tab_bottom.currentIndex(), 0)

    def test_download_button_uses_popup(self):
        # 下载/更新按钮 => _download_missing 弹窗（不再切页签、不改按钮文案）
        win = self.win
        col = Path(win.config["collections_dir"]) / "custom" / "下载测.json"
        col.parent.mkdir(parents=True, exist_ok=True)
        col.write_text(json.dumps({"id": "dl", "name": "下载测", "category": "custom",
                                   "tags": [], "work_ids": ["T0001", "T0002"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("下载测.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        calls = []
        win._download_missing = lambda pairs, dest, title="下载": calls.append(
            (list(pairs), title)) or True
        win._prompt_save_collection = lambda *a, **k: None
        win.chk_pdf.setChecked(True)
        win.chk_epub.setChecked(True)
        win._on_download_button()
        self.assertEqual(len(calls), 1)
        pairs, title = calls[0]
        self.assertEqual(title, "下载/更新")
        self.assertEqual(sorted(pairs), [("T0001", "epub"), ("T0001", "pdf"),
                                         ("T0002", "epub"), ("T0002", "pdf")])
        self.assertEqual(win.btn_download.text(), "下载/更新")
        col.unlink(missing_ok=True)


class DownloadMissingTest(unittest.TestCase):
    """合并/ZIP/导出 及 下载/更新 共用：弹进度窗下载。"""

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
        self.assertEqual(self.win._dl_stats["ok"], 2)
        self.assertEqual(self.win._dl_stats["total"], 2)

    def test_partial_failure_returns_false(self):
        restore = self._patch({"T0001"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T9999", "pdf")],
                                            self.tmp / "eb2", title="下载")
        finally:
            restore()
        self.assertFalse(ok)
        self.assertIn("T9999", " ".join(self.win._dl_stats["failed"]))

    # ---------- 窗口宽度 / 无错自动关闭 ----------
    def test_progress_dialog_is_narrow(self):
        dlg, update, st = self.win._make_progress("下载", 1)
        try:
            self.assertLessEqual(dlg.minimumWidth(), 520)     # 旧值 640 偏宽
            self.assertLessEqual(dlg.minimumHeight(), 360)
        finally:
            dlg.close()

    def _patch_progress(self):
        # 替换进度窗：只记录 finish 的总结与 autoclose_ms（offscreen 下真窗口会直接关闭）
        win = self.win
        real = win._make_progress
        cap = {}

        def fake(title, total):
            st = {"cancel": False, "lines": [], "oncancel": None,
                  "autoclose_ms": 0, "summary": None}

            def update(done, label="", is_html=False):
                if label:
                    st["lines"].append(str(label))
                return True

            def finish(lines=None):
                st["summary"] = list(lines or [])
            st["finish"] = finish
            cap["st"] = st

            class _D:
                pass
            return _D(), update, st
        win._make_progress = fake
        return cap, lambda: setattr(win, "_make_progress", real)

    def test_autoclose_after_ok_download(self):
        cap, restore_pp = self._patch_progress()
        restore_dl = self._patch({"T0001", "T0002"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T0002", "pdf")],
                                            self.tmp / "eb3", title="下载（合并前）",
                                            autoclose_ok=True)
        finally:
            restore_dl()
            restore_pp()
        self.assertTrue(ok)
        self.assertEqual(cap["st"]["autoclose_ms"], 3000)
        self.assertTrue(any("自动关闭" in x for x in cap["st"]["summary"]), cap["st"]["summary"])

    def test_no_autoclose_on_failure(self):
        cap, restore_pp = self._patch_progress()
        restore_dl = self._patch({"T0001"})
        try:
            ok = self.win._download_missing([("T0001", "pdf"), ("T9999", "pdf")],
                                            self.tmp / "eb4", title="下载（合并前）",
                                            autoclose_ok=True)
        finally:
            restore_dl()
            restore_pp()
        self.assertFalse(ok)
        self.assertEqual(cap["st"]["autoclose_ms"], 0)

    def test_no_autoclose_for_download_button(self):
        # 下载/更新 按钮（autoclose_ok=False）成功也不自动关
        cap, restore_pp = self._patch_progress()
        restore_dl = self._patch({"T0001"})
        try:
            self.win._download_missing([("T0001", "pdf")], self.tmp / "eb5",
                                       title="下载/更新")
        finally:
            restore_dl()
            restore_pp()
        self.assertEqual(cap["st"]["autoclose_ms"], 0)


if __name__ == "__main__":
    unittest.main()
