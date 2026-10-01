# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包定义（onedir）。

用法：由 build_exe.ps1 调用，或
  pyinstaller --clean --noconfirm packaging/cbeta_publish.spec
可用环境变量覆盖：
  PUBLISH_ROOT  仓库根（默认当前工作目录）
  X2P_ROOT      xml2pdf 仓库根（默认 E:/dev/cbeta/xml2pdf；用于收集 pycbeta）
"""
import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

PUBLISH_ROOT = Path(os.environ.get("PUBLISH_ROOT") or os.getcwd()).resolve()
X2P_ROOT = Path(os.environ.get("X2P_ROOT") or r"E:\dev\cbeta\xml2pdf").resolve()

# 可执行/产物名取自唯一来源 cbeta_publish/__init__.py 的 APP_ID（不导入包，避免副作用）
_init_txt = (PUBLISH_ROOT / "cbeta_publish" / "__init__.py").read_text(encoding="utf-8")
_m = re.search(r'APP_ID\s*=\s*"([^"]+)"', _init_txt)
APP_ID = _m.group(1) if _m else "cbeta-publish"

# 诊断用：设 CBETA_CONSOLE=1 则构建带控制台的版本，便于看崩溃堆栈
CONSOLE = os.environ.get("CBETA_CONSOLE") == "1"

datas = []
hiddenimports = []

# 包内只读资源：主题 tokens + 格式图标（经 Path(__file__).parent 定位）
_theme = PUBLISH_ROOT / "cbeta_publish" / "gui" / "theme"
if (_theme / "tokens.json").is_file():
    datas.append((str(_theme / "tokens.json"), "cbeta_publish/gui/theme"))
_icons = _theme / "icons"
if _icons.is_dir():
    datas.append((str(_icons), "cbeta_publish/gui/theme/icons"))

# pycbeta（来自 xml2pdf 仓库）：代码子模块 + 数据文件
# 注意：collect_* 依赖 import，必须先把 X2P_ROOT 加进 sys.path
if X2P_ROOT.is_dir() and str(X2P_ROOT) not in sys.path:
    sys.path.insert(0, str(X2P_ROOT))
if X2P_ROOT.is_dir():
    try:
        hiddenimports += collect_submodules("pycbeta")
        datas += collect_data_files("pycbeta")
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] collect pycbeta failed: {exc}")
else:
    print(f"[spec] X2P_ROOT 不存在，跳过 pycbeta: {X2P_ROOT}")

# 动态/隐式导入的第三方（PyInstaller 未必自动跟到）
for pkg in ("opencc", "ebooklib", "pypinyin", "reportlab",
            "fitz", "tinycss2", "lxml", "lxml.etree", "fontTools",
            "playwright"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        hiddenimports.append(pkg)

a = Analysis(
    [str(PUBLISH_ROOT / "cbeta_publish" / "app.py")],
    pathex=[str(PUBLISH_ROOT), str(X2P_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "numpy", "scipy", "pandas",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtQuick",
        "tests", "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_ID,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=CONSOLE,        # GUI，无控制台窗口（CBETA_CONSOLE=1 时用于诊断）
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_ID,
)
