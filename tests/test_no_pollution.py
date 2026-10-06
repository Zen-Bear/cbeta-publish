# -*- coding: utf-8 -*-
"""护栏：测试操作不得写脏真实工程配置/丛书/备份。

历史上曾出现：测试窗口未覆盖 `_config_path`/`collections_dir` → 切来源、保存、
合并元数据写进真实 `config/app.json` 与 `collections/custom/*.json`。
本用例用临时配置跑一遍代表性流程（来源切换/保存/预设切换/设置应用），
断言真实文件哈希不变。
"""
import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

#: 真实工程文件（不得被测试写脏）
REAL_FILES = [
    ROOT / "config" / "app.json",
    ROOT / "config" / "verify_records.json",
    ROOT / "config" / "official_state.json",
    ROOT / "mulu" / "backup" / "last" / "app.json",
    ROOT / "mulu" / "backup" / "original" / "app.json",
] + sorted((ROOT / "collections").rglob("*.json"))

_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _hash(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None


class NoRealConfigPollutionTest(unittest.TestCase):
    def test_representative_ops_do_not_touch_real_files(self):
        _ensure_app()
        from cbeta_publish.gui.main_window import MainWindow
        from cbeta_publish.gui.settings_dialog import SettingsDialog, DEFAULT_CONFIG
        before = {str(p): _hash(p) for p in REAL_FILES}
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
            # 代表性写操作：来源切换/保存、预设切换、显式保存
            win.rb_made.setChecked(True)
            win.src_group.buttonClicked.emit(win.rb_made)
            win._on_preset_changed()
            win._save_config()
            # 设置对话框仅应用（不保存）不应写盘
            dlg = SettingsDialog(copy.deepcopy(DEFAULT_CONFIG), None)
            dlg.ed_organizer_official.setText("临时")
            dlg._apply()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        after = {str(p): _hash(p) for p in REAL_FILES}
        changed = [p for p in before if before[p] != after[p]]
        self.assertEqual(changed, [], f"真实文件被测试写脏：{changed}")


if __name__ == "__main__":
    unittest.main()
