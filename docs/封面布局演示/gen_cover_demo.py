#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面布局演示文档生成器（cbeta-publish）。

把「合并时加封面封底、说明（以下所有内容）」总开关打开后，PDF 合并可能出现的
**所有页**，用真实渲染管线（`ebook_merger` 的 `_cover_pdf`/`_intro_pdf`/`_toc_pdf`/
`_editnote_pdf`/`_image_pdf`/`_blank_pdf`）生成，再叠加「页名 + 控制设置」标注、
封面元素编号图例与元素对照表，输出一份自解释的演示 PDF。

用法（在 publish 仓库根目录）：
    .venv\\Scripts\\python docs\\封面布局演示\\gen_cover_demo.py
    .venv\\Scripts\\python docs\\封面布局演示\\gen_cover_demo.py --paper a5
    .venv\\Scripts\\python docs\\封面布局演示\\gen_cover_demo.py --out 自定义路径.pdf

依赖：pymupdf、reportlab（publish 运行环境自带）。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cbeta_publish.books import ebook_merger as em  # noqa: E402

try:
    import pymupdf
except ImportError:  # PyMuPDF 旧版以 fitz 命名
    import fitz as pymupdf
    sys.modules["pymupdf"] = pymupdf

# ---------------------------------------------------------------- 演示参数
#: 纸张名 → (宽pt, 高pt)；演示默认 A4（与配置页签一致）
PAPERS = {
    "a4": (595.28, 841.89),
    "a5": (419.53, 595.28),
    "16k": (523.28, 737.01),
    "32k": (368.50, 523.28),
}

#: 示例丛书名（=「丛书名｜部类行」，与 main_window._cover_group_label 组装一致；
#: 部类行含「显示所有书名」titles=all 的展开，按 “ / ” 每段一行）
DEMO_COLLECTION = ("大乘五部典籍｜寶積部類 / 大乘五部 / "
                   "大寶積經 / 大般若波羅蜜多經 / 長阿含經")
DEMO_ORGANIZER = "依 CBETA XML 自製"
DEMO_TITLES = ["大寶積經", "大般若波羅蜜多經", "長阿含經"]
DEMO_PAGES = [15, 42, 96]

#: 演示用「全开」封面配置（键与真实 `cover` 段一致；未写的走出厂默认）
CFG = {
    "enabled": True,
    "mode": "print",
    "imprint": "CBETA 電子佛典自選叢書",
    "organizer_official": "CBETA 官方電子書",
    "organizer_xml": "依 CBETA XML 自製",
    "date_text": "{date}",
    "bulei": {"enabled": True, "titles": "all", "depth": 0,
              "layout": "lines", "sep": "·", "show_num": True},
    "images": {"buddha": {"enabled": True, "file": ""},
               "weituo": {"enabled": True, "file": ""}},
    "styles": {
        "background": {"color": [250, 245, 230]},
        "intro_background": {"color": [244, 238, 222]},
        "toc_background": {"color": [250, 248, 240]},
    },
    "intro": {
        "enabled": True, "title": "说明", "note": "依 CBETA XML 自制",
        "summary": ["本丛书共收录 3 部", "三藏分布：经 3"],
        "sections": [
            ("01 寶積部類（2 部）", ["T0310 大寶積經", "T0220 大般若波羅蜜多經"]),
            ("02 其他部類（1 部）", ["T0001 長阿含經"]),
        ],
    },
}

#: 编辑说明页（已解析 dict，供 `_editnote_pdf` 直接用；等价于一份说明 TXT）
DEMO_EDITNOTE = {
    "title": "編者序",
    "lines": [
        ("h1", "left", "凡例"),
        ("h2", "left", "一、收錄範圍"),
        ("body", "left", "　　本叢書依 CBETA XML 自製，收錄示例經書三部。"),
        ("gap", "left", ""),
        ("b", "left", "這一行整行加粗。"),
        ("center", "center", "這一行居中。"),
        ("right", "right", "這一行右對齊。"),
    ],
}

