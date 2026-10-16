# -*- coding: utf-8 -*-
"""界面字体：启动即与设置「确定」同路径。

回归（2026-10-15 用户报告）：无父创建的控件（左栏树 `QTreeWidget()`、中栏列表
`QListWidget()`、各下拉框等）**不继承** app 字体，会落在系统默认字体上
（Windows 下=微软雅黑 9，观感比宋体 10 大）；此前要进一次设置「确定」
（`apply_ui_fonts` 逐控件显式 setFont）才变小。现在 `MainWindow.__init__`
末尾统一应用一次，两处一致。
"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.gui.main_window import MainWindow, apply_ui_fonts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window(size=10):
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "collections" / "custom").mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    cfg["ui"] = {"app_font": "SimSun", "app_font_size": size}
    return MainWindow(cfg), tmp


class UiFontTest(unittest.TestCase):
    def setUp(self):
        self.win, self.tmp = _make_window(10)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_startup_applies_font_to_parentless_widgets(self):
        # 构造完成即落在 ui 字体上：左栏树、中栏列表（两者都是无父创建）
        for w in (self.win.tree, self.win.list, self.win.ws_tree):
            f = w.font()
            self.assertEqual(f.family(), "SimSun")
            self.assertEqual(f.pointSize(), 10)

    def test_apply_ui_fonts_updates_parentless_widgets(self):
        # 设置「确定」路径：改字号后左栏树/中栏列表立即跟随
        apply_ui_fonts({"app_font": "SimSun", "app_font_size": 12})
        self.assertEqual(self.win.tree.font().pointSize(), 12)
        self.assertEqual(self.win.list.font().pointSize(), 12)
        apply_ui_fonts({"app_font": "SimSun", "app_font_size": 10})
        self.assertEqual(self.win.tree.font().pointSize(), 10)

    def test_arrows_keep_7pt_after_apply(self):
        # 分隔条 ◀/▶ 箭头带 app_font_keep 标记：apply_ui_fonts 不放大它们
        apply_ui_fonts({"app_font": "SimSun", "app_font_size": 12})
        sp = self.win._splitter
        h = sp.handle(sp.count() - 1)
        btns = [h.layout().itemAt(i).widget() for i in range(h.layout().count())]
        arrows = [b for b in btns
                  if b is not None and hasattr(b, "text") and b.text() in ("◀", "▶")]
        self.assertEqual(len(arrows), 2)
        for b in arrows:
            self.assertEqual(b.font().pointSize(), 7)


if __name__ == "__main__":
    unittest.main()
