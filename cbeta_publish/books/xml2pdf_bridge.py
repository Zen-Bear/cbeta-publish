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

from cbeta_publish.paths import app_root

PROJECT_ROOT = app_root()
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
        _track_temp(path)
        return Path(path)
    except Exception as e:
        print("write run wrapper fail", e)
        return None


#: 本进程登记在册、尚未删除的临时文件（退出兜底用；正常流程为零）
_LIVE_TEMP_FILES = set()


def _track_temp(path):
    try:
        import os
        _LIVE_TEMP_FILES.add(os.path.normcase(os.path.abspath(str(path))))
    except Exception:
        pass


def _untrack_temp(path):
    try:
        import os
        _LIVE_TEMP_FILES.discard(os.path.normcase(os.path.abspath(str(path))))
    except Exception:
        pass


def cleanup_live_wrappers():
    """退出兜底：删除登记在册、尚未删除的临时 run/preset 文件；返回已处理路径列表。"""
    import os
    left = sorted(_LIVE_TEMP_FILES)
    _LIVE_TEMP_FILES.clear()
    for p in left:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except Exception:
            pass
    return left


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
            _track_temp(p)
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
        _track_temp(path)
        return Path(path)
    except Exception as e:
        print("write temp preset fail", e)
        return None


def remove_temp_preset(path):
    """删除临时预设文件（尽力，失败忽略）；同时从在册集合注销。"""
    try:
        _untrack_temp(path)
        if path:
            Path(path).unlink(missing_ok=True)
    except Exception:
        pass


# ---------- 自制书输出目录（`{root}/{fmt}/…`，与官方缓存同构） ----------

def xml_books_dir(config) -> Path:
    """自制书输出根（可配，与官方 cbeta_ebooks 分开；相对路径按工程根解析）。"""
    return _abs((config or {}).get("xml_to_ebooks_dir") or XML_BOOKS_DEFAULT_DIR)


def work_dir_of(config, work: str):
    """工作根下该 work 的平展目录（`{id} {书名}` 或恰为 `{id}`）；无则 None。

    与上游 `fetch._find_work_dir` 同规则：排除更长編號误命中（如查 T0349 不命中
    T0349a）。用于推导与上游一致的产物基名 `{id} {书名}`。
    """
    root = xml_work_dir(config)
    try:
        for entry in sorted(root.glob(f"{work}*")):
            if not entry.is_dir():
                continue
            rest = entry.name[len(work):]
            if rest and rest[0].isalnum():
                continue
            return entry
    except Exception:
        pass
    return None


def built_name(config, work: str) -> str:
    """自制书产物基名（不含扩展名）：优先用工作根目录名 `{id} {书名}`
    （与上游 `default_output_name` 同源，保证导入项与直生项同名），
    无工作目录时退回 `{work}`。"""
    d = work_dir_of(config, work)
    return d.name if d is not None else work


def xml_dest(work: str, fmt: str, base_dir, name: str = None):
    """自制书目标路径（`{fmt}/{name}.{fmt}`；name 缺省=work，publish 定名保证合并可寻址）。"""
    return Path(base_dir) / fmt / f"{name or work}.{fmt}"


def find_built(work: str, fmt: str, base_dir):
    """已生成的自制书：精确名 `{fmt}/{work}.{fmt}` 优先，
    其次带书名 `{fmt}/{work} *.{fmt}`（L2 命名，边界=空格，避免 T185 误命中 T1858）；
    都没有返回 None（旧版平展/顶层不双读）。"""
    base = Path(base_dir)
    exact = base / fmt / f"{work}.{fmt}"
    if exact.exists():
        return exact
    try:
        cands = sorted((base / fmt).glob(f"{work} *.{fmt}"))
    except Exception:
        return None
    return cands[0] if cands else None


def source_mtime(config, work: str):
    """该 work 的 XML 源最新 mtime：工作根下其目录内**根级** `*.xml` 取最大。

    xml2pdf 会在同一目录下产出 html/figures/docx 等（也含 xml 派生），只认根级
    `*.xml` 才反映真正的源更新；无工作目录/无 XML 返回 None。
    """
    d = work_dir_of(config, work)
    if d is None:
        return None
    try:
        stamps = [p.stat().st_mtime for p in d.glob("*.xml") if p.is_file()]
    except Exception:
        return None
    return max(stamps) if stamps else None