#: 封面页元素（编号、说明名）——供图例与标注用；y 位置由 _cover_markers 计算
COVER_ELEMENT_NAMES = [
    "左上角系列名（cover.imprint）",
    "封面标题（丛书名｜册名）",
    "封面部类行（cover.bulei）",
    "书籍版本/来源（cover.organizer_*）",
    "日期/署名（cover.date_text）",
    "封面背景色（cover.styles.background）",
]

#: 元素对照表：(页, 元素, 设置名（GUI）, 配置键, 样式来源)
ELEMENT_ROWS = [
    ("封面", "左上角系列名/落款", "左上角系列名", "cover.imprint",
     "字体 styles.cbeta.font；色 styles.cbeta.color；字号 sizes.cbeta_a4 / ratio cbeta"),
    ("封面", "封面标题（丛书名｜册名）", "封面标题", "合并名（丛书名｜部类行）",
     "字体 styles.title.font；ratio title；色 title；Y positions.title_y_ratio（缺省 0.25）"),
    ("封面", "封面部类行", "封面部类行 / 显示部类·书名 / 部类行细节", "cover.bulei.*",
     "字体 styles.toc_item.font；色 toc_item；Y positions.group_y_ratio（缺省 0.30）"),
    ("封面", "书籍版本/来源", "书籍版本/来源（官方 / 自制）",
     "cover.organizer_official / cover.organizer_xml",
     "字体 styles.date.font；色 organizer；Y positions.organizer_y_ratio（缺省 0.84）"),
    ("封面", "日期/署名", "日期/署名", "cover.date_text（{date}=今天）",
     "字体 styles.date.font；色 date；Y positions.date_y_ratio（缺省 0.90）"),
    ("封面", "背景色", "封面背景色", "cover.styles.background.color", "整页填充"),
    ("封面图页", "封面图", "封面图", "cover.images.buddha",
     "assets/images/B01.jpg（回退 1.*，后缀不限）；图占页 80% 居中"),
    ("编辑说明页", "标题/分级标题/正文/对齐/分页",
     "加编辑说明页 / 加丛书说明页", "cover.edit_note / 丛书 edit_note",
     "字体 styles.editnote_title.font / styles.editnote_body.font；字号 sizes.editnote_body"),
    ("说明页", "说明页标题", "说明页标题", "cover.intro.title",
     "字体 styles.toc_title.font；色 toc_title"),
    ("说明页", "自制书说明", "自制书说明", "cover.intro.note",
     "字体 styles.toc_item.font；仅来源=自制时显示"),
    ("说明页", "简介行（本丛书…/三藏分布）", "（自动从书单推导）", "cover.intro.summary",
     "字体 styles.intro_summary.font（默认仿宋）；色 toc_item"),
    ("说明页", "部类统计 + 完整清单", "插入说明页（部类统计 + 完整清单）", "cover.intro.sections",
     "字体 styles.toc_item.font；部类段每段一行（按 “ / ” 拆）"),
    ("说明页", "背景色", "说明页背景色", "cover.styles.intro_background.color",
     "缺席＝跟随封面背景色"),
    ("目录页", "目录标题（“目录”）", "（自动）", "—", "字体 styles.toc_title.font；色 toc_title"),
    ("目录页", "目录条目（含序号）", "（自动）", "—",
     "字体 styles.toc_item.font；色 toc_item；同行微右移模拟加粗"),
    ("目录页", "页码（右对齐）", "（自动）", "—", "字体 styles.toc_page.font；色 toc_page"),
    ("目录页", "背景色", "目录页背景色", "cover.styles.toc_background.color",
     "缺席＝跟随封面背景色"),
    ("目录页", "标题/条目起始高度", "（自动）",
     "positions.toc_y_ratio / positions.toc_item_y_ratio",
     "缺省 0.11 / 0.20"),
    ("正文", "各经书正文", "—", "—", "逐部；打印模式每部补偶页"),
    ("封底图页", "封底图", "封底图", "cover.images.weituo",
     "assets/images/B02.jpg（回退 2.*，后缀不限）"),
    ("封底", "空白封底", "—", "cover.mode=print", "打印模式：无图也保留一张空白封底"),
    ("空白页", "自动补白", "—", "cover.mode=print",
     "封面/封面图/编辑说明/说明/目录后按需补白（保证奇数页起）"),
]


