import sys, json, os
from pathlib import Path
# 支持 `python -m cbeta_publish.app` 与 `python cbeta_publish/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from cbeta_publish.gui.main_window import MainWindow, apply_ui_fonts
from cbeta_publish.gui.theme.theme_manager import ThemeManager
from cbeta_publish.paths import app_root
from cbeta_publish import APP_NAME, APP_ID, __version__

def main():
    # 冻结运行时：若 exe 同级带 ms-playwright（Chromium 浏览器），指给 playwright
    if getattr(sys, "frozen", False):
        _browsers = Path(sys.executable).resolve().parent / "ms-playwright"
        if _browsers.is_dir():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_browsers))
    cfg_path=app_root()/"config/app.json"
    cfg=json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    ui=cfg.get("ui",{}) or {}
    from cbeta_publish.qt_diag import install as _install_diag
    _diag_log=_install_diag()
    if _diag_log:
        print(f"CBETA_QT_DIAG 日志: {_diag_log}")
    app=QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("CBETA")
    app.setDesktopFileName(APP_ID)
    apply_ui_fonts(ui)
    tm=ThemeManager(Path(__file__).parent/"gui/theme/tokens.json")
    tm.apply(app, cfg.get("theme",{}).get("mode","light"))
    w=MainWindow(cfg)
    w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()
