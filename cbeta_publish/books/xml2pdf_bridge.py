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
import json
import re
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


def _id_juan_arg(src, juan=None):
    """`-i` 取值：work id + 卷范围（`ID:spec`）；空 juan 或已是路径/含 `:` 原样。

    与上游 `-i ID:范围`（`split_id_juan`）同形；多段分隔沿用上游 `,`（CLI）。
    """
    s = str(src or "")
    j = str(juan or "").strip()
    if not j or ":" in s or "/" in s or "\\" in s:
        return s
    return f"{s}:{j}"


def _run_cli_convert(src, fmt, output, config, preset, juan=None):
    """构造一次 CLI 调用并返回 `(退出码, 输出尾部)`；调用前不检查停机，由调用方决定。"""
    x2p = _x2p_root(config)
    if not x2p.exists():
        print("xml2pdf path not found", x2p)
        return None, ""
    _ensure_path(str(x2p))
    run_wrap = write_run_wrapper(config, preset) if preset else None
    argv = ["-i", _id_juan_arg(src, juan), "-f", fmt, "-o", str(output)]
    if run_wrap is not None:
        argv += ["--config", str(run_wrap)]
    elif preset:
        argv += ["--config", str(preset)]
    # CBETA XML 目录（工作根）：不可空，空则用默认
    argv += ["--cbeta-ebook", str(xml_work_dir(config))]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return _run_cli(argv), (buf.getvalue() or "")[-500:].strip()
    except Exception as e:
        print("pycbeta lib fail", e)
        return None, ""
    finally:
        if run_wrap is not None:
            remove_temp_preset(run_wrap)


def _product_suffix(fmt: str) -> str:
    if str(fmt).lower() == "txt_notes":
        return ".txt"
    return f".{fmt}"


def _is_product_output(path: Path, fmt: str) -> bool:
    """判断暂存目录里的顶层条目是否为本次请求格式的正式产物。"""
    try:
        if path.name.endswith("（验证）"):
            return False
        if str(fmt).lower() == "html":
            return path.is_dir() and path.name.lower().endswith("_html")
        suffix = _product_suffix(fmt)
        return path.is_file() and path.suffix.lower() == suffix.lower()
    except OSError:
        return False


def _replace_staged_path(src: Path, dest: Path):
    # 文件目标优先原子替换；目录目标必须先清空旧目录。失败不吞源文件诊断。
    try:
        if not (dest.is_dir() and not dest.is_symlink()):
            src.replace(dest)
            return True
        import shutil
        shutil.rmtree(dest, ignore_errors=True)
    except OSError:
        pass
    try:
        import shutil
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(src), str(dest))
        return True
    except OSError as e:
        print("move staged output fail", e)
        return False