# ---------------------------------------------------------------- 工具函数
def _make_source_pdf(path: Path, w: float, h: float) -> Path:
    """造一张目标纸张空白页，作各渲染函数的尺寸基准。"""
    doc = pymupdf.open()
    doc.new_page(width=w, height=h)
    doc.save(str(path))
    doc.close()
    return path


def _make_body_pdf(path: Path, w: float, h: float) -> Path:
    """正文示意页（自造，仅作占位，非真实渲染）。"""
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    page.insert_textbox(
        pymupdf.Rect(40, h * 0.42, w - 40, h * 0.52),
        "正文（示意）\n各經書正文，依書單逐部；打印模式每部補偶頁。",
        fontname="china-s", fontsize=14, color=(0.25, 0.25, 0.25), align=1)
    doc.save(str(path))
    doc.close()
    return path


def _pdf_pages(path: Path) -> int:
    try:
        with pymupdf.open(str(path)) as d:
            return len(d)
    except Exception:
        return 0


def _sum_pages(paths) -> int:
    return sum(_pdf_pages(p) for p in paths)


def _ratio(cfg, name, default):
    st = (cfg.get("styles") or {}).get(name)
    if isinstance(st, dict) and "ratio" in st:
        try:
            return float(st["ratio"])
        except Exception:
            return default
    return (cfg.get("sizes") or {}).get("ratios", {}).get(name, default)


def _cover_markers(cfg, w, h, paper):
    """按 `_cover_pdf` 同源公式算各封面元素的 y（自底向上），返回 [(no, y, name)]。

    仅用出厂默认（未写 sizes/positions），演示默认样式；若默认值变动需重生成。
    """
    sizes = cfg.get("sizes", {}) or {}
    pos = cfg.get("positions", {}) or {}
    base = sizes.get(f"body_{paper}", {"a4": 12, "a5": 10, "16k": 11, "32k": 9}.get(paper, 12))
    margins = sizes.get("margins", {}) or {}
    m = margins.get(paper)

    def _mg(side):
        if isinstance(m, dict) and side in m:
            return float(m[side])
        if isinstance(m, (int, float)):
            return float(m)
        return 40.0

    top = _mg("top")
    is_a5 = paper in ("a5", "32k")
    # 与 `_cover_pdf` 同源：cbeta/title 字号优先 `sizes.cbeta_a4|a5`，
    # 否则按基准×ratio；未配置 sizes 时走旧逻辑缺省（cbeta=10、title=base×3）
    cbeta_sz = sizes.get("cbeta_a5" if is_a5 else "cbeta_a4",
                         base * _ratio(cfg, "cbeta", 1.0))
    if ("cbeta_a5" not in sizes and "ratios" not in sizes
            and "body_a5" not in sizes and "cbeta" not in (cfg.get("styles") or {})):
        cbeta_sz = sizes.get("cbeta_a5" if is_a5 else "cbeta_a4", 10)
    title_sz = sizes.get("title_a5" if is_a5 else "title_a4",
                         base * _ratio(cfg, "title", 3.0))
    if ("title_a5" not in sizes and "ratios" not in sizes
            and "body_a5" not in sizes):
        title_sz = base * 3.0
    y_title = h * (1 - pos.get("title_y_ratio", 0.25))
    y_spine = h * (1 - pos.get("group_y_ratio", 0.30))
    y_group = y_title - title_sz - 6 - (y_title - y_spine)
    return [
        (1, h - top - cbeta_sz, "左上角系列名"),
        (2, y_title, "封面标题"),
        (3, y_group, "封面部类行"),
        (4, h * (1 - pos.get("organizer_y_ratio", 0.84)), "书籍版本/来源"),
        (5, h * (1 - pos.get("date_y_ratio", 0.90)), "日期/署名"),
        (6, 28, "封面背景色"),   # 角标（x 由 _annotate_cover 放右下角）
    ]


