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
XML_BOOKS_DEFAULT_DIR = str(PROJECT_ROOT / "cbeta_xml_ebooks")
XML_WORK_DEFAULT_DIR = str(PROJECT_ROOT / "cbeta_xml")   # CBETA XML 目录（默认工作根，不可空）


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


def xml_work_dir(config) -> Path:
    """CBETA XML 目录（xml2pdf 的 `--cbeta-ebook` 工作根；空则用默认，不可空）。"""
    return _abs(_cfg(config).get("cbeta_ebook") or XML_WORK_DEFAULT_DIR)


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
    preset: 预设文件路径（命名预设或临时预设；None=对面默认）。
    传参时会被包进一张**临时 run.json**（5 槽沿用 xml2pdf 仓库当前 run.json，
    `config-json` 指向该预设），这样主题 CSS 槽不回出厂；用后删除。
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
    run_wrap = write_run_wrapper(config, preset) if preset else None
    argv = ["-i", src, "-f", fmt, "-o", str(out_file)]
    if run_wrap is not None:
        argv += ["--config", str(run_wrap)]
    elif preset:
        argv += ["--config", str(preset)]
    # CBETA XML 目录（工作根）：不可空，空则用默认
    argv += ["--cbeta-ebook", str(xml_work_dir(config))]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _run_cli(argv)
    except Exception as e:
        print("pycbeta lib fail", e)
        return None
    finally:
        if run_wrap is not None:
            remove_temp_preset(run_wrap)
    if code:
        tail = (buf.getvalue() or "")[-500:].strip()
        print("pycbeta fail", code, tail)
        return None
    return out_file if out_file.exists() else None


def write_run_wrapper(config, preset_path) -> Path | None:
    """为一次调用生成临时 run.json 并返回路径；失败返回 None（调用方回退直传预设）。

    内容：5 槽沿用 xml2pdf 仓库当前 `run.json`，`config-json` 指向本次预设
    （绝对路径）。用后由调用方删除（`remove_temp_preset`）。
    """
    import json
    import tempfile
    try:
        root = _x2p_root(config)
        _ensure_path(str(root))
        import pycbeta.theme as _theme
        # 必须是配置根下那份上游（sys.path/缓存里可能是别处旧的）：否则回退直传
        try:
            if Path(_theme.__file__).resolve().parent.parent != root.resolve():
                return None
        except Exception:
            return None
        from pycbeta.theme import load_run_config, RUN_KEYS
        try:
            run = load_run_config(None, str(root))
        except TypeError:
            run = load_run_config(str(root / "run.json"))
        if not isinstance(run, dict):
            return None
        data = {k: run.get(k, "") for k in RUN_KEYS}
        data["config-json"] = str(Path(preset_path).resolve())
        fd, path = tempfile.mkstemp(prefix="cbeta-publish-run-", suffix=".json")
        import os
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return Path(path)
    except Exception as e:
        print("write run wrapper fail", e)
        return None


# ---------- 预设（xml2pdf 仓库下 presets/，用上游公开 API） ----------

def presets_dir(config) -> Path:
    """配置预设目录：xml2pdf 仓库下 presets/（随仓库发布；名称=文件名 stem）。"""
    return _x2p_root(config) / "presets"


def list_presets(config) -> list:
    """预设名列表（presets/*.json 的 stem，按名排序）。

    走上游公开 API `list_config_presets(root)`；上游不可用时回退本地扫描。
    """
    root = _x2p_root(config)
    try:
        _ensure_path(str(root))
        from pycbeta.gui.panel import list_config_presets
        return [stem for stem, _p in list_config_presets(str(root))]
    except Exception:
        pass
    d = presets_dir(config)
    try:
        return [p.stem for p in sorted(d.glob("*.json"), key=lambda x: x.name.lower())]
    except Exception:
        return []


def resolve_preset(config, name=None):
    """预设名 → 完整路径；空/不存在返回 None（=对面默认）。

    名称可为 presets/ 下的 stem、`x.json` 文件名、或绝对/相对路径。
    """
    if name is None:
        name = _cfg(config).get("preset", "")
    if not name:
        return None
    p = Path(name)
    if p.is_absolute() or p.parent != Path("."):
        cand = p if p.is_absolute() else (PROJECT_ROOT / p)
        return cand if cand.exists() else None
    d = presets_dir(config)
    for cand in (d / name, d / f"{name}.json"):
        if cand.exists():
            return cand
    return None