def source_newer(config, work: str, built) -> bool:
    """XML 源是否比已有自制书新（是则应重制）。任一侧缺失返回 False。"""
    if built is None:
        return False
    try:
        if not Path(built).exists():
            return False
        src = source_mtime(config, work)
        return src is not None and src > Path(built).stat().st_mtime
    except OSError:
        return False


def ensure_one(work: str, fmt: str, base_dir, config, preset=None,
               regen_all: bool = False, name: str = None):
    """确保一部自制书存在，返回 (产物 Path | None, reused: bool)。

    name: 产物基名（不含扩展名）；缺省=work。调用方传 `built_name(config, work)`
    以统一到 L2 带书名布局。
    regen_all=False（仅生成缺少）：已有产物直接复用（`find_built`），但若
    其 XML 源比产物新（`source_newer`）则重新生成并覆盖原路径；
    regen_all=True 一律重新生成并覆盖原路径。
    """
    hit = find_built(work, fmt, base_dir)
    if not regen_all and hit is not None and not source_newer(config, work, hit):
        return hit, True
    out = hit if hit is not None else xml_dest(work, fmt, base_dir, name)
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
    # 本地库预填校验基线（只补缺失；工作目录不存在则跳过，上游 auto_fetch 兜底）
    try:
        from cbeta_publish.books import official_ebook_source as _oes
        _need = {"md": ["txt_notes"], "docx": ["docx", "html"],
                 "txt": ["txt_notes"], "html": ["html"],
                 "epub": ["epub"], "pdf": ["docx"]}
        _kinds = sorted({k for f in (fmts or []) for k in _need.get(f, [])})
        _wdir = work_dir_of(config, work)
        if _wdir is not None and _kinds:
            _seeded = _oes.seed_baselines_from_library(work, _kinds, _wdir, config)
            if _seeded:
                print("seed baselines from library", work, sorted(_seeded))
    except Exception as e:
        print("seed baselines fail", e)
    run_wrap = write_run_wrapper(config, preset) if preset else None
    # 校验阈值（全局配置）：缺+多 ≤ verify_max_diff 判 OK；verify_diff_lines 为失败报告上下文行数。
    # 上游仅 CLI 支持（预设 verify 段无此二项），故始终透传；钳制 0–50。
    try:
        _maxd = int(_cfg(config).get("verify_max_diff", 5))
    except Exception:
        _maxd = 5
    try:
        _dl = int(_cfg(config).get("verify_diff_lines", 5))
    except Exception:
        _dl = 5
    _maxd = max(0, min(50, _maxd))
    _dl = max(0, min(50, _dl))
    argv = ["-i", str(work), "-f", fmt_arg, "-o", str(out_dir), "--verify",
            "--verify-max-diff", str(_maxd), "--verify-diff-lines", str(_dl)]
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