def _band(page, title, settings):
    """在页顶空白边距画「页名 + 控制设置」标注条（灰字，两行内自动折行）。"""
    rect = pymupdf.Rect(40, 5, page.rect.width - 40, 38)
    txt = f"{title}   控制设置：{settings}"
    try:
        page.insert_textbox(rect, txt, fontname="china-s", fontsize=7.5,
                            color=(0.32, 0.32, 0.32))
    except Exception:
        pass


def _annotate_cover(page, cfg, w, h, paper):
    """封面页：元素编号标记（左边距/右下角）+ 中部空白区图例框。"""
    markers = _cover_markers(cfg, w, h, paper)
    for no, y_bottom, _name in markers:
        y = h - y_bottom
        x = w - 30 if no == 6 else 30
        try:
            page.draw_circle((x, y), 8, color=(0.85, 0.33, 0.10),
                             fill=(0.85, 0.33, 0.10), width=0.5)
            page.insert_text((x - 3.5, y + 3.2), str(no), fontname="china-s",
                             fontsize=8, color=(1, 1, 1))
        except Exception:
            pass
    # 图例框：放在部类行之下、版本/来源之上（不遮挡内容）
    item_sz = em._toc_text_style(cfg, w, h, paper)["item_sz"]
    y_group = markers[2][1]
    _group = str(DEMO_COLLECTION.split("｜")[-1])
    n_group = len([s for s in _group.split(" / ") if s.strip()])
    group_last_td = h - (y_group - (n_group - 1) * item_sz * 1.6)
    org_td = h - markers[3][1]
    top = group_last_td + 16
    bottom = max(top + 120, org_td - 24)
    box = pymupdf.Rect(70, top, w - 70, bottom)
    try:
        page.draw_rect(box, color=(0.80, 0.55, 0.35), width=0.8,
                       fill=(1, 0.99, 0.96), fill_opacity=0.9)
    except Exception:
        pass
    lines = ["封面元素图例（对应左侧编号）"]
    for i, name in enumerate(COVER_ELEMENT_NAMES, 1):
        lines.append(f"{i}. {name}")
    try:
        page.insert_textbox(box + (10, 8, -10, -8), "\n".join(lines),
                            fontname="china-s", fontsize=9,
                            color=(0.30, 0.22, 0.12), lineheight=1.5)
    except Exception:
        pass


# ---------------------------------------------------------------- 对照表页
def _table_pdf(path: Path, w: float, h: float, rows, font_name: str):
    """用 reportlab 画元素对照表（可多页）。"""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    title_st = ParagraphStyle("t", fontName=font_name, fontSize=15, leading=20,
                              textColor=colors.HexColor("#333333"))
    cell_st = ParagraphStyle("c", fontName=font_name, fontSize=8.2, leading=11,
                             wordWrap="CJK")
    head_st = ParagraphStyle("h", parent=cell_st, textColor=colors.white)
    doc = SimpleDocTemplate(str(path), pagesize=(w, h),
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="封面布局演示 · 元素对照表")
    head = ["页", "元素", "设置名（GUI）", "配置键", "样式来源"]
    data = [[Paragraph(x, head_st) for x in head]]
    for r in rows:
        data.append([Paragraph(str(x), cell_st) for x in r])
    tbl = Table(data, colWidths=[16 * mm, 40 * mm, 40 * mm, 46 * mm, 62 * mm],
                repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8a5a2b")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbb79a")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#faf6ef")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story = [Paragraph("封面元素对照表", title_st), Spacer(1, 4 * mm), tbl]
    doc.build(story)
    return path


