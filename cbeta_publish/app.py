import sys, json
from pathlib import Path
# 支持 `python -m cbeta_publish.app` 与 `python cbeta_publish/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from cbeta_publish.gui.main_window import MainWindow, apply_ui_fonts
from cbeta_publish.gui.theme.theme_manager import ThemeManager

def main():
    cfg_path=Path(__file__).resolve().parents[1]/"config/app.json"
    cfg=json.loads(cfg_path.read_text(encoding="utf-8"))
    ui=cfg.get("ui",{}) or {}
    app=QApplication(sys.argv)
    apply_ui_fonts(ui)
    tm=ThemeManager(Path(__file__).parent/"gui/theme/tokens.json")
    tm.apply(app, cfg.get("theme",{}).get("mode","light"))
    w=MainWindow(cfg)
    w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