def parse_work_summary_line(line) -> list:
    """解析上游总结行 `[id] N format: 1[docx=OK(0/0)], 2[pdf=1], 3[epub=FAIL(48/97)]`
    （见上游 docs/第三方调用说明.md `format_work_summary`）。

    返回 [(fmt, verdict, missing, extra, reason)]（按行内顺序）：
    verdict True/False/None；missing/extra 为 int 或 None（`?`）；
    reason 为 None（有明确结论）或 "covered:<src_fmt>" / "covered" /
    "no baseline" / "gen not found" / "error…"（未判定原因）。
    fmt 含 `→` 取左侧（产物格式，与上游一致）。
    """
    import re as _re
    m = _re.match(r"^\[([^\]]+)\]\s+\d+\s+format:\s*(.*)$", (line or "").strip())
    if not m:
        return []
    raw_items = _re.findall(r"(\d+)\[([^\]=\s]+)=([^\]]+)\]", m.group(2))
    items = []  # (fmt, kind, payload)
    for _i, fmt_raw, x_raw in raw_items:
        fmt = (fmt_raw or "").split("→")[0].strip()
        if not fmt:
            continue
        x = (x_raw or "").strip()
        mu = _re.match(r"^(OK|FAIL)\(([^/]*)/([^)]*)\)$", x, _re.IGNORECASE)
        if mu:
            def _num(t):
                t = (t or "").strip()
                if t == "" or t == "?":
                    return None
                try:
                    return int(t)
                except ValueError:
                    return None
            items.append((fmt, mu.group(1).upper(),
                          _num(mu.group(2)), _num(mu.group(3))))
        elif x.isdigit():
            items.append((fmt, "ref", int(x), None))
        elif x.upper() == "COVERED":
            items.append((fmt, "covered", None, None))
        elif x.upper() == "NO_BASELINE":
            items.append((fmt, "pending", "no baseline", None))
        elif x.upper() == "NOGEN":
            items.append((fmt, "pending", "gen not found", None))
        else:
            items.append((fmt, "pending", x.lower() or "error", None))
    # 消解被覆盖项（`2[pdf=1]`：结论看同行第 1 条；防环）
    verdicts = []
    for fmt, kind, a, b in items:
        if kind == "OK":
            verdicts.append((True, a, b, None))
        elif kind == "FAIL":
            verdicts.append((False, a, b, None))
        elif kind == "pending":
            verdicts.append((None, None, None, a))
        elif kind == "covered":
            verdicts.append((None, None, None, "covered"))
        else:  # ref
            seen = set()
            tgt = a
            v = None
            while isinstance(tgt, int) and 1 <= tgt <= len(items) and tgt not in seen:
                seen.add(tgt)
                tfmt, tkind, ta, tb = items[tgt - 1]
                if tkind == "OK":
                    v = (True, ta, tb, f"covered:{tfmt}")
                    break
                elif tkind == "FAIL":
                    v = (False, ta, tb, f"covered:{tfmt}")
                    break
                elif tkind == "ref":
                    tgt = ta
                    continue
                break
            verdicts.append(v if v is not None else (None, None, None, "covered"))
    return [(fmt, v, mi, ex, r) for (fmt, *_), (v, mi, ex, r)
            in zip(items, verdicts)]