def convert_outputs(work_id: str, fmt: str, out_dir, config: dict, preset=None,
                    stop=None, juan=None) -> list:
    """用上游默认命名转换一部作品的全部源文档，返回搬入 `out_dir` 的产物。

    同一 work id 可能对应多个源 XML（如 TX0011 的 TX18/TX19 两册）。
    显式 `-o` 文件会让后渲染的源覆盖先渲染的源，因此这里传输出目录，
    让上游按各自标题落盘，再把产物与报告一起搬回 `out_dir`。
    `juan`（卷范围 `ID:spec` 的 spec）非空时按卷子集渲染，产物名带上游 `（卷…）` 后缀。
    """
    if stop is not None:
        try:
            if stop():
                return []
        except Exception:
            pass
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory(prefix=f"{work_id}-{fmt}-", dir=out_dir) as stage:
        stage_path = Path(stage)
        code, tail = _run_cli_convert(str(work_id), fmt, stage_path, config, preset,
                                      juan=juan)
        if code:
            print("pycbeta fail", code, tail)
            return []
        moved = []
        try:
            entries = sorted(stage_path.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return []
        for child in entries:
            dest = out_dir / child.name
            if not _replace_staged_path(child, dest):
                continue
            if _is_product_output(dest, fmt) and not dest.name.endswith("_转换报告.txt"):
                moved.append(dest)
        if not moved:
            print(f"pycbeta produced no {fmt} output for {work_id}")
            return []
        return sorted(moved, key=lambda p: p.name.lower())


def convert(work_id: str, xml_path, out_file, config: dict, fmt: str = "pdf",
            preset=None, stop=None, juan=None) -> Path | None:
    """进程内调 pycbeta 生成单个文件。

    xml_path: 本地 XML 路径（一般传 None 直接传 work id，由对面按自家
    配置的 XML 源解析；CBReader 书库是 P5a 按卷切分，不符合对面要的 P5
    整部经，publish 侧不再自行定位）。
    preset: 预设文件路径（命名预设或临时预设；None=对面默认）。
    传参时会被包进一张**临时 run.json**（5 槽沿用 xml2pdf 仓库当前 run.json，
    `config-json` 指向该预设），这样主题 CSS 槽不回出厂；用后删除。
    out_file: 显式输出文件路径（publish 侧定名，保证合并可寻址）。
    注意：多源 work 不要用显式 `-o`（后渲染的源会覆盖先渲染的源），
    请用 `convert_outputs` 走输出目录。
    juan: 卷范围 spec（`ID:spec` 的 spec）；非空按卷子集渲染（显式 `-o` 不加后缀，
    调用方需自行按上游模板定名，见 `resolve_juan_suffix`）。
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
    code, tail = _run_cli_convert(src, fmt, out_file, config, preset, juan=juan)
    if code:
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


def work_source_files(config, work: str) -> list:
    """该 work 在本地工作目录内的根级源 XML 列表（排序、确定性）。

    同一 work id 可能对应多个源文档（如 TX0011 的 TX18/TX19 两册）。
    只看已缓存的工作目录，不触发下载或材料化。
    """
    d = work_dir_of(config, work)
    if d is None:
        return []
    try:
        return sorted(
            (p for p in d.iterdir() if p.is_file() and p.suffix.lower() == ".xml"),
            key=lambda p: p.name.lower())
    except OSError:
        return []


def find_all_built(work: str, fmt: str, base_dir):
    """已生成的自制书全部产物（排序、确定性）：精确名优先，其次带书名通配。

    一个 work 可能对应多个源文档，因此也可能对应多个产物。
    """
    base = Path(base_dir)
    exact = base / fmt / f"{work}.{fmt}"
    out = [exact] if exact.is_file() else []
    try:
        cands = sorted((base / fmt).glob(f"{work} *.{fmt}"),
                       key=lambda p: p.name.lower())
    except OSError:
        return out
    for cand in cands:
        if cand.is_file() and cand != exact:
            out.append(cand)
    return out


def find_built(work: str, fmt: str, base_dir):
    """已生成的自制书代表产物：`find_all_built` 的第一项，无则 None。"""
    found = find_all_built(work, fmt, base_dir)
    return found[0] if found else None


def find_all_built_entry(work: str, fmt: str, base_dir, juan=""):
    """条目产物：卷非空取带 `（卷…）` 后缀者；整本取无卷后缀者（回退全部）。"""
    allp = find_all_built(work, fmt, base_dir)
    j = str(juan or "").strip()
    if not j:
        return [p for p in allp if "（卷" not in p.stem] or allp
    suffix = f"（卷{j}）"
    return [p for p in allp if p.stem.endswith(suffix)]


def source_mtime(config, work: str):
    """该 work 的 XML 源最新 mtime：工作根下其目录内**根级** `*.xml` 取最大。

    xml2pdf 会在同一目录下产出 html/figures/docx 等（也含 xml 派生），只认根级
    `*.xml` 才反映真正的源更新；无工作目录/无 XML 返回 None。
    """
    try:
        stamps = [p.stat().st_mtime for p in work_source_files(config, work)]
    except OSError:
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


def sources_newer(config, work: str, built_list) -> bool:
    """任一已有产物是否比最新 XML 源旧（任一旧即应重制）。"""
    latest = source_mtime(config, work)
    if latest is None:
        return False
    try:
        return any(Path(p).stat().st_mtime < latest for p in built_list)
    except OSError:
        return True


def _outputs_current(existing, sources, fresh: bool) -> bool:
    if not existing:
        return False
    if sources and len(existing) < len(sources):
        # 已有多源但产物不全：保守重制，避免沿用被覆盖的旧产物。
        return False
    return fresh


def ensure_products(work: str, fmt: str, base_dir, config, preset=None,
                    regen_all: bool = False, name: str = None, juan=None):
    """确保一部作品该格式的全部自制产物存在，返回 ([Path...], 全部复用?)。

    同一 work id 可能对应多个源 XML（如 TX0011 的 TX18/TX19 两册），
    此时上游默认命名才能区分产物；只有在源集合已知为单文件时才沿用
    `name`/精确路径的旧行为。`name` 在多源批量生成中不作为输出名。
    `juan`（卷范围 spec）非空时恒走输出目录模式，由上游按卷子集命名
    （显式 `-o` 不加 `（卷…）` 后缀）。
    """
    base_dir = Path(base_dir)
    out_dir = base_dir / fmt
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    existing = find_all_built_entry(work, fmt, base_dir, juan)
    sources = work_source_files(config, work)
    if not regen_all and _outputs_current(
            existing, sources, not sources_newer(config, work, existing)):
        return existing, True
    if not juan and sources and len(sources) == 1 and len(existing) <= 1:
        target = existing[0] if existing else xml_dest(work, fmt, base_dir, name)
        got = convert(work, None, target, config, fmt=fmt, preset=preset)
        if got is not None and got.exists():
            return [got], False
        return [], False
    outputs = convert_outputs(work, fmt, out_dir, config, preset=preset, juan=juan)
    if not outputs:
        return [], False
    if sources and len(outputs) == len(sources):
        # 本轮是完整重制：删掉同 work 下未再生成的旧名残留，避免旧坏文件继续被复用。
        current = {p.name for p in outputs}
        for old in existing:
            if old.name not in current:
                try:
                    if old.exists():
                        old.unlink()
                except OSError:
                    pass
    return outputs, False


def ensure_one(work: str, fmt: str, base_dir, config, preset=None,
               regen_all: bool = False, name: str = None, juan=None):
    """确保一部自制书存在，返回 (代表产物 Path | None, 全部复用?)。

    兼容旧的单产物调用；多源 work 会生成全部产物，但只返回第一项。
    需要全部产物时请用 `ensure_products`。
    """
    outputs, reused = ensure_products(work, fmt, base_dir, config,
                                      preset=preset, regen_all=regen_all,
                                      name=name, juan=juan)
    return (outputs[0] if outputs else None), reused


def adopt_pdf_companions(work: str, pdf_outs, base_dir, drop_stale: bool = False):
    """把本轮 PDF 产物的伴生 docx 认领为 docx 产物（省一次 docx 渲染）。

    上游 docx2pdf 管线在 PDF 成功产出时，总在输出根附一份同内容、同 stem 的
    docx（唯一目的是 `--verify-only` 定位；无条件覆盖写）。publish 从不用
    verify-only，pdf+docx 同跑时可直接把这份 docx 搬进 `docx/`，免去再次渲染。
    仅应在本轮 PDF **真实渲染**（非复用）后调用；html2pdf 管线无伴生，返回空。
    `drop_stale=True`（重制路径）：清理 docx 目录内同 work 的过期异名残留，
    与 `ensure_products` 重制后的清理语义对齐。单个文件失败只跳过该文件。
    """
    base = Path(base_dir)
    docx_dir = base / "docx"
    adopted = []
    for pdf in (pdf_outs or []):
        try:
            cand = Path(pdf).parent / f"{Path(pdf).stem}.docx"
            if not cand.is_file():
                continue
            docx_dir.mkdir(parents=True, exist_ok=True)
            dest = docx_dir / cand.name
            if _replace_staged_path(cand, dest) and dest.is_file():
                adopted.append(dest)
        except OSError as e:
            print("adopt pdf companion fail", e)
    if drop_stale and adopted:
        current = {p.name for p in adopted}
        for old in find_all_built(work, "docx", base):
            if old.name not in current:
                try:
                    if old.exists():
                        old.unlink()
                except OSError:
                    pass
    return adopted


# ---------- 校验（进程内逐本生成+校验；publish 只管跑与入库） ----------

VERIFY_DEFAULT_DIR = str(PROJECT_ROOT / "cbeta_verify")


def verify_dir(config) -> Path:
    """校验工作根（可配；与自制书目录分离，验证报告不污染复用池）。"""
    return _abs((config or {}).get("verify_dir") or VERIFY_DEFAULT_DIR)


def verify_coll_dir(config, slug: str) -> Path:
    """某丛书的校验目录（产物 `{id 书名}.{fmt}`＋报告落这里/其 `（验证）/` 子目录）。"""
    return verify_dir(config) / (_safe_stem(slug) or "coll")


def verify_work(work: str, fmts, out_dir, config: dict, preset=None, stop=None,
                juan=None) -> Path | None:
    """进程内逐本校验：跑 `pycbeta.cli.main([... --verify])`，产物与报告落 out_dir。

    - 有预设时经 `write_run_wrapper` 包临时 run.json（保留仓库主题），用后删。
    - 报告：CLI 写 `{id 书名}（验证）/{id}_{书名}_校验报告.txt`
      （旧版为 `report.txt`，仍兼容读）；本函数返回实际报告 Path（存在）或 None。
    - juan: 卷范围 spec；非空时 `-i ID:spec` 按卷子集校验（上游产物/报告目录名带
      `（卷…）` 后缀，`find_verify_report` 的 `{work}*（验证）` 通配仍命中）。
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
    # 清新版布局 `{out}/验证/` 下本书旧的 `（验证）` 目录，避免新旧报告混淆
    # （顶层旧目录保留，供旧报告兼容读取）
    try:
        import shutil as _sh
        for d in (out_dir / VERIFY_ROOT_NAME).glob(f"{work}*（验证）"):
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
    # 默认 max_diff=0（严格：仅 0/0 通过；注释差异由 publish 验收档处理）、diff_lines=5。
    try:
        _maxd = _cfg(config).get("verify_max_diff", 0)
        _maxd = 0 if _maxd is None else int(_maxd)
    except Exception:
        _maxd = 0
    try:
        _dl = _cfg(config).get("verify_diff_lines", 5)
        _dl = 5 if _dl is None else int(_dl)
    except Exception:
        _dl = 5
    _maxd = max(0, min(50, _maxd))
    _dl = max(0, min(50, _dl))
    argv = ["-i", _id_juan_arg(str(work), juan), "-f", fmt_arg, "-o", str(out_dir), "--verify",
            "--verify-max-diff", str(_maxd), "--verify-diff-lines", str(_dl)]
    # 校验根钉死到 `{out_dir}/验证`：CLI `--verify-root` 显式优先，预设
    # `source.verify_root` 劫持不到（报告才能落回 publish 托管区）
    argv += ["--verify-root", str(out_dir / VERIFY_ROOT_NAME)]
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
    """在 out_dir 下找某书最新校验报告（兼容三种命名）：
    `{id 书名}（验证）/{id}_{书名}_校验报告.txt`（新）、
    `{id 书名}（验证）/{stem}_verify_report.txt`（独立窗旧）与
    `（验证）/report.txt`（CLI 旧）。"""
    out = Path(out_dir)
    cands = []
    exact = out / f"{work}_verify_report.txt"
    if exact.is_file():
        cands.append(exact)
    exact2 = out / f"{work}_校验报告.txt"
    if exact2.is_file():
        cands.append(exact2)
    try:
        # 顶层旧布局 ＋ 上游新布局 `{out}/验证/{id 书名}（验证）/`
        _dirs = list(out.glob(f"{work}*（验证）"))
        _dirs += list((out / VERIFY_ROOT_NAME).glob(f"{work}*（验证）"))
        for d in _dirs:
            for name in (f"{work}_verify_report.txt", "report.txt"):
                p = d / name
                if p.is_file():
                    cands.append(p)
            # 新命名：{id}_{书名}_校验报告.txt（与旧 report.txt 同目录去重）
            for p in d.glob("*_校验报告.txt"):
                if p.is_file():
                    cands.append(p)
    except Exception:
        pass
    return _newest_report(cands)


def _report_group_key(path, stem: str):
    """同一校验语义的报告归一组；不同语义产物（如同一 work 的上/中下）各自保留。

    `(验证)` 目录名是上游默认产物名：同一目录内的新旧命名（`report.txt` /
    `{stem}_verify_report.txt` / `{id}_{书名}_校验报告.txt`）取最新；
    不同语义产物在不同目录，各自保留。
    """
    parent = Path(path).parent
    if parent.name.endswith("（验证）"):
        return ("dir", parent.name[:-len("（验证）")])
    name = Path(path).name
    if name.endswith("_verify_report.txt"):
        return (stem, name[:-len("_verify_report.txt")])
    if name.endswith("_校验报告.txt"):
        return (stem, name[:-len("_校验报告.txt")])
    return (stem, name)


def _report_group_identity(path) -> str:
    """报告对应的产物语义名（校验目录名或报告文件名去掉验证后缀）。"""
    path = Path(path)
    parent = path.parent
    if parent.name.endswith("（验证）"):
        return parent.name[:-len("（验证）")]
    if path.name.endswith("_verify_report.txt"):
        return path.name[:-len("_verify_report.txt")]
    if path.name.endswith("_校验报告.txt"):
        return path.name[:-len("_校验报告.txt")]
    return ""


def _head_token(s):
    """token/stem 的 work 头：剥 `:范围` 与 `_NNN` 卷后缀（`T0001_001`→`T0001`）。"""
    s = str(s or "").strip()
    m = re.match(r"^([^:：]+)[:：]", s)
    if m:
        s = m.group(1).strip()
    m2 = re.match(r"^(.+)_\d{1,3}$", s)
    if m2:
        s = m2.group(1)
    return s


def _verify_stem_matches(stem: str, work: str) -> bool:
    # 新命名用下划线分隔（T0001_长阿含经_校验报告.txt），同样按分隔符匹配，
    # 避免 T185 误命中 T1858（要求分隔符后一位对齐）。
    # 先剥两侧卷后缀（`:范围`/`_NNN`）：旧脏 id `T0001_001` 与 `T0001` 视为同一部。
    if not stem or not work:
        return False
    stem = _head_token(stem)
    work = _head_token(work)
    return (stem == work or stem.startswith(work + " ")
            or stem.startswith(work + "_"))


def work_verify_reports(out_dir, work: str, primary=None):
    """某 work 在校验目录中的全部相关报告（同一 work 的不同语义产物各保留）。

    `primary` 是本次 `verify_work` 返回的报告：即使它不在标准扫描命名里
    （测试替身常见），也一并纳入，避免聚合时漏掉。没有本次报告时不回退
    扫描旧报告，避免把旧报告当作本次结论。
    """
    if primary is None:
        return []
    matches = [p for p, stem in verify_reports(out_dir)
               if _verify_stem_matches(stem, work)]
    if all(Path(p) != Path(primary) for p in matches):
        matches.append(Path(primary))
    return matches


def verify_reports(out_dir):
    """列出 out_dir 下全部校验报告 [(Path, stem)]，**每个语义产物只取最新一份**

    （同一书可能同时有独立窗的 `{stem}_verify_report.txt`、CLI 的 `report.txt`、
    新命名的 `{id}_{书名}_校验报告.txt`；同一 work 的不同语义产物，例如 TX0011 的上/中下，会分别保留）。
    `*_verify_report.txt` 与 `*_校验报告.txt` 取文件名 stem；`（验证）/report.txt` 取父目录名前缀。
    同一验证目录内的新旧命名按同一组去重（取最新）。"""
    out = Path(out_dir)
    by_group = {}
    def _collect(p, stem):
        if not stem:
            return
        key = _report_group_key(p, stem)
        prev = by_group.get(key)
        if prev is None:
            by_group[key] = (p, stem)
        else:
            newest = _newest_report([prev[0], p])
            by_group[key] = (p, stem) if newest is p else prev
    try:
        for p in out.rglob("*_verify_report.txt"):
            _collect(p, p.name[:-len("_verify_report.txt")])
    except Exception:
        pass
    try:
        for p in out.rglob("*_校验报告.txt"):
            _collect(p, p.name[:-len("_校验报告.txt")])
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
    return [(p, stem) for p, stem in by_group.values()]


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


#: 机读结论固定名（上游 2026-10-07 起 CLI/GUI 统一；旧 JSON 名不再被发现）
VERIFY_JSON_FILENAME = "report.json"
#: 上游校验根目录名（默认校验根 = `{输出}/验证`；publish 钉死到 `{out_dir}/验证`）
VERIFY_ROOT_NAME = "验证"
#: diff_scope 文案与保守合并序（上游说明 §3：body > unknown > notes_only）
_DIFF_SCOPE_TEXT = {"notes_only": "差异仅注释", "body": "含正文差异",
                    "unknown": "范围未知"}
_DIFF_SCOPE_RANK = {"body": 2, "unknown": 1, "notes_only": 0}


def diff_scope_text(scope) -> str:
    """diff_scope → 展示文案（空/未知值返回 ""）。"""
    return _DIFF_SCOPE_TEXT.get(scope or "", "")


def conservative_diff_scope(scopes):
    """多格式/多报告范围取最保守（body > unknown > notes_only）；无则 None。"""
    best = None
    for s in scopes or []:
        if s in _DIFF_SCOPE_RANK and (best is None
                                      or _DIFF_SCOPE_RANK[s] > _DIFF_SCOPE_RANK[best]):
            best = s
    return best


def _paired_json(report_path):
    """报告同目录的机读 `report.json`（不存在返回 None）。

    上游 2026-10-07 起 CLI/GUI 统一此名；旧名 `{id}_{书名}_校验报告.json` /
    `*_verify_report.json` 上游已不再发现，publish 同口径不认（旧目录走 txt 回退）。
    """
    try:
        p = Path(report_path).parent / VERIFY_JSON_FILENAME
        return p if p.is_file() else None
    except Exception:
        return None


def _read_verify_json(report_path):
    """读配对的 `report.json` → 归一 dict；不可用返回 None（调用方回退 txt）。

    - 容错：utf-8-sig；解析失败／非 dict／`schema != 1`／无 `fmts` → None；
    - 归一：`{fmts: {fmt: {verdict, missing, extra, reason, diff_scope,
      formal_outputs, fingerprint}}, coverage, inputs}`，其中 `inputs` 为
      `inputs.xml_files` 基名列表（保序，供跨边指纹重算）；未知字段忽略（上游约定）。
    """
    jp = _paired_json(report_path)
    if jp is None:
        return None
    try:
        data = json.loads(jp.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("schema") != 1:
        return None
    fmts_raw = data.get("fmts")
    if not isinstance(fmts_raw, dict):
        return None
    out = {"fmts": {}, "coverage": {}, "inputs": [], "juan": None}
    for fmt, info in fmts_raw.items():
        if not fmt or not isinstance(info, dict):
            continue
        _mi = info.get("missing")
        _ex = info.get("extra")
        _scope = info.get("diff_scope")
        _fp = info.get("fingerprint")
        out["fmts"][str(fmt)] = {
            "verdict": str(info.get("verdict") or ""),
            "missing": _mi if isinstance(_mi, int) else None,
            "extra": _ex if isinstance(_ex, int) else None,
            "reason": info.get("reason") if isinstance(info.get("reason"), str) else None,
            "diff_scope": _scope if _scope in _DIFF_SCOPE_RANK else None,
            "formal_outputs": [str(p) for p in (info.get("formal_outputs") or [])
                               if isinstance(p, (str, Path)) and str(p)],
            "fingerprint": _fp if isinstance(_fp, str) and _fp else None,
        }
    _inp = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}
    for x in (_inp.get("xml_files") or []):
        if isinstance(x, dict) and x.get("name"):
            out["inputs"].append(str(x["name"]))
    _cov = _inp.get("coverage")
    if isinstance(_cov, dict):
        out["coverage"] = {str(k): str(v) for k, v in _cov.items() if k and v}
    _j = data.get("juan")
    if isinstance(_j, dict):
        _segs = _j.get("segments")
        _lab = _j.get("label")
        if isinstance(_segs, list) or isinstance(_lab, str):
            out["juan"] = {"segments": _segs if isinstance(_segs, list) else [],
                           "label": str(_lab or "")}
    return out


def _json_pending_reason(reason):
    """上游 reason（可能 `; ` 连接多段）→ publish pending 词汇。

    `no_baseline`→"no baseline"；`gen_not_found`→"gen not found"；
    `covered:*` 原样；其余原文（no_record / error 详情等）。
    """
    for tok in [t.strip() for t in str(reason or "").split(";") if t.strip()]:
        if tok == "no_baseline":
            return "no baseline"
        if tok == "gen_not_found":
            return "gen not found"
        if tok.startswith("covered:"):
            return tok
    return str(reason or "").strip() or "未判定"


def verify_json_formats(path):
    """`report.json` 声明的（请求过并判定的）格式集；无 json 返回 None。"""
    rj = _read_verify_json(path)
    return sorted(rj["fmts"]) if rj is not None else None


def verify_report_diff_scopes(path) -> dict:
    """逐格式 diff_scope → `{fmt: notes_only|body|unknown}`（仅 json；txt → {}）。"""
    rj = _read_verify_json(path)
    if rj is None:
        return {}
    return {f: i["diff_scope"] for f, i in rj["fmts"].items() if i["diff_scope"]}


def verify_report_comparison_files(path) -> dict:
    """逐格式比对档（`formal_outputs` 存在者）→ `{fmt: [Path]}`；txt → {}。

    仅供人工检验"打开比对档"链接（比对档≠正式产物，不可作导入源）。
    """
    rj = _read_verify_json(path)
    if rj is None:
        return {}
    out = {}
    for f, i in rj["fmts"].items():
        files = [Path(p) for p in i["formal_outputs"]]
        files = [p for p in files if p.is_file()]
        if files:
            out[f] = files
    return out


#: 注释差异自动接受上限（total=缺+多 ≤ 此值 且 diff_scope=="notes_only"）。
#: 与验证阈值（verify_max_diff=0，严格仅 0/0）互补：0 差异直接入库；小注释差异也入库。
ACCEPT_NOTES_DIFF_MAX = 10


def accept_tier(passed: bool, mi, ex, scope) -> str | None:
    """单格式接受档：'strict' | 'notes_only' | None（人工）。

    - 逐格式判定通过 → strict；
    - 未通过但 missing/extra 均为 int、合计 ≤ ACCEPT_NOTES_DIFF_MAX 且
      scope=="notes_only" → notes_only；
    - 余下（正文差异/超限/数未知/未判定）→ None，走人工检验。
    """
    if passed:
        return "strict"
    if (isinstance(mi, int) and isinstance(ex, int)
            and (mi + ex) <= ACCEPT_NOTES_DIFF_MAX and scope == "notes_only"):
        return "notes_only"
    return None


def verify_json_inputs_names(report_path):
    """配对 report.json 的 `inputs.xml_files` 基名列表（保序）；无则 None。"""
    rj = _read_verify_json(report_path)
    if rj is None:
        return None
    return list(rj.get("inputs") or [])


def verify_json_juan(report_path):
    """配对 report.json 的卷标签（`juan.label`）；无 json／整本返回 ""。"""
    rj = _read_verify_json(report_path)
    if rj is None:
        return ""
    j = rj.get("juan") or {}
    return str(j.get("label") or "") if isinstance(j, dict) else ""


def juan_segments(config, spec):
    """卷范围 spec → 上游归一 [(lo,hi)]；空/非法/上游不可用返回 None。

    `、`（显示分隔）先归一为 `,`（上游 `parse_juan_spec` 分隔符）。
    """
    s = str(spec or "").strip()
    if not s:
        return None
    try:
        _ensure_path(str(_x2p_root(config)))
        from pycbeta.juan import parse_juan_spec
        return parse_juan_spec(s.replace("、", ","))
    except Exception:
        return None


def juan_label(config, spec):
    """卷范围 spec → 上游规范标签（`format_juan_label`）；不可用回退原文。"""
    segs = juan_segments(config, spec)
    if segs is None:
        return str(spec or "").strip()
    try:
        from pycbeta.juan import format_juan_label
        return format_juan_label(segs)
    except Exception:
        return str(spec or "").strip()


def verify_reports_dir(config):
    """上游报告扫描根：显式 `xml2pdf.verify_reports_dir` 优先，否则取生效预设的
    `source.verify_root`；都无则 None（跨边导入功能关闭）。"""
    try:
        x = _cfg(config)
        v = str(x.get("verify_reports_dir") or "").strip()
        if v:
            return Path(v)
        pp = resolve_preset(config)
        d = load_preset_dict(pp, config) if pp else {}
        v2 = str(((d or {}).get("source") or {}).get("verify_root") or "").strip()
        return Path(v2) if v2 else None
    except Exception:
        return None


def find_upstream_reports(config, reports_dir):
    """经上游公开接口扫描报告根 → [{id,title,dir,report_json,report_txt}]；失败回 []。"""
    try:
        _ensure_path(str(_x2p_root(config)))
        from pycbeta.verify import find_verify_reports
        got = find_verify_reports(str(reports_dir))
        return [e for e in (got or []) if isinstance(e, dict)]
    except Exception:
        return []


def verify_report_numbers(path) -> dict:
    """缺数/多余数 → {fmt: (missing, extra)}（`?`→None）。

    `report.json` 存在时直读 `missing/extra`；否则按总结行解析。
    供导入标签与人工检验显示"缺48/多97"；都无返回 {}。
    """
    rj = _read_verify_json(path)
    if rj is not None:
        return {f: (i["missing"], i["extra"]) for f, i in rj["fmts"].items()
                if i["missing"] is not None or i["extra"] is not None}
    return {f: (mi, ex) for f, (v, mi, ex, r) in _summary_entries(path).items()
            if mi is not None or ex is not None}


def verify_report_pending(path) -> dict:
    """解析未判定项 → {product_fmt: reason}（供展示/导入标注）。

    `report.json` 存在时按其 `undetermined/error` 的 reason 映射；
    pdf 的 reason 缺失但 `inputs.coverage` 有映射时合成 `covered:<src>`。
    否则回退 txt `[--]` 行：
    - `[--]  pdf 已覆盖（已由 docx 校验）` → {"pdf": "covered:docx"}
    - `[--]  {disp} no baseline` → {fmt: "no baseline"}（disp 形如 epub 或 pdf→docx，取 → 左侧）
    - `[--]  {disp} gen not found: ...` → {fmt: "gen not found"}
    - 其他 `[--]` → {fmt: 原文}（fmt 取不到时键为 ""，调用方可忽略）

    有上游总结行（`[id] N format: …`）时优先用它：
    `NO_BASELINE`→"no baseline"、`NOGEN`→"gen not found"、
    `ERROR`等→小写原文、`COVERED`（无 ref）→"covered"。
    """
    rj = _read_verify_json(path)
    if rj is not None:
        out = {}
        for f, i in rj["fmts"].items():
            if i["verdict"] in ("undetermined", "error") and (i["reason"] or "").strip():
                out[f] = _json_pending_reason(i["reason"])
        _cov = rj.get("coverage") or {}
        if "pdf" in rj["fmts"] and "pdf" not in out and _cov.get("pdf"):
            out["pdf"] = f"covered:{_cov['pdf']}"
        return out
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

    `report.json` 存在时按 verdict：任一 `fail`→False；任一 `pass`→True；
    `undetermined/error` 不计入（否则 None）。
    回退 txt 总结行（`[id] N format: …`）时：含 FAIL verdict→False；
    ≥1 OK（含消解为通过的被覆盖项）→True；否则 None。
    """
    rj = _read_verify_json(path)
    if rj is not None:
        vals = [i["verdict"] for i in rj["fmts"].values()]
        if any(v == "fail" for v in vals):
            return False
        return True if any(v == "pass" for v in vals) else None
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
    `report.json` 存在时按 verdict：`pass→True、fail→False`；
    `undetermined/error` 不收录（与 txt 语义一致）。
    """
    rj = _read_verify_json(path)
    if rj is not None:
        out = {}
        for f, i in rj["fmts"].items():
            if i["verdict"] == "pass":
                out[f] = True
            elif i["verdict"] == "fail":
                out[f] = False
        return out
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
#: `*_verify_report.txt` / `*_校验报告.txt` / `（验证）/report.txt`，不参与导入扫描）
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


def verify_fingerprint_available(config) -> bool:
    """上游是否提供校验指纹（`pycbeta.verify.verify_fingerprint` 可调用）。"""
    try:
        _ensure_path(str(_x2p_root(config)))
        from pycbeta import verify as _v
        return callable(getattr(_v, "verify_fingerprint", None))
    except Exception:
        return False


def _effective_presets(config, preset_path):
    """生效配置 dict（上游公开 API；与 GUI run 形态同口径）。

    经临时 run 包装（仓库 run.json 槽＋config-json 指预设）解析；裸预设已由上游
    出厂深合并。返回 (eff_dict, wrap_path)；失败回 (None, wrap)（调用方判不可复用）。
    wrap 由调用方用后经 `remove_temp_preset` 删除。
    """
    _ensure_path(str(_x2p_root(config)))
    from pycbeta.theme import load_effective_presets
    wrap = write_run_wrapper(config, preset_path) if preset_path else None
    try:
        eff = load_effective_presets(str(wrap) if wrap else None)
        return (eff if isinstance(eff, dict) else None), wrap
    except Exception:
        return None, wrap


def verify_fingerprint(work: str, fmt: str, config, preset=None, xml_files=None,
                       juan=None):
    """单（work, fmt）校验指纹预判：返回当前输入的指纹，None 表示不可复用。

    - xml_files 为空时上游自行定位（旧行为）；传入则按该有序列表计算
      （跨边比对须与报告 `inputs.xml_files` 同序）；
    - juan 为卷范围 spec（或规范标签）；非空时经上游 `parse_juan_spec` 归一后
      入指纹（子集与整本、不同子集互异）；非法/上游不支持则返回 None（不复用）；
    - 以生效配置 dict（`presets=`）调用上游，与 GUI 报告同形；另传
      `config_path=包装路径` 贴近 GUI（注释相对路径等边缘求同）；
    - 阈值取 publish 全局（`verify_max_diff` 默认 0、`verify_diff_lines` 默认 5），
      钳制 0–50，与 `verify_work` 透传值一致。
    无副作用（不下载不写盘）。
    """
    try:
        _ensure_path(str(_x2p_root(config)))
        from pycbeta import verify as _v
        fn = getattr(_v, "verify_fingerprint", None)
        if fn is None:
            return None
    except Exception:
        return None
    segs = None
    if str(juan or "").strip():
        segs = juan_segments(config, juan)
        if segs is None:
            return None          # 卷范围非法/上游不支持：不可复用
    try:
        md = _cfg(config).get("verify_max_diff", 0)
        md = 0 if md is None else int(md)
    except (TypeError, ValueError):
        md = 0
    try:
        dl = _cfg(config).get("verify_diff_lines", 5)
        dl = 5 if dl is None else int(dl)
    except (TypeError, ValueError):
        dl = 5
    try:
        eff, wrap = _effective_presets(config, preset)
        if not isinstance(eff, dict):
            return None
        try:
            fp = fn(str(work), str(fmt),
                    xml_files=[str(p) for p in (xml_files or [])] or None,
                    config_path=str(wrap) if wrap else None, presets=eff,
                    max_diff=max(0, min(50, md)),
                    diff_lines=max(0, min(50, dl)),
                    juan=segs)
        finally:
            if wrap is not None:
                try:
                    remove_temp_preset(wrap)
                except Exception:
                    pass
    except Exception:
        return None
    return fp if isinstance(fp, str) and fp else None


def write_verify_summary(vdir, coll_name=None, works=None):
    """合并校验目录下全部单本报告为总报告（固定名覆盖写；无报告返回 None）。

    摘要行文与 `_do_import_verified` 一致（通过列格式、未通过带缺/多 numbers、
    未判定带原因），只读报告不搬产物；全文区按 stem 排序拼接各报告原文。
    works 非空时只汇总这些 work 的报告（跳过复用项的旧报告不计入，避免误读）。
    """
    import datetime as _dt
    vdir = Path(vdir)
    try:
        reports = sorted(verify_reports(vdir), key=lambda r: r[1])
    except Exception:
        return None
    if works is not None:
        _ws = {str(w) for w in (works or [])}
        reports = [(rp, stem) for rp, stem in reports
                   if any(_verify_stem_matches(stem, w) for w in _ws)]
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
