from pathlib import Path
import json

class ThemeManager:
    def __init__(self, tokens_path: Path):
        self.tokens_path = Path(tokens_path)
        self.tokens = json.loads(self.tokens_path.read_text(encoding="utf-8")) if self.tokens_path.exists() else {}

    def apply(self, app, mode: str="light"):
        qss = ""
        if mode=="dark":
            qss = "QMainWindow{background:#222;color:#eee} QTreeView{border:1px solid #555}"
        else:
            qss = "QMainWindow{background:#fff;color:#222} QTreeView{border:1px solid #ccc}"
        app.setStyleSheet(qss)