def load_preset_dict(path_or_name, config=None):
    """读预设为 dict（供 XmlOptionsDialog 预填；失败返回 {}）。

    走上游公开 API `load_config_preset`；上游不可用时回退本地读 JSON。
    """
    root = _x2p_root(config)
    try:
        _ensure_path(str(root))
        from pycbeta.gui.panel import load_config_preset
        d = load_config_preset(str(path_or_name), str(root))
        return d if isinstance(d, dict) else {}
    except Exception:
        pass
    try:
        import json
        import re
        p = Path(path_or_name)
        cands = []
        if p.is_absolute():
            cands = [p]
        else:
            if p.exists():
                cands.append(p)
            pd = root / "presets"
            cands += [pd / p, pd / f"{str(path_or_name)}.json"]
        for cand in cands:
            if not cand.is_file():
                continue
            text = re.sub(r"(?m)^\s*//.*$", "", cand.read_text(encoding="utf-8-sig"))
            d = json.loads(text)
            return d if isinstance(d, dict) else {}
        return {}
    except Exception:
        return {}


def _safe_stem(name):
    """预设名 → 安全文件名 stem（与上游 safe_preset_stem 同规则；空则 ""）。"""
    import re
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", (name or "").strip())
    return stem.strip().strip(".")


def save_preset(config, name, data) -> Path | None:
    """保存预设 dict 到 presets/<name>.json（同名覆盖）；返回路径或 None。

    走上游公开 API `save_config_preset`（内部净化文件名，空名抛错）；
    上游不可用时回退本地写入（同规则净化）。
    """
    root = _x2p_root(config)
    try:
        _ensure_path(str(root))
        from pycbeta.gui.panel import save_config_preset
        return Path(save_config_preset(name, data, str(root)))
    except Exception:
        pass
    try:
        import json
        stem = _safe_stem(name)
        if not stem:
            return None
        d = root / "presets"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{stem}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
    except Exception as e:
        print("save preset fail", e)
        return None


def write_temp_preset(config, data) -> Path | None:
    """把预设 dict 写成**临时**文件（系统临时目录），供 `--config` 用一次。

    用于「调整…」后仅本次生效、不落盘为命名预设的场景；调用方负责用
    `remove_temp_preset` 删除。优先用上游公开 API `panel.write_temp_preset`
    （系统 temp、不碰 presets/ 与 run.json），不可用时本地写。
    """
    root = _x2p_root(config)
    try:
        _ensure_path(str(root))
        from pycbeta.gui.panel import write_temp_preset as _up
        p = _up(data)
        if p:
            return Path(p)
    except Exception:
        pass
    import json
    import tempfile
    try:
        fd, path = tempfile.mkstemp(prefix="cbeta-publish-preset-", suffix=".json")
        import os
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data or {}, f, ensure_ascii=False, indent=2)
        return Path(path)
    except Exception as e:
        print("write temp preset fail", e)
        return None


def remove_temp_preset(path):
    """删除临时预设文件（尽力，失败忽略）。"""
    try:
        if path:
            Path(path).unlink(missing_ok=True)
    except Exception:
        pass


# ---------- 自制书输出目录（`{root}/{fmt}/…`，与官方缓存同构） ----------

def xml_books_dir(config) -> Path:
    """自制书输出根（可配，与官方 cbeta_ebooks 分开；相对路径按工程根解析）。"""
    return _abs((config or {}).get("xml_to_ebooks_dir") or XML_BOOKS_DEFAULT_DIR)


def xml_dest(work: str, fmt: str, base_dir) -> Path:
    """自制书目标路径（`{fmt}/{work}.{fmt}`，publish 定名保证合并可寻址）。"""
    return Path(base_dir) / fmt / f"{work}.{fmt}"


def find_built(work: str, fmt: str, base_dir):
    """已生成的自制书：精确名 `{fmt}/{work}.{fmt}` 优先，其次同目录通配；
    都没有返回 None（旧版平展/`{id 书名}` 兼容已删除，不双读）。"""
    base = Path(base_dir)
    exact = base / fmt / f"{work}.{fmt}"
    if exact.exists():
        return exact
    try:
        cands = sorted((base / fmt).glob(f"{work}*.{fmt}"))
    except Exception:
        return None
    return cands[0] if cands else None


def ensure_one(work: str, fmt: str, base_dir, config, preset=None,
               regen_all: bool = False):
    """确保一部自制书存在，返回 (产物 Path | None, reused: bool)。

    regen_all=False（仅生成缺少）：已有产物直接复用（`find_built`）；
    否则一律重新生成并覆盖原路径。
    """
    hit = find_built(work, fmt, base_dir)
    if not regen_all and hit is not None:
        return hit, True
    out = hit if hit is not None else xml_dest(work, fmt, base_dir)
    got = convert(work, None, out, config, fmt=fmt, preset=preset)
    if got is not None and got.exists():
        return got, False
    return None, False


# ---------- 校验（进程内逐本生成+校验；publish 只管跑与入库） ----------

VERIFY_DEFAULT_DIR = str(PROJECT_ROOT / "cbeta_verify")


