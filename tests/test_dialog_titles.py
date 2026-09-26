# -*- coding: utf-8 -*-
"""弹窗标题永不含应用名：所有对话框/消息框标题均为功能性文字。

背景：用户要求弹窗不加 "CBETA 發佈管理器" 字样；审计确认全仓约 45 处
标题均为功能名（"下载确认"/"失败"…），应用名只出现在主窗口标题栏与
任务栏分组（applicationDisplayName）。本测试锁定该不变量。
"""
import ast
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "CBETA 發佈管理器"


def _literal_titles(path):
    """AST 提取对话框标题字面量：setWindowTitle("…") 与
    QMessageBox.*(parent, "…", …) / _wrap_box(…, "…", …)。变量标题跳过。"""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = ""
        if isinstance(f, ast.Attribute):
            name = f.attr
        elif isinstance(f, ast.Name):
            name = f.id
        args = []
        if name == "setWindowTitle" and node.args:
            args = node.args[:1]
        elif name in ("question", "warning", "information", "critical") and len(node.args) >= 2:
            args = node.args[1:2]
        elif name == "_wrap_box" and len(node.args) >= 2:
            args = node.args[1:2]
        elif name == "getText" and len(node.args) >= 2:
            args = node.args[1:2]
        elif name == "getOpenFileName" and len(node.args) >= 2:
            args = node.args[1:2]
        elif name == "getExistingDirectory" and len(node.args) >= 2:
            args = node.args[1:2]
        elif name == "getColor" and len(node.args) >= 3:
            args = node.args[2:3]
        for a in args:
            if isinstance(a, ast.Constant) and isinstance(a.value, str):
                out.append(a.value)
    return out


class DialogTitleTest(unittest.TestCase):
    def test_no_app_name_in_dialog_titles(self):
        hits = []
        for p in sorted((ROOT / "cbeta_publish").rglob("*.py")):
            for t in _literal_titles(p):
                if APP_NAME in t or "發佈管理器" in t or "发布管理器" in t:
                    hits.append(f"{p.name}: {t}")
        self.assertEqual(hits, [])

    def test_messagebox_title_roundtrip(self):
        # 机制保证：QMessageBox 标题原样回读，不掺应用名
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication.instance() or QApplication([])
        box = QMessageBox(QMessageBox.Warning, "失败", "x", QMessageBox.Ok)
        try:
            self.assertEqual(box.windowTitle(), "失败")
            self.assertNotIn("CBETA", box.windowTitle())
        finally:
            box.deleteLater()


if __name__ == "__main__":
    unittest.main()