def _front_pdf(path: Path, w: float, h: float, paper: str, font_name: str,
               order_lines):
    """前言页（说明 + 页序清单）。"""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    t_st = ParagraphStyle("t", fontName=font_name, fontSize=17, leading=22,
                          textColor=colors.HexColor("#8a5a2b"))
    h_st = ParagraphStyle("h", fontName=font_name, fontSize=11, leading=15,
                          textColor=colors.HexColor("#333333"))
    b_st = ParagraphStyle("b", fontName=font_name, fontSize=9, leading=14,
                          wordWrap="CJK", textColor=colors.HexColor("#333333"))
    doc = SimpleDocTemplate(str(path), pagesize=(w, h),
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="封面布局演示")
    story = [
        Paragraph("封面布局演示", t_st),
        Spacer(1, 3 * mm),
        Paragraph(
            "本演示把「合并时加封面封底、说明（以下所有内容）」总开关打开后，"
            "PDF 合并可能出现的<b>所有页</b>用真实渲染管线生成（纸张："
            f"{paper.upper()}），并标注每页的控制设置。"
            "每页顶部灰字即该页的设置；封面页左侧编号对应页内「封面元素图例」；"
            "文末附完整「封面元素对照表」。", b_st),
        Spacer(1, 4 * mm),
        Paragraph("页序（打印模式：自动补白；阅读模式：去空白页）", h_st),
        Spacer(1, 2 * mm),
    ]
    for i, ln in enumerate(order_lines, 1):
        story.append(Paragraph(f"{i}. {ln}", b_st))
    story += [
        Spacer(1, 4 * mm),
        Paragraph("说明", h_st),
        Spacer(1, 1 * mm),
        Paragraph(
            "· 总开关 <b>cover.enabled</b>；模式 <b>cover.mode</b>=print/reading。"
            "关闭总开关＝直接拼接原文件，仅生成书签，不插任何封面/封底/说明页。", b_st),
        Paragraph(
            "· 字体/颜色/字号在「封面/版式 → 字体」「基准字号」「边距」子页签，"
            "按纸张（a5/a4/16k/32k）分别设置；未配置走出厂默认。", b_st),
        Paragraph(
            "· 本 PDF 由 <b>gen_cover_demo.py</b> 生成，封面代码变动后重新运行即可。", b_st),
    ]
    doc.build(story)
    return path


