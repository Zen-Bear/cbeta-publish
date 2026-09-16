# -*- coding: utf-8 -*-
"""链路 B 桥接：CBETA XML → 库调用 E:/dev/cbeta/xml2pdf (pycbeta) → pdf/epub。

publish 只做"选预设、传 work ids、收产物"；转换逻辑全在 xml2pdf 侧，
XML 源解析也归对面（`materialize_work`：本地候选源→官方下载）。
publish 侧不再自行定位 XML：CBReader 书库是 P5a（按卷切分），不是对面
要的 P5（整部经），拿 CBReader 路径去找只会喂错文件。
调用方式为进程内库调用（`pycbeta.cli.main(argv)`），不再起子进程：
- 省掉每本一次 python 启动开销；
- 进度/取消/错误都是直接对象，不再解析 stdout / 杀进程。
仅调度，不含转化逻辑（契约见 docs/链路B-设计契约.md）。
"""
import contextlib
import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
X2P_DEFAULT_DIR = "E:/dev/cbeta/xml2pdf"
XML_BOOKS_DEFAULT_DIR = str(PROJECT_ROOT / "cbeta_ebooks_xml")


def _abs(p, base=None):
    """目录统一为绝对路径：相对路径按工程根解析（与各目录默认值一致）。"""
    p = str(p or "")
    if not p:
        return Path(base or PROJECT_ROOT)
    pp = Path(p)
    return pp if pp.is_absolute() else Path(base or PROJECT_ROOT) / p


def _cfg(config):
    return (config or {}).get("xml2pdf", {}) or {}


def _x2p_root(config):
    return Path(_cfg(config).get("path") or X2P_DEFAULT_DIR)


def _ensure_path(x2p):
    x2p = str(x2p or "")
    if x2p and x2p not in sys.path:
        sys.path.insert(0, x2p)


def _run_cli(argv):
    """进程内跑 `pycbeta.cli.main`，返回退出码（ap.error 的 SystemExit 也转为码）。"""
    from pycbeta.cli import main as _cli_main
    try:
        return int(_cli_main(argv) or 0)
    except SystemExit as e:
        try:
            return int(e.code or 1)
        except (TypeError, ValueError):
            return 1


def convert(work_id: str, xml_path, out_file, config: dict, fmt: str = "pdf",
            preset=None, stop=None) -> Path | None:
    """进程内调 pycbeta 生成单个文件。

    xml_path: 本地 XML 路径（一般传 None 直接传 work id，由对面按自家
    配置的 XML 源解析；CBReader 书库是 P5a 按卷切分，不符合对面要的 P5
    整部经，publish 侧不再自行定位）。
    preset: run.json 预设文件路径（None=对面默认）。
    out_file: 显式输出文件路径（publish 侧定名，保证合并可寻址）。
    stop: 可调用对象，调用前返回 True 表示取消。
    返回产物 Path（存在）或 None。
    """
    if stop is not None:
        try:
            if stop():
                return None
        except Exception:
            pass
    x2p = _x2p_root(config)
    if not x2p.exists():
        print("xml2pdf path not found", x2p)
        return None
    _ensure_path(str(x2p))
    out_file = Path(out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    src = str(xml_path) if xml_path else str(work_id)
    argv = ["-i", src, "-f", fmt, "-o", str(out_file)]
    if preset:
        argv += ["--config", str(preset)]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _run_cli(argv)
    except Exception as e:
        print("pycbeta lib fail", e)
        return None
    if code:
        tail = (buf.getvalue() or "")[-500:].strip()
        print("pycbeta fail", code, tail)
        return None
    return out_file if out_file.exists() else None


# ---------- 预设目录 ----------

def preset_dir(config) -> Path:
    """预设目录：配置 preset_dir；缺省为 xml2pdf 仓库下 presets 子目录
    （相对路径按工程根解析）。"""
    d = _cfg(config).get("preset_dir") or ""
    return _abs(d) if d else _x2p_root(config) / "presets"


def list_presets(config) -> list:
    """预设目录下所有合法预设文件名（可解析为 JSON 对象的 *.json；
    run bundle 与纯 presets 均可，对面两种都认；坏文件静默跳过）。"""
    import json
    import re
    d = preset_dir(config)
    out = []
    if not d.exists():
        return out
    try:
        files = sorted(d.glob("*.json"), key=lambda p: p.name.lower())
    except Exception:
        return out
    for p in files:
        try:
            text = p.read_text(encoding="utf-8-sig")
            # run.json 含整行 // 注释：去注释行再解析（行内 URL 不受影响）
            text = re.sub(r"(?m)^\s*//.*$", "", text)
            if isinstance(json.loads(text), dict):
                out.append(p.name)
        except Exception:
            continue
    return out


def resolve_preset(config, name=None):
    """预设名（下拉框存的值）→ 完整路径；空名/不存在返回 None（=对面默认）。"""
    if name is None:
        name = _cfg(config).get("preset", "")
    if not name:
        return None
    p = Path(name)
    if p.is_absolute():
        return p if p.exists() else None
    cand = preset_dir(config) / name
    return cand if cand.exists() else None


def load_preset_dict(path, config=None):
    """读预设文件为 dict（供 XmlOptionsDialog 预填；失败返回 {}）。"""
    try:
        _ensure_path(str(_x2p_root(config)))
        from pycbeta.theme import load_effective_presets
        d = load_effective_presets(str(path))
        return d if isinstance(d, dict) else {}
    except Exception:
        pass
    try:
        import json
        d = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# ---------- 自制书输出目录（完全平展） ----------

def xml_books_dir(config) -> Path:
    """自制书输出根（可配，与官方 cbeta_ebooks 分开；相对路径按工程根解析）。"""
    return _abs((config or {}).get("xml_to_ebooks_dir") or XML_BOOKS_DEFAULT_DIR)


def xml_dest(work: str, fmt: str, base_dir) -> Path:
    """自制书目标路径（平展 `{work}.{fmt}`，publish 定名保证合并可寻址）。"""
    return Path(base_dir) / f"{work}.{fmt}"


def find_built(work: str, fmt: str, base_dir):
    """已生成的自制书：精确名优先，其次 `{work}*.{fmt}`（兼容 GUI 产出的
    `{id 书名}.pdf` 形式）；都没有返回 None。"""
    base = Path(base_dir)
    exact = base / f"{work}.{fmt}"
    if exact.exists():
        return exact
    try:
        cands = sorted(base.glob(f"{work}*.{fmt}"))
    except Exception:
        return None
    return cands[0] if cands else None


def is_fresh(dest, preset_path) -> bool:
    """复用规则：文件存在且比预设新（preset 为空时只看存在）。"""
    dest = Path(dest)
    if not dest.exists():
        return False
    if not preset_path:
        return True
    try:
        return dest.stat().st_mtime >= Path(preset_path).stat().st_mtime
    except Exception:
        return True