def _summary_entries(path) -> dict:
    """读报告中全部总结行 → {fmt: (verdict, missing, extra, reason)}。
    多总结行（非常见）时同格式首个胜出；无总结行返回 {}（调用方回退 trial 解析）。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out = {}
    for raw in text.splitlines():
        if "format:" not in raw:
            continue
        for fmt, v, mi, ex, r in parse_work_summary_line(raw):
            if fmt and fmt not in out:
                out[fmt] = (v, mi, ex, r)
    return out


def verify_report_numbers(path) -> dict:
    """总结行缺数/多余数 → {fmt: (missing, extra)}（`?`→None）。
    供导入标签与人工检验显示"缺48/多97"；无总结行返回 {}。"""
    return {f: (mi, ex) for f, (v, mi, ex, r) in _summary_entries(path).items()
            if mi is not None or ex is not None}


def verify_report_pending(path) -> dict:
    """解析报告中的 `[--]` 行 → {product_fmt: reason}（未判定原因，供展示/导入标注）。

    - `[--]  pdf 已覆盖（已由 docx 校验）` → {"pdf": "covered:docx"}
    - `[--]  {disp} no baseline` → {fmt: "no baseline"}（disp 形如 epub 或 pdf→docx，取 → 左侧）
    - `[--]  {disp} gen not found: ...` → {fmt: "gen not found"}
    - 其他 `[--]` → {fmt: 原文}（fmt 取不到时键为 ""，调用方可忽略）

    有上游总结行（`[id] N format: …`）时优先用它：
    `NO_BASELINE`→"no baseline"、`NOGEN`→"gen not found"、
    `ERROR`等→小写原文、`COVERED`（无 ref）→"covered"。
    """
    import re as _re
    summ = _summary_entries(path)
    if summ:
        return {f: r for f, (v, mi, ex, r) in summ.items() if r}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out = {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s.startswith("[--]"):
            continue
        rest = s[len("[--]"):].strip()
        m = _re.search(r"已由\s*(\S+?)\s*校验", rest)
        if m:
            # 「pdf 已覆盖（已由 docx 校验）」：fmt 在行首
            head = _re.split(r"\s+", rest, maxsplit=1)[0]
            fmt = head.split("→")[0].strip()
            out[fmt] = f"covered:{m.group(1)}"
            continue
        low = rest.lower()
        if "no baseline" in low:
            head = _re.split(r"\s+", rest, maxsplit=1)[0]
            out[head.split("→")[0].strip()] = "no baseline"
        elif "gen not found" in low:
            head = _re.split(r"\s+", rest, maxsplit=1)[0]
            out[head.split("→")[0].strip()] = "gen not found"
        else:
            head = _re.split(r"\s+", rest, maxsplit=1)[0]
            out[head.split("→")[0].strip()] = rest
    return out


def apply_verify_coverage(fmt_status: dict, pending: dict) -> dict:
    """docx通过即pdf通过：某格式被记为「已由 src 校验覆盖」，
    且 src 逐格式通过 → 该格式视为通过（返回新 dict，不改入参）。

    覆盖标记两处来源：老报告 `[--] pdf 已覆盖（已由 docx 校验）`（pending
    值为 "covered:docx"）；新总结行无 ref 的 `COVERED`（pending 值为 "covered"，
    此时仅 pdf←docx 套用启发式：docx 通过即 pdf 通过）。
    src 未过/未验时不套用（该格式退回整体判定或未判定）。
    """
    out = dict(fmt_status or {})
    for fmt, reason in (pending or {}).items():
        if not fmt or fmt in out:
            continue
        if isinstance(reason, str) and reason.startswith("covered:"):
            src = reason.split(":", 1)[1]
            if src and out.get(src) is True:
                out[fmt] = True
        elif reason == "covered" and fmt == "pdf" and out.get("docx") is True:
            out[fmt] = True
    return out


def verify_report_pass(path) -> bool | None:
    """判读上游报告：有 `[FAIL]`→False；
    ≥1 个 `[OK]` 且无 `[FAIL]`→True；否则 None（未判定，需人工看）。

    有上游总结行（`[id] N format: …`）时优先用它：
    含 FAIL verdict→False；≥1 OK（含消解为通过的被覆盖项）→True；否则 None。
    """
    summ = _summary_entries(path)
    if summ:
        vals = [v for v, mi, ex, r in summ.values()]
        if any(v is False for v in vals):
            return False
        return True if any(v is True for v in vals) else None
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


def verify_report_formats(path) -> dict:
    """解析报告的**逐格式**结果 → {product_fmt: True/False}（True=通过）。

    有上游总结行（`[id] N format: …`）时优先用它（被覆盖项按 ref 消解）；
    无则回退 trial 解析：
    - CLI `report.txt`：标记行 `[OK]/[FAIL] (…)` 后跟 `{disp} 【源】…`，
      `disp` 形如 `pdf→docx`（取 `→` 左侧为产物格式）或 `epub`/`docx`。
    - 独立窗 `{stem}_verify_report.txt`：标记行内直接含 trial 格式
      `[OK] docx …` / `[FAIL] pdf→docx …`。
    只收录明确 `[OK]/[FAIL]` 的格式；`[--]`（覆盖/无基线）不入表。
    """
    summ = _summary_entries(path)
    if summ:
        return {f: v for f, (v, mi, ex, r) in summ.items() if v is not None}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out = {}
    pending = None
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        mark = None
        if s.startswith("[OK]"):
            mark = True
        elif s.startswith("[FAIL]"):
            mark = False
        elif s.startswith("[--]"):
            pending = None
            continue
        if mark is not None:
            rest = s[s.index("]") + 1:].strip()
            if not rest or rest.startswith("("):
                pending = mark          # CLI：格式在随后的 【源】 行
            else:
                tok = rest.split()[0]   # 独立窗：格式紧跟标记
                fmt = tok.split("→")[0].strip()
                if fmt:
                    out[fmt] = mark
                pending = None
            continue
        if pending is not None and "【源】" in s:
            disp = s.split("【源】")[0].strip()
            fmt = disp.split("→")[0].strip()
            if fmt:
                out[fmt] = pending
            pending = None
    return out


#: 总验证报告固定名（覆盖写；刻意避开单本报告的两种发现模式
#: `*_verify_report.txt` / `（验证）/report.txt`，不参与导入扫描）
VERIFY_SUMMARY_FILENAME = "总验证报告.txt"


def _pending_reason(fmt, pending):
    _r = (pending or {}).get(fmt)
    if _r == "no baseline":
        return "无基线"
    if _r == "gen not found":
        return "无生成档"
    if isinstance(_r, str) and _r.startswith("covered:"):
        return f"由{_r.split(':', 1)[1]}覆盖待定"
    return "未判定"


def write_verify_summary(vdir, coll_name=None):
    """合并校验目录下全部单本报告为总报告（固定名覆盖写；无报告返回 None）。

    摘要行文与 `_do_import_verified` 一致（通过列格式、未通过带缺/多 numbers、
    未判定带原因），只读报告不搬产物；全文区按 stem 排序拼接各报告原文。
    """
    import datetime as _dt
    vdir = Path(vdir)
    try:
        reports = sorted(verify_reports(vdir), key=lambda r: r[1])
    except Exception:
        return None
    if not reports:
        return None
    ok_lines, fail_lines, undet_lines, bodies = [], [], [], []
    for rp, stem in reports:
        label = stem or rp.name
        try:
            text = rp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        fmt_status = apply_verify_coverage(verify_report_formats(rp),
                                           verify_report_pending(rp))
        nums = verify_report_numbers(rp)
        pending = verify_report_pending(rp)
        passed = sorted(f for f, v in fmt_status.items() if v is True)
        bad = sorted(f for f, v in fmt_status.items() if v is False)
        undet = sorted(f for f, v in fmt_status.items() if v is not True and v is not False)
        # [--]-only 格式（如无基线）不在 formats 表里，同样视为未定
        for _f in (pending or {}):
            if _f and _f not in fmt_status and _f not in undet:
                undet.append(_f)
        undet = sorted(undet)

        def _num(f):
            mi, ex = nums.get(f, (None, None))
            if mi is None and ex is None:
                return f
            ms = "?" if mi is None else mi
            es = "?" if ex is None else ex
            return f"{f} 缺{ms}/多{es}"

        def _rs(fs):
            out = []
            for _f in fs:
                _r = _pending_reason(_f, pending)
                out.append(f"{_f}{_r}" if _r != "未判定" else _f)
            return out
        if passed and not bad:
            tail = f"；未入 {'/'.join(_num(f) for f in undet)}" if undet else ""
            ok_lines.append(f"{label} 通过（{'/'.join(passed)}）{tail}")
        elif bad:
            tail = ""
            if undet:
                tail = f"；未入 {'/'.join(_num(f) for f in undet)}"
            fail_lines.append(f"{label} 校验未通过（{'/'.join(_num(f) for f in bad)}）{tail}")
        else:
            rs = _rs(undet)
            suffix = f"（{'/'.join(rs)}）" if rs else ""
            undet_lines.append(f"{label} 未判定{suffix}")
        bodies.append(f"===== {label}（{rp.name}）=====\n{text.rstrip()}")
    total = len(reports)
    head = [f"总验证报告",
            f"丛书：{coll_name or vdir.name}",
            f"时间：{_dt.datetime.now().isoformat(timespec='seconds')}",
            f"共 {total} 部：通过 {len(ok_lines)} 部 / "
            f"未通过 {len(fail_lines)} 部 / 未判定 {len(undet_lines)} 部",
            "（通过=判定格式全过；未通过=任一格式 FAIL；未判定=无 FAIL 但有未定格式）",
            "--- 摘要 ---",
            *([f"通过 {len(ok_lines)} 部："] + [f"・{l}" for l in ok_lines] if ok_lines else []),
            *([f"未通过 {len(fail_lines)} 部："] + [f"・{l}" for l in fail_lines] if fail_lines else []),
            *([f"未判定 {len(undet_lines)} 部："] + [f"・{l}" for l in undet_lines] if undet_lines else []),
            "--- 全文 ---",
            *bodies]
    try:
        out = vdir / VERIFY_SUMMARY_FILENAME
        out.write_text("\n".join(head) + "\n", encoding="utf-8")
        return out
    except OSError:
        return None
