import sys, os
from pathlib import Path
# 支持 `python -m cbeta_publish.app` 与 `python cbeta_publish/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from cbeta_publish.gui.main_window import MainWindow, apply_ui_fonts
from cbeta_publish.paths import read_user_config, app_root
from cbeta_publish import APP_NAME, APP_ID, __version__

def main():
    # 冻结运行时：若 exe 同级带 ms-playwright（Chromium 浏览器），指给 playwright
    if getattr(sys, "frozen", False):
        _browsers = Path(sys.executable).resolve().parent / "ms-playwright"
        if _browsers.is_dir():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_browsers))
    # 首启：用户配置缺失时从出厂模板 config/app.default.json 复制；
    # 损坏时备份为 app.json.bak-<时间戳> 并恢复出厂（提示延后到主窗显示后，见下）
    cfg, cfg_recovered = read_user_config()
    if not isinstance(cfg, dict):
        cfg = {}
    # 极端情况（出厂模板也缺失/不可写）：给最小默认，避免 KeyError 直接崩
    cfg.setdefault("mulu_dir", str(app_root() / "mulu"))
    cfg.setdefault("collections_dir", str(app_root() / "collections"))
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
    # 恢复外观改版前的观感：应用级浅色样式表（分隔条画成细线而非原生宽抓手）
    app.setStyleSheet("QMainWindow{background:#fff;color:#222}"
                      " QTreeView{border:1px solid #ccc}")
    w=MainWindow(cfg)
    w.show()
    if cfg_recovered:
        w.detail.setText(f"配置文件损坏，已恢复出厂默认"
                         f"（旧文件备份为 {cfg_recovered.name}）")
    sys.exit(app.exec())

if __name__=="__main__":
    main()
