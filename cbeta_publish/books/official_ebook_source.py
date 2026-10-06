"""官方电子书下载（复用 cbeta-fetch 共享层：URL 模板 / id 规范化 / 原子下载 / zip 解压）。

- URL、id 大小写规范化、下载与解压均由 `cbeta_publish/_vendor/cbeta_fetch` 提供（勿改）。
- 目录布局（publish 自有）：`{dest_dir}/{fmt}/{work}.{fmt}`；
  目录型（docx/odt/html/txt/txt_notes，端点为 zip）解压到 `{dest_dir}/{fmt}/{work}/`。
  与自制书目录同构（`{root}/{fmt}/…`），根分开防复用串源。
- 官方电子书本地库（`official_library`）：本地优先、缺失回退下载。
  只读本地库、拷贝进缓存；冻结快照语义（命中不做更新检查）。
"""
import os
import re
import shutil
from email.utils import parsedate_to_datetime
from pathlib import Path

from cbeta_publish._vendor import cbeta_fetch as cf
from cbeta_publish.catalog.work_id import canonical_work, catalog_path

_ZIP_FORMATS = {"docx", "odt", "html", "txt_notes", "txt"}

#: 打包（ZIP/导出）可选格式：官方源 7 种全列，自制源仅 pdf/epub（xml2pdf 只产这两种）。
PACK_FORMATS = ("pdf", "epub", "html", "docx", "odt", "txt", "txt_notes")

#: vendor 共享层之外的官方端点（vendor 标勿改，publish 自有扩展放这里）：
#: 纯 txt（一部一档，含 `{id}-toc.txt` 目次），见 CBData「下載純文字格式佛典」。
_EXTRA_DOWNLOADS = {
    "txt": "https://cbdata.dila.edu.tw/stable/download/text/{id}.txt.zip",
}


def canonical(work: str) -> str:
    """按 catalog 原始大小写规范化（`TXA001 → TXa001`、`T0128A → T0128a`）。"""
    return canonical_work(work)


def canon_of(work: str) -> str:
    """藏经代号（大写）：`T0001 → T`、`TXa001 → TX`、`JB005 → J`。"""
    try:
        return cf.parse_work_id(canonical(work))[0]
    except ValueError:
        return (work or "?")[0].upper()


def ebook_url(fmt: str, canon: str, work: str) -> str:
    tmpl = cf.DEFAULT_DOWNLOADS.get(fmt) or _EXTRA_DOWNLOADS.get(fmt)
    if not tmpl:
        raise ValueError(f"unknown ebook format: {fmt}")
    return tmpl.format(canon=canon, id=work)


def official_books_dir(config) -> Path:
    """官方电子书缓存根（`cbeta_ebooks_dir` 优先，兼容 `official_ebooks_dir`；与旧回退链同序）。"""
    cfg = (config or {})
    return Path(cfg.get("cbeta_ebooks_dir") or cfg.get("official_ebooks_dir")
                or "./cbeta_ebooks")


def dest_path(work: str, fmt: str, dest_dir) -> Path:
    """单文件格式落盘路径（布局 publish 自有）。"""
    return Path(dest_dir) / fmt / f"{canonical(work)}.{fmt}"


def zip_dest_dir(work: str, fmt: str, dest_dir) -> Path:
    """zip 型格式解压目录。"""
    return Path(dest_dir) / fmt / canonical(work)


def local_path(work: str, fmt: str, dest_dir) -> Path:
    return zip_dest_dir(work, fmt, dest_dir) if fmt in _ZIP_FORMATS else dest_path(work, fmt, dest_dir)


def local_size_kb(path) -> int:
    """本地已下载文件/目录的大小（KB）；失败返回 0。"""
    try:
        p = Path(path)
        if p.is_file():
            return p.stat().st_size // 1024
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) // 1024
    except OSError:
        return 0


def library_version(config=None) -> str:
    """本地官方库版本名（`official_library.root` 目录名，如 `2026r2`）；空→""。

    用于官方书过期判据：换库版本（目录名变化）时视为全部过期。
    """
    try:
        root = ((config or {}).get("official_library") or {}).get("root") or ""
    except Exception:
        root = ""
    root = str(root).strip().rstrip("/\\")
    if not root:
        return ""
    try:
        return Path(root).name
    except Exception:
        return ""