# ---------------------------------------------------------------- 主流程
def build(out_path: Path, paper: str = "a4") -> Path:
    w, h = PAPERS.get(paper, PAPERS["a4"])
    tmp = Path(tempfile.mkdtemp(prefix="cover-demo-"))
    src = _make_source_pdf(tmp / "src.pdf", w, h)

    # 真实渲染各页
    cover = em._cover_pdf(src, DEMO_COLLECTION, tmp / "cover.pdf",
                          organizer=DEMO_ORGANIZER, config=CFG)
    blank = em._blank_pdf(src, tmp / "blank.pdf")
    buddha = em.resolve_cover_image(CFG["images"], "buddha")
    weituo = em.resolve_cover_image(CFG["images"], "weituo")
    buddha_pdf = em._image_pdf(src, buddha, tmp / "buddha.pdf") if buddha else None
    weituo_pdf = em._image_pdf(src, weituo, tmp / "weituo.pdf") if weituo else None
    edit_pdf = tmp / "edit.pdf"
    edit_pages = em._editnote_pdf(DEMO_EDITNOTE, src, edit_pdf, config=CFG)
    intro_pdf = tmp / "intro.pdf"
    intro_pages = em._intro_pdf(CFG["intro"], src, intro_pdf, config=CFG)
    toc_pdf = tmp / "toc.pdf"
    em._toc_pdf(DEMO_TITLES, src, toc_pdf, config=CFG,
                page_nums=DEMO_PAGES, toc_start_index=0)
    toc_pages = _pdf_pages(toc_pdf)
    body_pdf = _make_body_pdf(tmp / "body.pdf", w, h)

    # 打印模式拼装（复刻 _merge_pdfs_impl 的补白规则）
    pad = CFG.get("mode") == "print"
    seq = []  # [(页名, path, 控制设置)]
    seq.append(("封面页", cover,
                "cover.imprint / 封面标题(合并名) / cover.bulei / "
                "cover.organizer_official|organizer_xml / cover.date_text / "
                "cover.styles.background"))
    if pad:
        seq.append(("空白页（封面后）", blank, "cover.mode=print 自动补白"))
    if buddha_pdf:
        seq.append(("封面图页", buddha_pdf,
                    "cover.images.buddha（assets/images/B01.jpg，回退 1.*）"))
        if pad:
            seq.append(("空白页（封面图后）", blank, "cover.mode=print 自动补白"))
    seq.append(("编辑说明页", edit_pdf,
                "cover.edit_note（全局）+ 丛书 edit_note；TXT 排版，可多页"))
    if pad and edit_pages % 2 == 1:
        seq.append(("空白页（编辑说明后）", blank, "cover.mode=print 自动补白"))
    if pad and _sum_pages([s[1] for s in seq]) % 2 == 1:
        seq.append(("空白页（说明页前）", blank, "cover.mode=print 自动补白"))
    seq.append(("说明页", intro_pdf,
                "cover.intro.title / intro.note / intro.summary / intro.sections；"
                "背景 cover.styles.intro_background"))
    if pad and intro_pages % 2 == 1:
        seq.append(("空白页（说明页后）", blank, "cover.mode=print 自动补白"))
    seq.append(("目录页", toc_pdf,
                "标题「目录」；条目/页码字体 toc_item/toc_page；"
                "背景 cover.styles.toc_background"))
    if pad and toc_pages % 2 == 1:
        seq.append(("空白页（目录后）", blank, "cover.mode=print 自动补白"))
    seq.append(("正文（示意）", body_pdf, "各经书正文，逐部；打印模式每部补偶页"))
    if pad and _pdf_pages(body_pdf) % 2 == 1:
        seq.append(("空白页（正文补偶页）", blank,
                    "cover.mode=print（正文每部补偶页）"))
    if weituo_pdf:
        seq.append(("封底图页", weituo_pdf,
                    "cover.images.weituo（assets/images/B02.jpg，回退 2.*）"))
    if pad:
        seq.append(("封底（空白）", blank, "cover.mode=print；无图也保留"))

    # 拼装真实页
    doc = pymupdf.open()
    page_meta = []  # [(页名, 控制设置)]
    for name, path, settings in seq:
        start = len(doc)
        doc.insert_pdf(pymupdf.open(str(path)))
        for _ in range(len(doc) - start):
            page_meta.append((name, settings))

    # 标注（每页顶部条；封面页加编号+图例）
    for i, (name, settings) in enumerate(page_meta):
        page = doc[i]
        _band(page, name, settings)
        if name == "封面页":
            _annotate_cover(page, CFG, w, h, paper)

    # 字体（对照表/前言用 reportlab）
    font_name = em._register_font("CoverDemoCJK", "C:/Windows/Fonts/simhei.ttf")

    # 前言页（最前）
    order_lines = []
    _seen = set()
    for name, _s in page_meta:
        order_lines.append(name)
    front_pdf = _front_pdf(tmp / "front.pdf", w, h, paper, font_name, order_lines)

    # 对照表页（最后）
    table_pdf = _table_pdf(tmp / "table.pdf", w, h, ELEMENT_ROWS, font_name)

    out_doc = pymupdf.open()
    out_doc.insert_pdf(pymupdf.open(str(front_pdf)))
    out_doc.insert_pdf(doc)
    out_doc.insert_pdf(pymupdf.open(str(table_pdf)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_doc.save(str(out_path), garbage=3, deflate=True)
    out_doc.close()
    doc.close()
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成封面布局演示 PDF")
    ap.add_argument("--out", default=str(Path(__file__).with_name("封面布局演示.pdf")),
                    help="输出 PDF 路径")
    ap.add_argument("--paper", default="a4", choices=sorted(PAPERS),
                    help="纸张（默认 a4）")
    args = ap.parse_args(argv)
    out = build(Path(args.out), paper=args.paper)
    print(f"已生成：{out}（{_pdf_pages(out)} 页，纸张 {args.paper.upper()}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
