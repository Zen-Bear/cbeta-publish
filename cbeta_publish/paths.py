# -*- coding: utf-8 -*-
"""运行时路径：统一「工程根 / 数据根」，兼容源码运行与 PyInstaller 冻结。

- 源码运行：数据根 = 仓库根（本文件 parents[1]）。
- 冻结运行（onedir/onefile）：数据根 = **exe 所在目录**，便于把 config/mulu/
  collections/输出目录放在 exe 同级，拷走即用（可写、持久）。

包内只读资源（`cbeta_publish/gui/theme/...`）仍用 `Path(__file__).parent` 定位，
PyInstaller 会随包收集，`__file__` 指向包内，不受本函数影响。
"""
import shutil
import sys
from pathlib import Path


#: 出厂配置模板名（与 config/app.json 同目录，随仓库/安装包分发）
CONFIG_DEFAULT_NAME = "app.default.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """可写数据根目录（config/、mulu/、assets/、collections/、输出目录等）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def config_dir() -> Path:
    return app_root() / "config"


def ensure_user_config(cfg_path=None, default_path=None) -> Path:
    """首启：用户配置不存在时，从出厂模板 ``config/app.default.json`` 复制一份。

    `config/app.json` 是**用户运行期配置**（不进版本库，见 .gitignore），程序会随时
    改写它；出厂默认值放在跟踪的 ``app.default.json``。模板缺失时仅返回路径，
    由调用方自行处理缺失。返回用户配置路径。
    """
    cfg = Path(cfg_path) if cfg_path else config_dir() / "app.json"
    dflt = Path(default_path) if default_path else config_dir() / CONFIG_DEFAULT_NAME
    if not cfg.exists() and dflt.exists():
        cfg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(dflt), str(cfg))
    return cfg