def product_mtime(path) -> float:
    """产物时间戳：文件→mtime；目录→递归文件最大 mtime；空目录/缺失→0.0。"""
    try:
        p = Path(path)
        if p.is_file():
            return p.stat().st_mtime
        if p.is_dir():
            latest = 0.0
            for f in p.rglob("*"):
                try:
                    if f.is_file():
                        m = f.stat().st_mtime
                        if m > latest:
                            latest = m
                except OSError:
                    continue
            return latest
    except OSError:
        pass
    return 0.0


def remote_info(work: str, fmt: str) -> dict | None:
    """HEAD 探针（复用共享层），返回 {url,size,mtime,etag}；失败/zip 型返回 None。"""
    if fmt in _ZIP_FORMATS:
        return None   # 端点为 zip，本地是目录，大小不可比 → 总是下载
    work = canonical(work)
    url = ebook_url(fmt, canon_of(work), work)
    r = cf.probe_info(url)
    if r.get("status") != "changed":
        return None
    mtime = None
    lm = r.get("last_modified")
    if lm:
        try:
            mtime = parsedate_to_datetime(lm).timestamp()
        except Exception:
            mtime = None
    return {"url": url, "size": r.get("size"), "mtime": mtime, "etag": r.get("etag")}


def is_unchanged(info: dict | None, dest) -> bool:
    # 本地存在且远端大小一致、远端不比本地新 -> 视为未更新，可跳过
    if info is None:
        return False
    try:
        st = Path(dest).stat()
    except OSError:
        return False
    if not Path(dest).is_file():
        return False
    if info.get("size") is not None and info["size"] != st.st_size:
        return False
    if info.get("size") is None and info.get("mtime") is None:
        return False   # 远端无任何可比元信息：无法判断，下载
    if info.get("mtime") is not None and info["mtime"] > st.st_mtime + 1:
        return False
    return True


