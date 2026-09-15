# -*- coding: utf-8 -*-
"""链路 B 桥接：CBETA XML → 调用 E:/dev/cbeta/xml2pdf (pycbeta) → pdf/epub。
仅调度，不含转化逻辑（契约见 docs/链路B-设计契约.md）。"""
import subprocess
import sys
from pathlib import Path


def _cfg(config):
    return (config or {}).get("xml2pdf", {}) or {}


def find_xml(work_id: str, config: dict, mapping=None) -> Path | None:
    """定位 XML：
    1) 优先用 sutra_mapping（mapping.resolve）得到 file 与册目录
    2) 回退正则（T01n0001 / T0001）
    在 cbeta_xml(book_dir) 与 local_xml_root 两处查找；未找到 None。"""
    import re
    book=vol=None
    fname=None
    if mapping is not None:
        info=mapping.resolve(work_id)
        if info:
            book=info.get("book"); vol=info.get("vol"); fname=info.get("file")
    if not (book and vol and fname):
        m=re.match(r"^([A-Za-z]+)(\d+)n(\d+)([A-Za-z]?)$", work_id)
        if m:
            book, vol, no, sub = m.group(1), m.group(2), m.group(3), m.group(4) or ""
            fname=f"{book}{vol}n{no}{sub}.xml"
        else:
            m=re.match(r"^([A-Za-z]+)(\d{2})(\d{2})([A-Za-z]?)$", work_id)
            if m:
                book, vol, no, sub = m.group(1), m.group(2), m.group(3), m.group(4) or ""
                fname=f"{book}{vol}n{no}{sub}.xml"
    roots=[]
    for k in ("book_dir", "local_xml_root"):
        v=(config or {}).get(k)
        if v:
            roots.append(Path(v))
    for root in roots:
        if not root.exists():
            continue
        if book and vol and fname:
            d=root/book/f"{book}{vol}"
            stem=fname[:-4] if fname.endswith(".xml") else fname
            base=re.sub(r"_\d+$", "", stem)   # T01n0001_001 -> T01n0001
            for cand in (d/fname, d/f"{base}.xml"):
                if cand.exists():
                    return cand
            for cand in sorted(d.glob(f"{base}*.xml")):
                return cand
        # 回退：按 work_id 直接匹配文件名前缀
        for cand in sorted(root.rglob(f"{work_id}*.xml")):
            return cand
    return None


def convert(work_id: str, xml_path: Path, out_dir: Path, config: dict,
            fmt: str = "pdf", opts: dict = None) -> Path | None:
    """调用 `python -m pycbeta` 转换单个 XML。返回产物路径或 None。
    opts 覆盖 config.xml2pdf：{page,font_lang,engine,vertical}"""
    o = dict(_cfg(config))
    if opts:
        o.update({k: v for k, v in opts.items() if v is not None})
    x2p = Path(o.get("path") or "E:/dev/cbeta/xml2pdf")
    if not x2p.exists():
        print("xml2pdf path not found", x2p)
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{work_id}.{fmt}"
    cmd = [sys.executable, "-m", "pycbeta", "-i", str(xml_path), "-f", fmt,
           "-o", str(out_file)]
    if o.get("page"):
        cmd += ["--page", str(o["page"])]
    if o.get("font_lang"):
        cmd += ["--font-lang", str(o["font_lang"])]
    if o.get("engine") and fmt == "pdf":
        cmd += ["--engine", str(o["engine"])]
    if o.get("vertical") and fmt == "pdf":
        cmd += ["--vertical"]
    try:
        r = subprocess.run(cmd, cwd=str(x2p), capture_output=True, text=True, timeout=1800)
        if r.returncode != 0:
            print("pycbeta fail", r.returncode, (r.stderr or "")[-500:])
            return None
    except Exception as e:
        print("pycbeta run fail", e)
        return None
    return out_file if out_file.exists() else None


def batch_convert(work_ids: list, out_dir: Path, config: dict, fmt: str = "pdf",
                  opts: dict = None, progress=None, mapping=None) -> dict:
    """批量转换；返回 {work_id: path|None}。缺失 XML 记录为 None。"""
    out_dir = Path(out_dir)
    result = {}
    for i, w in enumerate(work_ids, 1):
        if progress:
            progress(f"({i}/{len(work_ids)}) {w}")
        xml = find_xml(w, config, mapping=mapping)
        if not xml:
            result[w] = None
            continue
        result[w] = convert(w, xml, out_dir, config, fmt=fmt, opts=opts)
    return result
