# -*- coding: utf-8 -*-
"""第九轮：状态机与跨文件一致性回归（退出保存/取消水位/配置路径/名称查重）。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class _FakeBox:
    """替身：不弹真实模态框，exec 一律返回「否」。"""
    Warning = QMessageBox.Warning
    Question = QMessageBox.Question
    Yes = QMessageBox.Yes
    No = QMessageBox.No
    Ok = QMessageBox.Ok
    Cancel = QMessageBox.Cancel

    def __init__(self, *a, **k):
        pass

    def setTextFormat(self, *a, **k):
        pass

    def setText(self, *a, **k):
        pass

    def setDefaultButton(self, *a, **k):
        pass

    def exec(self):
        return QMessageBox.No

    @staticmethod
    def question(*a, **k):
        return QMessageBox.Yes

    @staticmethod
    def warning(*a, **k):
        return QMessageBox.Ok


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    cdir = tmp / "collections" / "custom"
    cdir.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    (cdir / "甲.json").write_text(json.dumps(
        {"id": "甲", "name": "甲", "category": "custom", "tags": [],
         "work_ids": []}, ensure_ascii=False), encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["output_dir"] = str(tmp / "out")
    cfg["update_interval"] = "manual"
    cfg["official_library"] = {"root": ""}
    cfg["_config_path"] = str(tmp / "app.json")
    win = MainWindow(cfg)
    win._load_collections()
    return win, tmp


class StateRegressionTest(unittest.TestCase):
    def setUp(self):
        self.win, self.tmp = _make_window()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_close_ignores_when_save_fails(self):
        path = next(str(p) for p, d in self.win._collections
                    if d.get("name") == "甲")
        self.win._changed_colls.add(path)
        self.win._coll_changed = True
        ev = QCloseEvent()
        with mock.patch("cbeta_publish.gui.main_window.atomic_write_text",
                        side_effect=OSError("disk full")), \
                mock.patch("cbeta_publish.gui.main_window.QMessageBox", _FakeBox):
            self.win.closeEvent(ev)
        self.assertFalse(ev.isAccepted())
        self.assertIn(path, self.win._changed_colls)

    def test_cancel_does_not_write_official_watermark(self):
        calls = []
        self.win._download_missing = lambda *a, **k: (
            self.win._dl_stats.update(
                {"ok": 0, "total": 1, "failed": [], "cancel": True}) or True)
        with mock.patch("cbeta_publish.books.official_state.mark_checked",
                        side_effect=lambda *a, **k: calls.append(a)):
            self.win._prepare_official(["T0001"], ["pdf"], self.tmp / "eb",
                                       policy="all")
        self.assertEqual(calls, [])

    def test_save_config_keeps_pending_dirs(self):
        p = Path(self.win._config_path)
        disk = {"mulu_dir": str(self.tmp / "new_mulu"),
                "collections_dir": str(self.tmp / "new_coll"),
                "default_source": "official"}
        p.write_text(json.dumps(disk, ensure_ascii=False), encoding="utf-8")
        self.win.config["default_source"] = "xml"
        self.win._save_config()
        out = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(out["mulu_dir"], str(self.tmp / "new_mulu"))
        self.assertEqual(out["collections_dir"], str(self.tmp / "new_coll"))
        self.assertEqual(out["default_source"], "xml")

    def test_name_taken_is_case_insensitive(self):
        p = self.win._collections[0][0]
        self.win._collections[0][1]["name"] = "Abc"
        self.assertEqual(self.win._name_taken("abc"), str(p))

    def test_settings_dialog_uses_injected_config_path(self):
        import copy
        from cbeta_publish.gui.settings_dialog import SettingsDialog, DEFAULT_CONFIG
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        out = self.tmp / "settings.json"
        cfg["_config_path"] = str(out)
        cfg["mulu_dir"] = str(self.tmp / "mulu")
        cfg["collections_dir"] = str(self.tmp / "coll")
        dlg = SettingsDialog(cfg, None)
        with mock.patch.object(QMessageBox, "information",
                               return_value=QMessageBox.Ok):
            dlg._save()
        self.assertTrue(out.is_file())

    def test_category_corrupt_backs_up_before_save(self):
        from cbeta_publish.collection.category_manager import CategoryManager
        p = self.tmp / "categories.json"
        p.write_text("{bad", encoding="utf-8")
        cm = CategoryManager(p)
        self.assertTrue(cm.corrupt)
        self.assertEqual(cm.all(), [])
        cm.add("x", "X")
        bads = list(self.tmp.glob("categories.json.bad-*"))
        self.assertEqual(len(bads), 1)
        out = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(out["categories"][0]["id"], "x")

    def test_tags_corrupt_backs_up_before_save(self):
        from cbeta_publish.collection.tags_manager import TagsManager
        p = self.tmp / "tags.json"
        p.write_text("{bad", encoding="utf-8")
        tm = TagsManager(p)
        self.assertTrue(tm.corrupt)
        tm.add("标签")
        self.assertEqual(len(list(self.tmp.glob("tags.json.bad-*"))), 1)
        out = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(out["tags"][0]["name"], "标签")

    def test_corrupt_meta_backs_up_and_does_not_raise(self):
        from cbeta_publish.books.remote_manager import RemoteManager
        p = self.tmp / "meta.json"
        p.write_text("{bad", encoding="utf-8")
        rm = RemoteManager(p)
        self.assertEqual(rm.meta, {})
        self.assertEqual(len(list(self.tmp.glob("meta.json.bad-*"))), 1)

    def test_restore_mulu_only_sources_not_config(self):
        import copy
        from cbeta_publish.gui.settings_dialog import SettingsDialog, DEFAULT_CONFIG
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["mulu_dir"] = str(self.tmp / "mulu")
        cfg["_config_path"] = str(self.tmp / "app.json")
        last = self.tmp / "mulu" / "backup" / "last"
        last.mkdir(parents=True)
        (last / "SutraList.json").write_text("{}", encoding="utf-8")
        (last / "app.json").write_text('{"mulu_dir": "x"}', encoding="utf-8")
        dlg = SettingsDialog(cfg, None)
        with mock.patch.object(QMessageBox, "question",
                               return_value=QMessageBox.Yes), \
                mock.patch.object(QMessageBox, "information",
                                  return_value=QMessageBox.Ok):
            dlg._restore_mulu("last")
        self.assertTrue((self.tmp / "mulu" / "SutraList.json").is_file())
        self.assertFalse((self.tmp / "mulu" / "app.json").exists())

    def test_manual_approval_fingerprint_reprompts_when_file_changes(self):
        src = self.tmp / "a.epub"
        src.write_bytes(b"one")
        t1 = ("T1", "epub", str(src), "r")
        self.win._manual_approved[("T1", "epub")] = (src.stat().st_size,
                                                     src.stat().st_mtime_ns)
        self.assertTrue(self.win._is_manual_approved(t1))
        src.write_bytes(b"two-two")
        self.assertFalse(self.win._is_manual_approved(t1))


if __name__ == "__main__":
    unittest.main()