def download_ebook(work: str, fmt: str, dest_dir, config=None, *, force=False) -> Path | None:
    work = canonical(work)
    got = copy_from_library(work, fmt, dest_dir, config, force=force)
    if got is not None:
        return got
    url = ebook_url(fmt, canon_of(work), work)
    if _head_absent_404(url):
        raise RemoteNotFound(url)
    if fmt in _ZIP_FORMATS:
        out_dir = zip_dest_dir(work, fmt, dest_dir)
        return out_dir if cf.download(url, str(out_dir), unzip=True) else None
    dest = dest_path(work, fmt, dest_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest if cf.download(url, str(dest)) else None


#: HEAD 探针超时（秒）：只用于“确定不存在”快判；超时/异常一律视为不定，照常下载
_HEAD_PROBE_TIMEOUT = 10
#: 确定不存在的 HTTP 状态：不再重试下载，直接失败
_GONE_STATUS = (404, 410)


class RemoteNotFound(Exception):
    """远端确定不存在（HEAD 探针 404/410）：调用方记 `不存在`，不再重试下载。"""


def _head_absent_404(url, timeout=_HEAD_PROBE_TIMEOUT) -> bool:
    """远端是否确定不存在：HEAD 返回 404/410 为 True；2xx 为 False；
    超时/405/其它异常一律 False（不定，照常下载，不断生路）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": cf.USER_AGENT},
                                     method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=cf._ctx()) as r:
            return False
    except urllib.error.HTTPError as e:
        return e.code in _GONE_STATUS
    except Exception:
        return False
    return False


# ---------- 官方电子书本地库（只读；本地优先、缺失回退下载） ----------

#: 格式 → 子目录名关键字（小写包含即候选；排序取首个＋记日志，多版本并存不猜测）
#: 注意 "txt" 不是 "text" 的子串：纯文本目录（如 cbeta-text）靠 "text" 命中，
#: 再用 _LIB_EXCLUDE 把 text-with-notes 排除在 txt 之外（反之天然不命中）。
_LIB_KEYWORDS = {
    "epub": ("epub",),
    "docx": ("docx",),
    "txt_notes": ("text-with", "notes"),
    "txt": ("txt", "text"),
    "pdf": ("pdf",),
    "html": ("html", "htm"),
    "odt": ("odt",),
}
#: 格式 → 候选中必须排除的子串（防跨格式误认；纯 txt 绝不能拿带注版冒充）
_LIB_EXCLUDE = {
    "txt": ("text-with", "with-notes"),
}
#: 格式 → 本地文件扩展名
_LIB_EXT = {"epub": "epub", "docx": "docx", "txt_notes": "txt", "txt": "txt",
            "pdf": "pdf", "html": "html", "odt": "odt"}
#: work 文件名：单文件 `{id}.ext` / 按卷 `{id}_NNN.ext`
_LIB_SINGLE_RE = re.compile(r"^[A-Za-z]+\d+[A-Za-z]?\.[A-Za-z0-9]+$")
_LIB_JUAN_RE = re.compile(r"^[A-Za-z]+\d+[A-Za-z]?_\d+\.[A-Za-z0-9]+$")

#: 进程内映射缓存：{(root, overrides_key): ({fmt: entry}, [notes])}
_LIB_MAP_CACHE = {}

#: 校验基线目标子目录：本地库格式 → 工作根子目录（与上游 auto_fetch 落点一致)
_SEED_DIRS = {"docx": "docx", "txt_notes": "txt", "epub": "epub"}


def seed_baselines_from_library(work, kinds, wdir, config) -> dict:
    """把本地库基线拷进工作根（只补缺失、不覆盖已有）：`{wdir}/docx|txt/…`、`epub/…`。

    kinds 取上游口径（如 docx→["docx","html"]、epub→["epub"]；html 本地无基线）。
    wdir 不存在则跳过（上游 auto_fetch 兜底）。只读源、只写工作根。
    返回 {kind: [dest]}（已存在也计入）。
    """
    out = {}
    try:
        wdir_p = Path(wdir)
        if not wdir_p.is_dir():
            return out
    except Exception:
        return out
    root, ov = library_config(config)
    if not root:
        return out
    mapping, _notes = resolve_library_map(root, ov)
    try:
        w = canonical(work)
    except Exception:
        w = work
    for kind in kinds or []:
        libfmt = {"docx": "docx", "txt_notes": "txt_notes", "epub": "epub",
                  "md": "txt_notes", "txt": "txt_notes", "pdf": "docx"}.get(kind)
        if libfmt is None or libfmt not in _SEED_DIRS:
            continue
        files = find_in_library(w, libfmt, config, root=root, libmap=mapping)
        if not files:
            continue
        destdir = wdir_p / _SEED_DIRS[libfmt]
        try:
            destdir.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        got = []
        for f in files:
            dst = destdir / f.name
            try:
                if dst.is_file() and dst.stat().st_size > 0:
                    got.append(dst)
                    continue
            except OSError:
                pass
            try:
                shutil.copy2(str(f), str(dst))
                got.append(dst)
            except OSError:
                continue
        if got:
            out[kind] = got
    return out


def library_config(config) -> tuple:
    """`official_library` 配置 → (root, overrides)。

    允许直接写根路径字符串；`{"root": ..., "overrides": {fmt: 子目录名}}`。
    """
    lib = (config or {}).get("official_library")
    if isinstance(lib, str):
        return lib.strip(), {}
    if not isinstance(lib, dict):
        return "", {}
    root = str(lib.get("root") or "").strip()
    ov = lib.get("overrides") or {}
    return root, (dict(ov) if isinstance(ov, dict) else {})


def refresh_library_map(root=None):
    """清本地库映射缓存（设置保存/点刷新后调）。root 缺省清全部。"""
    if root is None:
        _LIB_MAP_CACHE.clear()
        return
    try:
        key = os.path.normcase(os.path.abspath(str(root)))
    except Exception:
        _LIB_MAP_CACHE.clear()
        return
    for k in [k for k in _LIB_MAP_CACHE if k[0] == key]:
        _LIB_MAP_CACHE.pop(k, None)


def _lib_candidate_dirs(root: Path, keywords, exclude=()) -> list:
    try:
        entries = sorted((p for p in root.iterdir() if p.is_dir()),
                         key=lambda p: p.name.lower())
    except OSError:
        return []
    kws = [k.lower() for k in keywords]
    exs = [e.lower() for e in exclude]
    return [p for p in entries
            if any(k in p.name.lower() for k in kws)
            and not any(e in p.name.lower() for e in exs)]


def _lib_classify(files, ext):
    """一批文件名按形态分类：先判按卷（`{id}_NNN.ext`），再判单文件（`{id}.ext`）。"""
    single = False
    for f in files:
        if f.suffix.lower() != f".{ext}":
            continue
        if _LIB_JUAN_RE.match(f.name):
            return "juan"   # 按卷优先（信息更全，与校验/解压布局一致）
        if _LIB_SINGLE_RE.match(f.name):
            single = True
    return "single" if single else None


def _lib_probe_pattern(d: Path, ext: str):
    """探测候选目录的文件形态：{"juan"} / {"single"} / None（只看少量样本）。

    兼容两层布局：`{canon}/{work}.ext`（单文件）与 `{canon}/{work}/{work}_NNN.ext`（按卷）。
    """
    try:
        subs = sorted((p for p in d.iterdir() if p.is_dir()),
                      key=lambda p: p.name.lower())[:12]
    except OSError:
        return None
    seen_single = False
    for sub in subs:
        try:
            entries = sorted(sub.iterdir(), key=lambda p: p.name.lower())[:60]
        except OSError:
            continue
        r = _lib_classify([p for p in entries if p.is_file()], ext)
        if r == "juan":
            return "juan"
        if r == "single":
            seen_single = True
        # 再下一层（按卷布局的 work 目录）
        for wdir in [p for p in entries if p.is_dir()][:6]:
            try:
                wfiles = sorted((p for p in wdir.iterdir() if p.is_file()),
                                key=lambda p: p.name.lower())[:30]
            except OSError:
                continue
            r2 = _lib_classify(wfiles, ext)
            if r2 == "juan":
                return "juan"
            if r2 == "single":
                seen_single = True
    return "single" if seen_single else None


def resolve_library_map(root, overrides=None) -> tuple:
    """解析本地库映射 → ({fmt: {"dir": Path, "pattern": "single"|"juan"}}, [说明行])。

    子目录：overrides[fmt] 显式优先；否则关键字自动探测（排序取首个）。
    形态：实探文件样本决定。结果按 root＋overrides 缓存。
    """
    root_p = Path(root or "")
    try:
        root_key = os.path.normcase(os.path.abspath(str(root_p)))
    except Exception:
        return {}, [f"{root_p}：路径无效"]
    ov = {str(k): str(v) for k, v in (overrides or {}).items() if v}
    cache_key = (root_key, tuple(sorted(ov.items())))
    hit = _LIB_MAP_CACHE.get(cache_key)
    if hit is not None:
        return hit
    mapping, notes = {}, []
    if not root_p.is_dir():
        notes.append(f"{root_p}：目录不存在，本地库关闭")
        _LIB_MAP_CACHE[cache_key] = (mapping, notes)
        return mapping, notes
    for fmt in ("pdf", "epub", "html", "docx", "odt", "txt", "txt_notes"):
        ext = _LIB_EXT[fmt]
        d = None
        how = ""
        if ov.get(fmt):
            cand = root_p / ov[fmt]
            if cand.is_dir():
                d, how = cand, "指定"
            else:
                notes.append(f"{fmt}：指定的 {ov[fmt]} 不存在")
                continue
        else:
            cands = _lib_candidate_dirs(root_p, _LIB_KEYWORDS[fmt],
                                        _LIB_EXCLUDE.get(fmt, ()))
            if cands:
                d, how = cands[0], "自动"
                if len(cands) > 1:
                    notes.append(f"{fmt}：候选多个，用首个 {cands[0].name}（可在覆盖中指定）")
        if d is None:
            notes.append(f"{fmt}：未找到对应子目录")
            continue
        pattern = _lib_probe_pattern(d, ext)
        if pattern is None:
            notes.append(f"{fmt}：{d.name} 下无可用文件形态")
            continue
        mapping[fmt] = {"dir": d, "pattern": pattern}
        notes.append(f"{fmt}：{d.name}（{how}，{'单文件' if pattern == 'single' else '按卷'}）")
    _LIB_MAP_CACHE[cache_key] = (mapping, notes)
    return mapping, notes


def _work_variants(work: str) -> list:
    try:
        c = canonical(work)
    except Exception:
        c = work
    out = []
    for v in (c, (c or "").upper(), work, (work or "").upper()):
        if v and v not in out:
            out.append(v)
    return out


def _lib_canon_dir(base: Path, canon: str):
    d = base / canon
    try:
        if d.is_dir():
            return d
    except OSError:
        return None
    low = (canon or "").lower()
    try:
        for p in base.iterdir():
            if p.is_dir() and p.name.lower() == low:
                return p
    except OSError:
        pass
    return None


def find_in_library(work: str, fmt: str, config=None, *, root=None, libmap=None) -> list:
    """本地库查找 → 非空文件 Path 列表（单文件 1 个，按卷多个）；无则 []。

    只读本地库。`{fmt: entry}` 可由 `resolve_library_map` 预解析传入。
    """
    if root is None:
        root, ov = library_config(config)
    else:
        ov = {}
    if not root:
        return []
    try:
        if not Path(root).is_dir():
            return []
    except Exception:
        return []
    mapping = libmap
    if mapping is None:
        mapping, _notes = resolve_library_map(root, ov)
    entry = mapping.get(fmt)
    if entry is None:
        return []
    ext = _LIB_EXT.get(fmt, fmt)
    try:
        canon = canon_of(work)
    except Exception:
        canon = (work or "?")[0].upper()
    cdir = _lib_canon_dir(entry["dir"], canon)
    if cdir is None:
        return []
    out = []
    if entry["pattern"] == "single":
        for v in _work_variants(work):
            f = cdir / f"{v}.{ext}"
            try:
                if f.is_file() and f.stat().st_size > 0:
                    return [f]
            except OSError:
                continue
        # 大小写回退：目录内不区分大小写匹配
        low = f"{work}".lower() + f".{ext}"
        try:
            for p in cdir.iterdir():
                if p.is_file() and p.name.lower() == low:
                    try:
                        if p.stat().st_size > 0:
                            return [p]
                    except OSError:
                        continue
        except OSError:
            pass
        return []
    for v in _work_variants(work):
        wdir = cdir / v
        try:
            ok = wdir.is_dir()
        except OSError:
            continue
        if not ok:
            continue
        try:
            files = sorted((p for p in wdir.iterdir()
                            if p.is_file() and _LIB_JUAN_RE.match(p.name)
                            and p.suffix.lower() == f".{ext}"
                            and p.name.startswith(v + "_")),
                           key=lambda p: p.name.lower())
        except OSError:
            continue
        files = [p for p in files if _nonempty(p)]
        if files:
            return files
    return out


def _nonempty(p: Path) -> bool:
    try:
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def copy_from_library(work: str, fmt: str, dest_dir, config=None, *, root=None,
                      libmap=None, force=False):
    """从本地库拷贝进缓存 → 目标 Path（单文件/目录）；无则 None。

    只读源、只写缓存。目标已存在且同大小则跳过（幂等，不 churn）；
    force=True 时忽略同大小跳过、强制覆盖（换库但同大小文件也能更新）。
    """
    files = find_in_library(work, fmt, config, root=root, libmap=libmap)
    if not files:
        return None
    try:
        w = canonical(work)
    except Exception:
        w = work
    try:
        if len(files) == 1 and _LIB_SINGLE_RE.match(files[0].name):
            dest = dest_path(w, fmt, dest_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists() and not force:
                try:
                    if dest.is_file() and dest.stat().st_size == files[0].stat().st_size:
                        return dest
                except OSError:
                    pass
            shutil.copy2(str(files[0]), str(dest))
            return dest if dest.exists() else None
        out = zip_dest_dir(w, fmt, dest_dir)
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            dst = out / f.name
            if not force:
                try:
                    if dst.is_file() and dst.stat().st_size == f.stat().st_size:
                        continue
                except OSError:
                    pass
            shutil.copy2(str(f), str(dst))
        return out if any(p.is_file() for p in out.iterdir()) else None
    except OSError:
        return None