def verify_dir(config) -> Path:
    """校验工作根（可配；与自制书目录分离，验证报告不污染复用池）。"""
    return _abs((config or {}).get("verify_dir") or VERIFY_DEFAULT_DIR)


def verify_coll_dir(config, slug: str) -> Path:
    """某丛书的校验目录（产物 `{id 书名}.{fmt}`＋报告落这里/其 `（验证）/` 子目录）。"""
    return verify_dir(config) / (_safe_stem(slug) or "coll")


def verify_work(work: str, fmts, out_dir, config: dict, preset=None, stop=None) -> Path | None:
    """进程内逐本校验：跑 `pycbeta.cli.main([... --verify])`，产物与报告落 out_dir。

    - 有预设时经 `write_run_wrapper` 包临时 run.json（保留仓库主题），用后删。
    - 报告：CLI 写 `{id 书名}（验证）/report.txt`（GUI 写 `{stem}_verify_report.txt`）；
      本函数返回实际报告 Path（存在）或 None。
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
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # 清掉本书旧的 `（验证）` 目录，避免新旧报告混淆（独立窗旧报告会被误读）
    try:
        import shutil as _sh
        for d in out_dir.glob(f"{work}*（验证）"):
            _sh.rmtree(d, ignore_errors=True)
    except Exception:
        pass
    fmt_arg = ",".join(f for f in (fmts or []) if f) or "pdf"
    run_wrap = write_run_wrapper(config, preset) if preset else None
    argv = ["-i", str(work), "-f", fmt_arg, "-o", str(out_dir), "--verify"]
    if run_wrap is not None:
        argv += ["--config", str(run_wrap)]
    elif preset:
        argv += ["--config", str(preset)]
    argv += ["--cbeta-ebook", str(xml_work_dir(config))]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = _run_cli(argv)
    except Exception as e:
        print("pycbeta verify fail", e)
        return None
    finally:
        if run_wrap is not None:
            remove_temp_preset(run_wrap)
    report = find_verify_report(out_dir, str(work))
    if report is None:
        tail = (buf.getvalue() or "")[-500:].strip()
        print("pycbeta verify no report", code, tail)
    return report


def _newest_report(paths):
    """从候选报告里取最新的一份（mtime 大者优先；同刻优先 report.txt＝进程内 CLI）。"""
    best = None
    for p in paths:
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = 0.0
        key = (mt, p.name == "report.txt")
        if best is None or key > best[0]:
            best = (key, p)
    return best[1] if best else None


def find_verify_report(out_dir, work: str) -> Path | None:
    """在 out_dir 下找某书最新校验报告（兼容两种命名）：
    `{id 书名}（验证）/{stem}_verify_report.txt`（独立窗）与 `（验证）/report.txt`（CLI）。"""
    out = Path(out_dir)
    cands = []
    exact = out / f"{work}_verify_report.txt"
    if exact.is_file():
        cands.append(exact)
    try:
        for d in out.glob(f"{work}*（验证）"):
            for name in (f"{work}_verify_report.txt", "report.txt"):
                p = d / name
                if p.is_file():
                    cands.append(p)
    except Exception:
        pass
    return _newest_report(cands)


def verify_reports(out_dir):
    """列出 out_dir 下全部校验报告 [(Path, stem)]，**每个 stem 只取最新一份**
    （同一书可能同时有独立窗的 `{stem}_verify_report.txt` 与 CLI 的 `report.txt`）：
    `*_verify_report.txt` 取文件名 stem；`（验证）/report.txt` 取父目录名前缀。"""
    out = Path(out_dir)
    by_stem = {}
    def _collect(p, stem):
        if not stem:
            return
        prev = by_stem.get(stem)
        by_stem[stem] = p if prev is None else _newest_report([prev, p])
    try:
        for p in out.rglob("*_verify_report.txt"):
            _collect(p, p.name[:-len("_verify_report.txt")])
    except Exception:
        pass
    try:
        for p in out.rglob("report.txt"):
            parent = p.parent.name
            if parent.endswith("（验证）"):
                parent = parent[:-len("（验证）")]
            _collect(p, parent.split(" ", 1)[0] if parent else "")
    except Exception:
        pass
    return [(p, stem) for stem, p in by_stem.items()]


def verify_report_pass(path) -> bool | None:
    """判读上游 `{stem}_verify_report.txt`：有 `[FAIL]`→False；
    ≥1 个 `[OK]` 且无 `[FAIL]`→True；否则 None（未判定，`[--]`/空报告，需人工看）。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    ok = fail = 0
    for ln in text.splitlines():
        s = ln.strip()
        if "[FAIL]" in s:
            fail += 1
        elif "[OK]" in s:
            ok += 1
    if fail:
        return False
    return True if ok else None
