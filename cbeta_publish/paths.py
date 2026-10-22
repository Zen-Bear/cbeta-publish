# -*- coding: utf-8 -*-
"""运行时路径：统一「工程根 / 数据根」，兼容源码运行与 PyInstaller 冻结。

- 源码运行：数据根 = 仓库根（本文件 parents[1]）。
- 冻结运行（onedir/onefile）：数据根 = **exe 所在目录**，便于把 config/mulu/
  collections/输出目录放在 exe 同级，拷走即用（可写、持久）。

包内只读资源（`cbeta_publish/gui/theme/...`）仍用 `Path(__file__).parent` 定位，
PyInstaller 会随包收集，`__file__` 指向包内，不受本函数影响。
"""
import json
import shutil
import sys
from datetime import datetime
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


#: 打包版出厂模板里会被改写成相对路径、且**按原样消费**的键
_PATH_KEYS = ("mulu_dir", "collections_dir", "official_ebooks_dir",
              "cbeta_ebooks_dir")


def _under_root(value: str) -> str:
    p = Path(value)
    return str(p if p.is_absolute() else app_root() / p)


def normalize_config_paths(cfg):
    """把相对路径按 `app_root()` 归一（**幂等**，只改内存 dict，不写磁盘）。

    打包版 `config/app.default.json` 是便携相对路径（mulu、collections…），
    而程序不改变工作目录；不归一时，从快捷方式/终端以别的 cwd 启动会读错目录。
    只处理真正按原样消费的键：其余键（output_dir/verify_dir/xml_to_ebooks_dir/
    xml2pdf.cbeta_ebook）已由 `_out_dir`/`_abs` 自行按工程根解析。
    """
    if not isinstance(cfg, dict):
        return cfg
    for key in _PATH_KEYS:
        val = cfg.get(key)
        if isinstance(val, str) and val.strip():
            cfg[key] = _under_root(val.strip())
    x2p = cfg.get("xml2pdf")
    if isinstance(x2p, dict):
        val = x2p.get("path")
        if isinstance(val, str) and val.strip():
            x2p["path"] = _under_root(val.strip())
    return cfg


def read_user_config(cfg_path=None, default_path=None):
    """读取用户配置；JSON 损坏时备份并恢复出厂模板。

    返回 `(cfg, backup_path 或 None)`。损坏文件改名为
    `app.json.bak-<年月日-时分秒>`，不静默丢弃用户设置。
    """
    p = Path(cfg_path) if cfg_path else config_dir() / "app.json"
    ensure_user_config(p, default_path)
    try:
        return json.loads(p.read_text(encoding="utf-8-sig")), None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        bak = p.with_name(f"{p.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        try:
            p.replace(bak)
        except OSError:
            bak = None
        ensure_user_config(p, default_path)
        try:
            return json.loads(p.read_text(encoding="utf-8-sig")), bak
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}, bak
