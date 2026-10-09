"""单一格式合并，封面中文支持，分册"""
from pathlib import Path
import datetime
import re

from cbeta_publish.paths import app_root

# 繁体字形覆盖率检查样本（CBETA 内容以繁体为主）
_CJK_SAMPLE = "緣類毘經藏録（）說明本會嚴"
# 候补全字库（配置字体缺字形时替换；宋体放最后）
_FALLBACK_FONTS = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simsun.ttc",
]
_WARNED_FONTS = set()
# 已注册字体缓存：name -> [解析后路径, 实际生效的注册名]。
# reportlab 对同名重注册静默忽略（旧字体一直沿用），故换路径必须换别名，
# 否则改字体设置后必须重启才生效；命中缓存时也不再重复解析大字库。
_REGISTERED = {}
_REG_SEQ = [0]


def _fresh_alias(name):
    _REG_SEQ[0] += 1
    return f"{name}__r{_REG_SEQ[0]}"

# 拉丁扩展回退（编辑说明 PDF 混排）：黑体/宋体经 reportlab 子集化后，
# 个别拉丁扩展字符（如 ś U+015B）映射损坏，画成空白还占幅（视觉像空格变宽）；
# 梵文转写扩展区（U+1E00–U+1EFF，中如 ṛṇṭ）则在中文字库普遍缺字。
# 下列西文字库实测可正确回读（drawString→提取一致），按序取首个存在者。
_LATN_FALLBACK_FILES = [
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/NotoSans-Regular.ttf",
]
# 无条件走回退的区段（主字体即便 cmap 声称覆盖也可能画坏，如黑体的 ś）
_LATN_ALWAYS_RANGES = ((0x0100, 0x024F), (0x1E00, 0x1EFF))
_LATN_FONT = [None]
_GLYPH_CACHE = {}


def _latn_font():
    """返回拉丁回退字体的注册名（首个存在的文件）；无则 None。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if _LATN_FONT[0] and _LATN_FONT[0] in pdfmetrics.getRegisteredFontNames():
        return _LATN_FONT[0]
    for i, f in enumerate(_LATN_FALLBACK_FILES):
        p = _font_path(f)
        if not p.is_file():
            continue
        name = f"EditNoteLatn{i}"
        if name not in pdfmetrics.getRegisteredFontNames():
            try:
                if p.suffix.lower() == ".ttc":
                    pdfmetrics.registerFont(TTFont(name, str(p), subfontIndex=0))
                else:
                    pdfmetrics.registerFont(TTFont(name, str(p)))
            except Exception:
                continue
        _LATN_FONT[0] = name
        return name
    return None


def _has_glyph(fontname, ch):
    """字体 cmap 是否含该字符形（查不到按有处理，沿用旧行为）。"""
    try:
        from reportlab.pdfbase import pdfmetrics
        cmap = _GLYPH_CACHE.get(fontname)
        if cmap is None:
            cmap = pdfmetrics.getFont(fontname).face.charToGlyph or {}
            _GLYPH_CACHE[fontname] = cmap
        return bool(cmap.get(ord(ch), 0))
    except Exception:
        return True


# PDF 书签跳转目标：页顶边距（pt）。PyMuPDF 对三元条目默认用 36pt，
# 点击后页面会被下拉约半厘米；0 虽是精确页顶，但某些阅读器会对
# “恰好页顶”的目标做特殊处理（如改变缩放），故取 1pt（0.35mm，
# 视觉等同页顶，又不触发该类逻辑）。
BOOKMARK_TOP_MARGIN = 1


def _detect_paper(w, h):
    """页面尺寸 → 纸张名（封面/说明/编辑说明共用）。"""
    if 350 < w < 385 and 510 < h < 535:
        return "32k"
    if 410 < w < 435 and 585 < h < 610:
        return "a5"
    if 515 < w < 535 and 725 < h < 750:
        return "16k"
    if 580 < w < 610 and 830 < h < 860:
        return "a4"
    if w < 400:
        return "32k"
    if w < 480:
        return "a5"
    if w < 560:
        return "16k"
    return "a4"


def _font_path(p):
    pp = Path(p)
    if not pp.is_absolute():
        pp = app_root() / pp
    return pp


_REPO_ROOT = app_root()
IMAGES_DIR = _REPO_ROOT / "assets" / "images"
#: 说明文件托管目录（用户私有，gitignore；仅 sample.txt 随包/进库）
NOTES_DIR = _REPO_ROOT / "assets" / "notes"

#: 封面图后缀（"不用管后缀名"；同号多文件并存时排序取第一个）
COVER_IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".tif", ".tiff",
                        ".bmp", ".gif", ".webp")
#: 角色→编号：1=封面图（前）/ 2=封底图（后）
COVER_ROLE_NUM = {"buddha": "1", "weituo": "2"}


def find_numbered_image(directory, num):
    """目录里找 `{num}.*` 图片（后缀不限，排序取第一个）；无则 None。"""
    try:
        d = Path(directory)
        if not d.is_dir():
            return None
        cands = sorted(
            (p for p in d.iterdir()
             if p.is_file() and p.stem == str(num)
             and p.suffix.lower() in COVER_IMAGE_SUFFIXES),
            key=lambda p: (p.suffix.lower(), p.name))
        return cands[0] if cands else None
    except Exception:
        return None


def resolve_cover_image(cfg_images: dict, key: str):
    """封面图解析：配置显式路径有效则用；否则按编号约定找
    `assets/images/{1|2}.*`（1=封面图，2=封底图，后缀不限）。
    关闭开关（enabled=False）返回 None。"""
    info = (cfg_images or {}).get(key) or {}
    if not bool(info.get("enabled", True)):
        return None
    f = (info.get("file") or "").strip()
    if f:
        p = _font_path(f)
        if p.is_file():
            return p
    num = COVER_ROLE_NUM.get(key)
    if num is None:
        return None
    return find_numbered_image(IMAGES_DIR, num)


def _face_has_cjk(fontname, sample=_CJK_SAMPLE):
    # 已注册字体是否覆盖样本字形（缺字形时 reportlab 会画成空白/方框）
    try:
        from reportlab.pdfbase import pdfmetrics
        face = pdfmetrics.getFont(fontname).face
        cmap = getattr(face, "charToGlyph", None)
        if not cmap:
            return True
        return all(cmap.get(ord(c), 0) for c in sample)
    except Exception:
        return True


def _register_font(name, path):
    """注册字体；若缺繁体字形则换用系统全字库（返回实际使用的字体名）。"""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    def _reg(n, p):
        if p.suffix.lower() == ".ttc":
            pdfmetrics.registerFont(TTFont(n, str(p), subfontIndex=0))
        else:
            pdfmetrics.registerFont(TTFont(n, str(p)))
    try:
        p = _font_path(path)
        key = str(p) if p.exists() else ""
    except Exception:
        key = ""
    if not key:
        return "Helvetica"
    hit = _REGISTERED.get(name)
    if hit is not None and hit[0] == key:
        return hit[1]
    eff = name if hit is None else _fresh_alias(name)
    try:
        _reg(eff, p)
        if _face_has_cjk(eff):
            _REGISTERED[name] = [key, eff]
            return eff
        for i, fb in enumerate(_FALLBACK_FONTS):
            fp = _font_path(fb)
            if not fp.exists():
                continue
            fn = f"{eff}__fb{i}"
            try:
                _reg(fn, fp)
                if _face_has_cjk(fn):
                    if str(path) not in _WARNED_FONTS:
                        _WARNED_FONTS.add(str(path))
                        print(f"font {path} lacks CJK glyphs; fallback -> {fb}")
                    _REGISTERED[name] = [key, fn]
                    return fn
            except Exception:
                continue
        _REGISTERED[name] = [key, eff]
        return eff
    except Exception:
        return "Helvetica"


def _resolve_cover_date(cfg, today=None):
    """封面日期行文本：`cover.date_text` 缺省 `{date}`（=今天，保持旧行为）；
    其中的 `{date}` 替换为今天；留空则返回 ""（调用方跳过绘制）。
    该行也可写任意文字（如制作者名字）。"""
    import datetime as _dt
    raw = (cfg or {}).get("date_text", "{date}")
    if raw is None:
        raw = "{date}"
    raw = str(raw)
    if "{date}" in raw:
        raw = raw.replace("{date}", today or _dt.date.today().isoformat())
    return raw.strip()


#: 封面「书籍版本/来源」行默认文字（按来源二选一）
ORGANIZER_DEFAULT_OFFICIAL = "CBETA 官方電子書"
ORGANIZER_DEFAULT_XML = "依 CBETA XML 自製"


def cover_organizer(cover, source):
    """封面「书籍版本/来源」行文本：按来源取对应键。

    `source`="xml" → `cover.organizer_xml`；否则 `cover.organizer_official`。
    键存在（即使为空=不绘制）就用它；键缺失则回退旧的 `cover.organizer`（兼容旧配置）。"""
    cover = cover or {}
    key = "organizer_xml" if str(source) == "xml" else "organizer_official"
    if key in cover:
        return str(cover.get(key) or "").strip()
    return str(cover.get("organizer") or "").strip()


#: 封面折行：行尾优先（留在行末）
_WRAP_AFTER = set("、，；。！？…）》”’") | set(",;.!?)")
#: 封面折行：行首优先（另起一行）
_WRAP_BEFORE = set("（《“‘") | set("(['\"")
#: 行首禁留（闭合标点不上行首）、行尾禁留（开放标点不下行末）
_WRAP_NO_HEAD = set("）》”’，。！？；…") | set(",.!?;)]}")
_WRAP_NO_TAIL = set("（《“‘") | set("([{\"")


def _wrap_cjk_lines(text, width_fn, avail):
    """CJK 优先断点折行 → 行列表（每行已 strip）。

    断点优先级：`、`等之后、`（`等之前、`——`（对）前后；无则按字折
    （ASCII 字母数字串不断开其内部；行首不留闭合标点）。
    width_fn(s) 返回字符串宽度；avail 为行宽上限。量宽失败回退等字数切分。
    """
    s = str(text or "")
    if not s:
        return []
    try:
        if width_fn(s) <= avail:
            return [s]
    except Exception:
        pass
    chars = list(s)
    n = len(chars)
    try:
        ws = [float(width_fn(c)) for c in chars]
    except Exception:
        ws = None
    if not ws:
        return [s]   # 量宽不可用：不折（调用方保证仅超宽才进）

    def _is_word(ch):
        return ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("0" <= ch <= "9")

    def _breakable(j, start):
        # 位置 j（在 chars[j] 前断）是否优先断点；start 为行首
        if j <= start or j >= n:
            return False
        if chars[j] == " " or chars[j - 1] == " ":
            return True
        if s.startswith("——", j):
            return True
        if j >= 2 and s.startswith("——", j - 2):
            return True   # 刚结束破折号对
        if chars[j - 1] in _WRAP_AFTER and chars[j] not in _WRAP_NO_HEAD:
            return True
        if chars[j] in _WRAP_BEFORE:
            return True
        return False

    lines = []
    start = 0
    while start < n:
        while start < n and chars[start] == " ":
            start += 1
        if start >= n:
            break
        cur = 0.0
        last = -1
        i = start
        while i < n:
            step = 2 if s.startswith("——", i) else 1
            wsum = sum(ws[i:i + step])
            if cur + wsum > avail and i > start:
                break
            cur += wsum
            j = i + step
            if j < n and _breakable(j, start):
                last = j
            i = j
            if i >= n:
                break
        if i >= n:
            tail = s[start:].strip()
            if tail:
                lines.append(tail)
            break
        b = last if last > start else -1
        if b < 0:
            # 无优先断点：按字折，不断开 ASCII 串与 —— 对
            b = i
            if chars[i] not in (" ",) and _is_word(chars[i]):
                j = i
                while j > start and _is_word(chars[j - 1]):
                    j -= 1
                if j > start:
                    b = j
            if b < n and chars[b] in _WRAP_NO_HEAD and b > start:
                b -= 1   # 闭合标点拉回本行
            if b <= start:
                b = i    # 保底，避免空行死循环
        lines.append(s[start:b].strip())
        start = b
    return [ln for ln in lines if ln]


def _cover_pdf(first_src: Path, title: str, out_path: Path, organizer: str="", config: dict=None):
    cfg=config or {}
    # 兼容新旧配置：优先 styles，其次 fonts/colors/sizes.ratios
    styles=cfg.get("styles",{})
    fonts=cfg.get("fonts",{})
    colors=cfg.get("colors",{})
    sizes=cfg.get("sizes",{})
    pos=cfg.get("positions",{})
    def _font(name, default):
        if name in styles and "font" in styles[name]:
            return styles[name]["font"]
        return fonts.get(name, default)
    def _color(name, default):
        if name in styles and "color" in styles[name]:
            return styles[name]["color"]
        return colors.get(name, default)
    def _ratio(name, default):
        if name in styles and "ratio" in styles[name]:
            return styles[name]["ratio"]
        return sizes.get("ratios", {}).get(name, default)
    def _delta(name, default):
        if name in styles and "delta" in styles[name]:
            return styles[name]["delta"]
        return sizes.get(f"{name}_delta", default)
    # 使用 pymupdf 获取尺寸与纸张类型
    try:
        import pymupdf
        src=pymupdf.open(first_src)
        rect=src[0].rect if len(src)>0 else pymupdf.Rect(0,0,595,842)
        src.close()
        width, height = rect.width, rect.height
        paper = _detect_paper(width, height)
        is_a5 = paper in ("a5", "32k")
    except:
        width, height = (419.5, 595.3)
        paper = "a5"
        is_a5 = True
        import pymupdf
        rect=pymupdf.Rect(0,0,width,height)
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import Color
    def reg(name, path):
        return _register_font(name, path)
    # 字体：优先 styles，其次 fonts（正文基准已统一）
    font_cbeta = reg("CoverSeries", _font("cbeta", "C:\\Windows\\Fonts\\simhei.ttf"))
    font_title = reg("CoverTitle", _font("title", "C:\\Windows\\Fonts\\Source Han Serif SC Heavy (TrueType).ttf"))
    font_toc_item = reg("CoverTocItem", _font("toc_item", "C:\\Windows\\Fonts\\simhei.ttf"))
    # 整理者与日期同字体：只注册日期字体，整理者行改用 font_date
    font_date = reg("CoverDate", _font("date", "C:\\Windows\\Fonts\\simhei.ttf"))
    for n in [font_cbeta, font_title, font_date]:
        if n not in pdfmetrics.getRegisteredFontNames():
            # fallback
            pass
    c=canvas.Canvas(str(out_path), pagesize=(width, height))
    _bg = _color("background", colors.get("background",[250,245,230])) if "background" in styles or "background" in colors else colors.get("background",[250,245,230])
    # 兼容 styles.background 结构 {"color": [...]}
    if "background" in styles and isinstance(styles["background"], dict) and "color" in styles["background"]:
        _bg = styles["background"]["color"]
    bg=_bg
    c.setFillColor(Color(bg[0]/255, bg[1]/255, bg[2]/255))
    c.rect(0,0,width,height, fill=1, stroke=0)
    # 正文大小为基准，其他按配置文件比例/增量派生（优先 styles，其次旧配置）
    body_a5 = sizes.get("body_a5", 10)
    body_a4 = sizes.get("body_a4", 12)
    body_16k = sizes.get("body_16k", 11)
    body_32k = sizes.get("body_32k", 9)
    # 兼容 styles.body 写法
    if "body" in styles and isinstance(styles["body"], dict):
        body_a5 = styles["body"].get("a5", body_a5)
        body_a4 = styles["body"].get("a4", body_a4)
        body_16k = styles["body"].get("16k", body_16k)
        body_32k = styles["body"].get("32k", body_32k)
    ratios = sizes.get("ratios", {})
    toc_delta = _delta("toc_item", 1)
    # 纸张对应正文字体与边距（优先纸张定义，无则用 margin_ratio）
    body_map = {"a5": body_a5, "a4": body_a4, "16k": body_16k, "32k": body_32k}
    base_sz = body_map.get(paper, body_a4)
    # 边距：优先 sizes.margins[纸张]，无则用 sizes.margin_ratio 比例
    margins_cfg = sizes.get("margins", {})
    margin_ratio_cfg = sizes.get("margin_ratio", {})
    def _get_margin(side):
        if paper in margins_cfg:
            m = margins_cfg[paper]
            if isinstance(m, dict) and side in m:
                return float(m[side])
            if isinstance(m, (int, float)):
                return float(m)
        if isinstance(margin_ratio_cfg, dict) and side in margin_ratio_cfg:
            return (width if side in ("left", "right") else height) * float(margin_ratio_cfg[side])
        if isinstance(margin_ratio_cfg, (int, float)):
            return (width if side in ("left", "right") else height) * float(margin_ratio_cfg)
        return 40.0
    # 封面文本区（pt）：边距优先生效（CBETA 左上、标题/整理者/日期居中均以此为界）
    left=_get_margin("left")
    right=_get_margin("right")
    top=_get_margin("top")
    bottom=_get_margin("bottom")
    avail=width-left-right
    cx=left+avail/2
    # 兼容旧逻辑的 base_sz 覆盖（保持 is_a5 分支兼容）
    _legacy_base = body_a5 if is_a5 else body_a4
    if base_sz is None:
        base_sz = _legacy_base
    def _r(name, default):
        return _ratio(name, default)
    # 左上系列名/落款（cover.imprint；留空则不绘制），位置以页边距为准（margins.left/top）
    topleft_sz=base_sz
    left_m=left
    top_m=top
    cbeta_sz=sizes.get("cbeta_a5" if is_a5 else "cbeta_a4", base_sz * _r("cbeta", 1.0))
    if "cbeta_a5" not in sizes and "ratios" not in sizes and "body_a5" not in sizes and "cbeta" not in styles:
        cbeta_sz=sizes.get("cbeta_a5" if is_a5 else "cbeta_a4", 10)
    topleft_sz=cbeta_sz
    c.setFillColor(Color(*[v/255 for v in _color("cbeta",[51,51,51])]))
    try:
        c.setFont(font_cbeta, cbeta_sz)
    except:
        c.setFont("Helvetica", cbeta_sz)
    # 处理空格（左上落款文字，可在 cover.imprint 配置；留空则不绘制）
    txt=cfg.get("imprint", "CBETA 電子佛典自選叢書")
    parts=txt.split(" ")
    cur_x=left_m
    cur_y=height - top_m - cbeta_sz
    for idx, part in enumerate(parts):
        if part:
            try:
                c.setFont(font_cbeta, cbeta_sz)
            except:
                c.setFont("Helvetica", cbeta_sz)
            c.drawString(cur_x, cur_y, part)
            cur_x+=c.stringWidth(part, font_cbeta if font_cbeta in pdfmetrics.getRegisteredFontNames() else "Helvetica", cbeta_sz)
        if idx < len(parts)-1:
            c.setFont("Helvetica", cbeta_sz)
            cur_x+=c.stringWidth(" ", "Helvetica", cbeta_sz)
    # 书名居中 Y 25%（1/4 高度；基准=正文；Y 位置读 positions.title_y_ratio）。
    # 组行/整理者/日期沿用旧基准：组行起始按 group_y_ratio（缺省 0.30 即旧位），
    # 书名抬高的差值从组行起始扣除（只抬书名，其余像素级不动；两者设一样即回旧版）。
    y_title=height*(1 - pos.get("title_y_ratio", 0.25))
    y_spine=height*(1 - pos.get("group_y_ratio", 0.30))
    t_sz=sizes.get("title_a5" if is_a5 else "title_a4", base_sz * _r("title", 3.0))
    if "title_a5" not in sizes and "ratios" not in sizes and "body_a5" not in sizes:
        t_sz=base_sz*3.0
    c.setFillColor(Color(*[v/255 for v in _color("title",[0,0,0])]))
    try:
        c.setFont(font_title, t_sz)
    except:
        c.setFont("Helvetica", t_sz)
    # 处理空格和自动换行；“｜”为手动换行（丛书名｜册名各居中一行）
    def draw_centred_with_spaces(y, text, font, size):
        cur_y=y
        for seg in (text or "").split("｜"):
            cur_y=_draw_centred_segment(cur_y, seg, font, size)
        return cur_y
    def _draw_centred_segment(y, text, font, size):
        # 分割空格，计算总宽
        parts=text.split(" ")
        # 计算总宽：中文部分用 font，空格用 Helvetica
        total=0
        for idx, part in enumerate(parts):
            if part:
                total+=c.stringWidth(part, font, size)
            if idx < len(parts)-1:
                total+=c.stringWidth(" ", "Helvetica", size)
        # 若过宽，折行（优先断点 `、`/`（`/破折号，无则按字；文本区宽度 = 页宽 - 左右边距）
        if total > avail:
            lines = _wrap_cjk_lines(
                text, lambda s: c.stringWidth(s, font, size), avail)
            if not lines:
                lines = [text]
            cur_y=y
            for line in lines:
                # 对每行重新计算居中
                lw=0
                lparts=line.split(" ")
                for idx, p in enumerate(lparts):
                    if p:
                        lw+=c.stringWidth(p, font, size)
                    if idx < len(lparts)-1:
                        lw+=c.stringWidth(" ", "Helvetica", size)
                cur_x=cx-lw/2
                for idx, p in enumerate(lparts):
                    if p:
                        c.setFont(font, size)
                        c.drawString(cur_x, cur_y, p)
                        cur_x+=c.stringWidth(p, font, size)
                    if idx < len(lparts)-1:
                        c.setFont("Helvetica", size)
                        cur_x+=c.stringWidth(" ", "Helvetica", size)
                cur_y-=size+6
            return cur_y
        else:
            cur_x=cx-total/2
            for idx, part in enumerate(parts):
                if part:
                    c.setFont(font, size)
                    c.drawString(cur_x, y, part)
                    cur_x+=c.stringWidth(part, font, size)
                if idx < len(parts)-1:
                    c.setFont("Helvetica", size)
                    c.drawString(cur_x, y, " ")
                    cur_x+=c.stringWidth(" ", "Helvetica", size)
            return y-size-6
    _segs=[s for s in str(title or "").split("｜")]
    _main=_segs[0] if _segs else ""
    _group=_segs[1] if len(_segs)>1 else ""
    y_after=draw_centred_with_spaces(y_title, _main, font_title, t_sz) if _main else y_spine
    if _main and _group:
        # 组行回落到旧基准：只抬书名（多行折行亦安全，只会更宽松）
        y_after-=(y_title-y_spine)
    if _group:
        # 部类/刊本分组路径：按 " / " 每段一行（不再整行折行）；字体字号沿用目录条目；
        # 超宽单行（如一行模式）截断加 …（多行短段不受影响）
        _tm=_toc_text_style(cfg, width, height, paper)
        _isz=_tm["item_sz"]
        c.setFillColor(Color(*[v/255 for v in _color("toc_item",[30,30,30])]))
        for _lv in [s for s in re.split(r"\s*/\s*", _group) if s]:
            try:
                c.setFont(font_toc_item, _isz)
                _ff = font_toc_item
            except Exception:
                c.setFont("Helvetica", _isz)
                _ff = "Helvetica"
            _lv = _lv.strip()
            if _lv and c.stringWidth(_lv, _ff, _isz) > avail:
                while _lv and c.stringWidth(_lv + "…", _ff, _isz) > avail:
                    _lv = _lv[:-1]
                _lv = (_lv + "…") if _lv else ""
            if not _lv:
                continue
            c.drawCentredString(cx, y_after, _lv)
            y_after-=_isz*1.6
    # 整理者 Y 84%（Y 位置读 positions.organizer_y_ratio）；
    # 字体字号均与日期一致（左上角文字大小）
    if organizer:
        y_org=height*(1 - pos.get("organizer_y_ratio", 0.84))
        o_sz=topleft_sz
        c.setFillColor(Color(*[v/255 for v in _color("organizer",[51,51,51])]))
        draw_centred_with_spaces(y_org, organizer, font_date, o_sz)
    # 日期 Y 90%（读 positions.date_y_ratio），字号与左上角文字一致；
    # 文本取 cover.date_text（`{date}`=今天；留空不绘制）
    _date_text=_resolve_cover_date(cfg)
    if _date_text:
        y_date=height*(1 - pos.get("date_y_ratio", 0.90))
        d_sz=topleft_sz
        c.setFillColor(Color(*[v/255 for v in _color("date",[100,100,100])]))
        draw_centred_with_spaces(y_date, _date_text, font_date, d_sz)
    c.showPage()
    c.save()
    return out_path


def _toc_text_style(cfg, width, height, paper):
    """目录/说明文字的共用字号、行距与位置（避免两者漂移）。"""
    styles=cfg.get("styles",{})
    sizes=cfg.get("sizes",{})
    pos=cfg.get("positions",{})
    def _ratio(name, default):
        if name in styles and "ratio" in styles[name]:
            return styles[name]["ratio"]
        return sizes.get("ratios", {}).get(name, default)
    def _delta(name, default):
        if name in styles and "delta" in styles[name]:
            return styles[name]["delta"]
        return sizes.get(f"{name}_delta", default)
    body_a5 = sizes.get("body_a5", 10)
    body_a4 = sizes.get("body_a4", 12)
    body_16k = sizes.get("body_16k", 11)
    body_32k = sizes.get("body_32k", 9)
    if "body" in styles and isinstance(styles["body"], dict):
        body_a5 = styles["body"].get("a5", body_a5)
        body_a4 = styles["body"].get("a4", body_a4)
        body_16k = styles["body"].get("16k", body_16k)
        body_32k = styles["body"].get("32k", body_32k)
    toc_delta = _delta("toc_item", 1)
    if "body_a5" not in sizes and "toc_item_a5" in sizes:
        body_a5 = max(8, sizes.get("toc_item_a5", 12) - toc_delta)
        body_a4 = max(8, sizes.get("toc_item_a4", 16) - toc_delta)
    base_map = {"a5": body_a5, "a4": body_a4, "16k": body_16k, "32k": body_32k}
    base = base_map.get(paper, body_a4)
    margins_cfg = sizes.get("margins", {})
    margin_ratio_cfg = sizes.get("margin_ratio", {})
    def _get_margin(side):
        if paper in margins_cfg:
            mm = margins_cfg[paper]
            if isinstance(mm, dict) and side in mm:
                return float(mm[side])
            if isinstance(mm, (int, float)):
                return float(mm)
        if isinstance(margin_ratio_cfg, dict) and side in margin_ratio_cfg:
            return (width if side in ("left", "right") else height) * float(margin_ratio_cfg[side])
        if isinstance(margin_ratio_cfg, (int, float)):
            return (width if side in ("left", "right") else height) * float(margin_ratio_cfg)
        return 40.0
    title_sz = sizes.get("toc_title", base * _ratio("toc_title", 1.9))
    if "toc_title" in sizes and "body_a5" not in sizes and "styles" not in cfg:
        title_sz = sizes.get("toc_title", base * 1.9)
    if "toc_item" in sizes and "body_a5" not in sizes and "ratios" not in sizes and "toc_item" not in styles:
        item_sz = sizes.get("toc_item", base * 1.0)
    elif _ratio("toc_item", None) is not None:
        item_sz = base * _ratio("toc_item", 1.0)
    else:
        item_sz = base + _delta("toc_item", 1)
    return {
        "left": _get_margin("left"),
        "right": _get_margin("right"),
        "top": _get_margin("top"),
        "bottom": _get_margin("bottom"),
        "base": base,
        "title_y": height * (1 - pos.get("toc_y_ratio", 0.11)),
        "title_sz": title_sz,
        "item_y0": height * (1 - pos.get("toc_item_y_ratio", 0.20)),
        "item_sz": item_sz,
        "page_sz": sizes.get("toc_page", base * _ratio("toc_page", 0.9)),
        "line_h": item_sz * 1.6,
        "item_gap": item_sz * 0.4,
        "body_continue_y": height - 40,
    }

def _page_bg(cfg, key):
    """说明/目录页背景色：styles.{key}.color；缺省跟随封面 background；再缺省米色。"""
    styles = ((cfg or {}).get("styles", {}) or {})
    keys = (key, "background") if key != "background" else ("background",)
    for k in keys:
        info = styles.get(k) or {}
        c = info.get("color") if isinstance(info, dict) else None
        if isinstance(c, (list, tuple)) and len(c) == 3:
            try:
                return [int(v) for v in c]
            except Exception:
                pass
    return [250, 245, 230]

def _toc_pdf(titles: list[str], first_src: Path, out_path: Path, config: dict=None, page_nums: list[int]=None, toc_start_index: int=2):
    cfg=config or {}
    styles=cfg.get("styles",{})
    fonts=cfg.get("fonts",{})
    colors=cfg.get("colors",{})
    sizes=cfg.get("sizes",{})
    pos=cfg.get("positions",{})
    def _font(name, default):
        if name in styles and "font" in styles[name]:
            return styles[name]["font"]
        return fonts.get(name, default)
    def _color(name, default):
        if name in styles and "color" in styles[name]:
            return styles[name]["color"]
        return colors.get(name, default)
    def _ratio(name, default):
        if name in styles and "ratio" in styles[name]:
            return styles[name]["ratio"]
        return sizes.get("ratios", {}).get(name, default)
    def _delta(name, default):
        if name in styles and "delta" in styles[name]:
            return styles[name]["delta"]
        return sizes.get(f"{name}_delta", default)
    try:
        import pymupdf
        src=pymupdf.open(first_src)
        rect=src[0].rect if len(src)>0 else pymupdf.Rect(0,0,595,842)
        src.close()
        width, height = rect.width, rect.height
    except:
        width, height = (595,842)
    # 纸张类型判定与边距（优先纸张定义，无则用 margin_ratio）
    def _detect_paper(w, h):
        if 350 < w < 385 and 510 < h < 535:
            return "32k"
        if 410 < w < 435 and 585 < h < 610:
            return "a5"
        if 515 < w < 535 and 725 < h < 750:
            return "16k"
        if 580 < w < 610 and 830 < h < 860:
            return "a4"
        if w < 400:
            return "32k"
        if w < 480:
            return "a5"
        if w < 560:
            return "16k"
        return "a4"
    paper_toc = _detect_paper(width, height)
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import Color
    def reg(name, path):
        return _register_font(name, path)
    font_toc_title=reg("TocTitle", _font("toc_title", "C:\\Windows\\Fonts\\Source Han Serif SC Heavy (TrueType).ttf"))
    font_toc_item=reg("TocItem", _font("toc_item", "C:\\Windows\\Fonts\\Source Han Serif SC Heavy (TrueType).ttf"))
    font_page=reg("TocPage", _font("toc_page", "C:\\Windows\\Fonts\\simhei.ttf"))
    c=canvas.Canvas(str(out_path), pagesize=(width, height))
    _toc_bg=_page_bg(cfg, "toc_background")
    def _paint_bg():
        c.setFillColor(Color(_toc_bg[0]/255, _toc_bg[1]/255, _toc_bg[2]/255))
        c.rect(0, 0, width, height, fill=1, stroke=0)
    _paint_bg()
    # 目录标题与正文使用共用字号、行距与位置。
    tm=_toc_text_style(cfg, width, height, paper_toc)
    toc_left=tm["left"]
    toc_right=tm["right"]
    y_toc=tm["title_y"]
    t_sz=tm["title_sz"]
    c.setFillColor(Color(*[v/255 for v in _color("toc_title",[0,0,0])]))
    try:
        c.setFont(font_toc_title, t_sz)
    except:
        c.setFont("Helvetica", t_sz)
    c.drawCentredString(width/2, y_toc, "目录")
    # 目录标题后空一行再开始条目（Y 20% 起，可配置 toc_item_y_ratio）
    y=tm["item_y0"]
    c.setFillColor(Color(*[v/255 for v in _color("toc_item",[30,30,30])]))
    item_sz=tm["item_sz"]
    page_sz=tm["page_sz"]
    line_h=tm["line_h"]
    item_gap=tm["item_gap"]
    # 若条目多，压缩间距
    total_needed=len(titles)*(line_h+item_gap)
    if total_needed > height*0.6 and len(titles)>10:
        # 压缩
        item_gap=item_sz*0.2
        line_h=item_sz*1.4
    link_rects=[]  # (最终PDF 1-based页码, y上, y下) reportlab 自底向上坐标
    toc_pg=1       # toc.pdf 内页码（1-based）；最终文档中 toc.pdf 从第3页开始
    for i,t in enumerate(titles,1):
        if y < 40:
            c.showPage()
            _paint_bg()
            y=tm["body_continue_y"]
            toc_pg+=1
            try:
                c.setFont(font_toc_item, item_sz)
            except:
                c.setFont("Helvetica", item_sz)
        # 一级目录 左对齐（经书加序号，全局连续、自适应补零；与 EPUB 目录同规则）
        txt = _epub_seq_title(i, len(titles), f"{t}")
        if c.stringWidth(txt, font_toc_item if font_toc_item in pdfmetrics.getRegisteredFontNames() else "Helvetica", item_sz) > width - toc_left - toc_right - 40:
            txt=txt[:38]+"..."
        try:
            c.setFont(font_toc_item, item_sz)
        except:
            c.setFont("Helvetica", item_sz)
        c.setFillColor(Color(*[v/255 for v in _color("toc_item",[30,30,30])]))
        c.drawString(toc_left, y, txt)
        # 经名加粗：同行再描一次（微右移），模拟粗体
        c.drawString(toc_left + max(0.3, item_sz*0.03), y, txt)
        # 页码 右对齐（真实页号；缺失时按每书1页估算）
        page_text=str(page_nums[i-1]) if page_nums and i-1<len(page_nums) else str(i+4)
        c.setFillColor(Color(*[v/255 for v in _color("toc_page",[100,100,100])]))
        try:
            c.setFont(font_page, page_sz)
        except:
            c.setFont("Helvetica", page_sz)
        c.drawRightString(width - toc_right, y, page_text)
        link_rects.append((toc_start_index+toc_pg, y, y+line_h))
        y-=(line_h+item_gap)
    c.showPage()
    c.save()
    return link_rects

class MergeCancelled(Exception):
    # 用户取消合成（由 progress 回调返回 False 触发）
    pass


def _intro_pdf(intro: dict, first_src: Path, out_path: Path, config: dict=None) -> int:
    # 说明页（部类统计 + 完整清单）；多页自动分页。返回页数。
    cfg=config or {}
    styles=cfg.get("styles",{})
    fonts=cfg.get("fonts",{})
    colors=cfg.get("colors",{})
    sizes=cfg.get("sizes",{})
    def _font(name, default):
        if name in styles and "font" in styles[name]:
            return styles[name]["font"]
        return fonts.get(name, default)
    def _color(name, default):
        if name in styles and "color" in styles[name]:
            return styles[name]["color"]
        return colors.get(name, default)
    def _ratio(name, default):
        if name in styles and "ratio" in styles[name]:
            return styles[name]["ratio"]
        return sizes.get("ratios", {}).get(name, default)
    try:
        import pymupdf
        src=pymupdf.open(first_src)
        rect=src[0].rect if len(src)>0 else pymupdf.Rect(0,0,595,842)
        src.close()
        width, height = rect.width, rect.height
    except:
        width, height = (595,842)
    def _detect_paper(w, h):
        if 350 < w < 385 and 510 < h < 535:
            return "32k"
        if 410 < w < 435 and 585 < h < 610:
            return "a5"
        if 515 < w < 535 and 725 < h < 750:
            return "16k"
        if 580 < w < 610 and 830 < h < 860:
            return "a4"
        if w < 400:
            return "32k"
        if w < 480:
            return "a5"
        if w < 560:
            return "16k"
        return "a4"
    paper=_detect_paper(width, height)
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.colors import Color
    def reg(name, path):
        return _register_font(name, path)
    f_title=reg("IntroTitle", _font("toc_title", "C:\\Windows\\Fonts\\Source Han Serif SC Heavy (TrueType).ttf"))
    f_body=reg("IntroBody", _font("toc_item", "C:\\Windows\\Fonts\\Source Han Serif SC Heavy (TrueType).ttf"))
    # 简介三行（本丛书…/三藏分布/部类分布）：默认仿宋；可在「封面/版式 → 字体」改
    f_summary=reg("IntroSummary", _font("intro_summary", "C:\\Windows\\Fonts\\simfang.ttf"))
    tm=_toc_text_style(cfg, width, height, paper)
    left=tm["left"]; right=tm["right"]; bottom=tm["bottom"]
    title_sz=tm["title_sz"]
    item_sz=tm["item_sz"]
    # 简介单行行距；清单条目沿用目录条目行距
    summary_advance=item_sz*1.2
    row_advance=item_sz*1.35
    body_continue_y=tm["body_continue_y"]
    c=canvas.Canvas(str(out_path), pagesize=(width, height))
    pages=0
    _intro_bg=_page_bg(cfg, "intro_background")
    def _paint_bg():
        c.setFillColor(Color(_intro_bg[0]/255, _intro_bg[1]/255, _intro_bg[2]/255))
        c.rect(0, 0, width, height, fill=1, stroke=0)
    _paint_bg()
    def _new_page():
        nonlocal pages, y
        c.showPage()
        _paint_bg()
        pages+=1
        y=body_continue_y
    def _draw(text, x, y0, font, size, color):
        try:
            c.setFont(font, size)
        except Exception:
            c.setFont("Helvetica", size)
        c.setFillColor(Color(*[v/255 for v in color]))
        c.drawString(x, y0, text)
    def _fit(text, font, size, maxw):
        if c.stringWidth(text, font if font in pdfmetrics.getRegisteredFontNames() else "Helvetica", size) <= maxw:
            return text
        while text and c.stringWidth(text+"…", font if font in pdfmetrics.getRegisteredFontNames() else "Helvetica", size) > maxw:
            text=text[:-1]
        return text+"…"
    # 标题
    pages=1
    y=tm["title_y"]
    try:
        c.setFont(f_title, title_sz)
    except Exception:
        c.setFont("Helvetica", title_sz)
    c.setFillColor(Color(*[v/255 for v in _color("toc_title",[0,0,0])]))
    c.drawCentredString(width/2, y, intro.get("title","说明"))
    y=tm["item_y0"]
    maxw=width-left-right
    if intro.get("note"):
        # 说明标题下一行：居中注明（如「依 CBETA XML 自制」）；其后空一行
        try:
            c.setFont(f_body, item_sz)
        except Exception:
            c.setFont("Helvetica", item_sz)
        c.setFillColor(Color(*[v/255 for v in _color("toc_item",[30,30,30])]))
        c.drawCentredString(width/2, y, _fit(str(intro["note"]), f_body, item_sz, maxw))
        y-=summary_advance*2
    for ln in intro.get("summary",[]) or []:
        if y<bottom+summary_advance:
            _new_page()
        _draw(_fit(ln, f_summary, item_sz, maxw), left, y, f_summary, item_sz, _color("toc_item",[30,30,30]))
        y-=summary_advance
    for header, rows in intro.get("sections",[]) or []:
        y-=item_sz*0.5
        # 部类/刊本信息：含路径（" / "）时每段独立成行；字体字号沿用目录条目
        for seg in [s for s in re.split(r"\s*/\s*", str(header)) if s]:
            if y<bottom+summary_advance:
                _new_page()
            _draw(_fit(seg, f_body, item_sz, maxw), left, y, f_body, item_sz, _color("toc_item",[30,30,30]))
            y-=summary_advance
        for r in rows:
            if y<bottom+row_advance:
                _new_page()
            _draw(_fit(r, f_body, item_sz, maxw-item_sz), left+item_sz, y, f_body, item_sz, _color("toc_item",[30,30,30]))
            y-=row_advance
    c.showPage()
    c.save()
    return pages


#: 编辑说明默认标题（TXT 无 <title> 行时）
EDITNOTE_DEFAULT_TITLE = "编辑说明"


def _epub_seq_title(i, total, title):
    """目录经书序号：全局 1-based，自适应补零（宽度看总部数）；
    EPUB 只对经书条目调用（封面/丛书目录/编辑说明/说明页不加），
    PDF 目录页共用此规则。"""
    try:
        _t = max(1, int(total or 1))
    except Exception:
        _t = 1
    _w = len(str(_t))
    return f"{max(1, int(i)):0{_w}d}. {title}"


def resolve_note_path(path):
    """说明 TXT 路径解析：相对路径按数据根（`app_root`）解析；空返回 None。"""
    p = str(path or "").strip()
    if not p:
        return None
    pp = Path(p)
    return pp if pp.is_absolute() else app_root() / pp


def parse_editnote_file(path):
    """编辑说明 TXT → {"title": str, "lines": [(kind, align, text), ...]}；
    文件缺失/空/无有效行返回 None。

    行前缀（对齐可与样式叠加，如 `<center><h1>xxx`；标签须与内容同行，
    单独成行的 `<center>` 只作用于空行、无效果）：
    `<title>` 标题（仅首个有效，不排版）；`<h1>`–`<h5>` 分级标题；
    `<b>` 整行加粗；`<center>/<right>` 对齐（默认左），行尾闭合
    `</center>/</right>` 可写可不写（如 `<center><h5>xxx</h5></center>`）。
    `<pb>`（独占一行，大小写不限）为强制分页：PDF 另起一页；
    EPUB 无固定页，输出空 break-div（`break-before:page`＋`page-break-before:always`
    兼容回退），认的阅读器分页、不认的零高度无残留（不切文件）。
    空格空行保留：行首空白原样保留（半角/全角空格均保留，制表按 4 空格展开；
    尾空格去掉），空行（含全空白行）均为段间距。
    标签行空格规则：标签前的空白一律保留；标签后的半角空格视为分隔符去掉
    （`<h1> 凡例`写法不受影响），全角空格/制表为有意缩进保留。
    """
    _np = resolve_note_path(path)
    if _np is None:
        return None
    try:
        text = _np.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    title = EDITNOTE_DEFAULT_TITLE
    title_set = False
    lines = []
    for raw in text.splitlines():
        if not raw.strip():
            lines.append(("gap", "left", ""))
            continue
        s = raw.rstrip()
        align = "left"
        rest = s.strip()
        while True:
            low = rest.lower()
            if low.startswith("<center>"):
                align = "center"
                rest = rest[len("<center>"):].strip()
                continue
            if low.startswith("<right>"):
                align = "right"
                rest = rest[len("<right>"):].strip()
                continue
            break
        # 强制分页（独占一行；行内夹杂文字的不认，走正文）
        if rest.lower() in ("<pb>", "<pb/>"):
            lines.append(("pb", "left", ""))
            continue
        # 行尾对齐闭合（</center>/</right>）直接由正则消费，不会漏进正文
        # （旧逻辑下 `<h5>xxx</h5></center>` 的 `</h5>` 会残留）
        m = re.match(r"^<(title|h1|h2|h3|h4|h5|b)>(.*?)\s*(</\1>)?\s*(</(?:center|right)>)?\s*$",
                     rest, re.IGNORECASE)
        if m:
            kind, text = m.group(1).lower(), m.group(2)
            # 内容仅去尾空格，行首空格保留
            text = re.sub(r"\s*</(center|right)>\s*$", "", text, flags=re.IGNORECASE).rstrip()
            if kind == "title":
                if not title_set and text.strip():
                    title = text.strip()
                    title_set = True
                continue
            # 标签后半角空格是分隔符（去掉），全角/制表是有意缩进（保留）；
            # 标签前的空白一律保留（制表展开）
            text = text.lstrip(" ")
            _pre = s[:len(s) - len(s.lstrip())].replace("\t", "    ")
            text = _pre + text.replace("\t", "    ")
            if not text.strip():
                continue
            lines.append((kind, align, text))
        else:
            # 无样式标签：行首空白原样保留（rest 已 strip，补回前导空白串；
            # 全角空格是中文常用缩进，lstrip(" ") 会丢掉，必须用全空白判定）。
            # 纯标签残留行（如单独的 </center>）直接跳过，不占垂直空间。
            _core = re.sub(r"\s*</(center|right)>\s*$", "", rest, flags=re.IGNORECASE).strip()
            if not _core:
                continue
            _lead = s[:len(s) - len(s.lstrip())].replace("\t", "    ")
            lines.append(("body", align, _lead + _core))
    if not any(k not in ("gap", "pb") for k, _, _ in lines):
        return None
    return {"title": title, "lines": lines}


def _as_editnotes(editnote):
    """把 editnote 参数统一为已解析说明页列表（支持 None / dict / list）。

    合并时可能同时插「全局编辑说明」与「当前丛书特定说明」两页；
    调用方传解析后的 dict 或 dict 列表，这里只做归一，不解析文件。"""
    if not editnote:
        return []
    if isinstance(editnote, (list, tuple)):
        return [e for e in editnote if e]
    return [editnote]


def _editnote_pdf(parsed, first_src: Path, out_path: Path, config: dict=None) -> int:
    """编辑说明页（TXT 转排版）；多页自动分页。返回页数。
    字号字体沿用封面设置：标题/h1=toc_title，h2–h5 依次缩小，正文=页面基准字号；
    加粗用同行微右移模拟（无粗体字形注册）。"""
    cfg=config or {}
    styles=cfg.get("styles",{})
    fonts=cfg.get("fonts",{})
    colors=cfg.get("colors",{})
    sizes=cfg.get("sizes",{})
    def _font(name, default):
        if name in styles and "font" in styles[name]:
            return styles[name]["font"]
        return fonts.get(name, default)
    def _color(name, default):
        if name in styles and "color" in styles[name]:
            return styles[name]["color"]
        return colors.get(name, default)
    try:
        import pymupdf
        src=pymupdf.open(first_src)
        rect=src[0].rect if len(src)>0 else pymupdf.Rect(0,0,595,842)
        src.close()
        width, height = rect.width, rect.height
    except:
        width, height = (595,842)
    tm=_toc_text_style(cfg, width, height, _detect_paper(width, height))
    left=tm["left"]; right=tm["right"]; bottom=tm["bottom"]
    title_sz=tm["title_sz"]; item_sz=tm["item_sz"]
    # 编辑说明正文用独立字号（cover.sizes.editnote_body，缺省 12；6–40 钳制）
    try:
        body_sz=int((sizes.get("editnote_body", 12) or 12))
    except Exception:
        body_sz=12
    body_sz=max(6, min(40, body_sz))
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.lib.colors import Color
    def reg(name, path):
        return _register_font(name, path)
    def _efont(name, fb_name, fb_default):
        # 编辑说明字体选项缺省时回退到目录/说明同类字体
        v = _font(name, None)
        return v if v else _font(fb_name, fb_default)
    f_title=reg("EditNoteTitle", _efont("editnote_title", "toc_title", "C:\\Windows\\Fonts\\simhei.ttf"))
    f_body=reg("EditNoteBody", _efont("editnote_body", "toc_item", "C:\\Windows\\Fonts\\simhei.ttf"))
    f_latn=_latn_font() or ""   # 拉丁扩展回退（ā/ś/梵文转写）；无则沿用主字体
    def _fn(name):
        return name if name in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    c=canvas.Canvas(str(out_path), pagesize=(width, height))
    pages=1
    y=tm["title_y"]
    _pending_gap=0.0   # 累积的空行高度：作者内容，换页也不丢（带到新页顶部）
    _drawn=False       # 本页是否已落笔（标题不计；<pb> 防文件头/连续/尾部空白页用）
    def _new_page():
        nonlocal pages, y, _drawn
        c.showPage()
        pages+=1
        y=tm["body_continue_y"]
        _drawn=False
    def _run_font(ch, primary):
        # 该字符的绘制字体：拉丁扩展区无条件回退（主字体可能画坏），
        # 主字体缺字形也回退；回退字体须覆盖该字符，否则沿用主字体
        o = ord(ch)
        if f_latn and f_latn != primary and (
                any(lo <= o <= hi for lo, hi in _LATN_ALWAYS_RANGES)
                or not _has_glyph(primary, ch)):
            if _has_glyph(f_latn, ch):
                return f_latn
        return primary
    def _runs(text, primary):
        # 按字体切分 run：[(font, seg)]（相邻同字体合并）
        out = []
        for ch in text:
            f = _run_font(ch, primary)
            if out and out[-1][0] == f:
                out[-1][1] += ch
            else:
                out.append([f, ch])
        return [(f, s) for f, s in out]
    def _mixed_width(text, primary, size):
        return sum(c.stringWidth(seg, _fn(f), size) for f, seg in _runs(text, primary))
    def _wrap(text, font, size, maxw):
        if _mixed_width(text, font, size) <= maxw:
            return [text]
        out=[]; cur=""; curw=0.0
        for ch in text:
            cw=c.stringWidth(ch, _fn(_run_font(ch, font)), size)
            if curw+cw<=maxw:
                cur+=ch; curw+=cw
            else:
                if cur:
                    out.append(cur)
                cur=ch; curw=cw
        if cur:
            out.append(cur)
        return out or [text]
    def _put(text, font, size, color, align, advance, bold=False):
        nonlocal y, _pending_gap, _drawn
        maxw=width-left-right
        if _pending_gap:
            if y-_pending_gap<bottom+advance:
                _new_page()
            y-=_pending_gap
            _pending_gap=0.0
        for ln in _wrap(text, font, size, maxw):
            if y<bottom+advance:
                _new_page()
            total=_mixed_width(ln, font, size)
            if align=="center":
                x=width/2-total/2
            elif align=="right":
                x=width-right-total
            else:
                x=left
            c.setFillColor(Color(*[v/255 for v in color]))
            for f, seg in _runs(ln, font):
                c.setFont(_fn(f), size)
                c.drawString(x, y, seg)
                if bold:
                    c.drawString(x+max(0.3,size*0.03), y, seg)
                x+=c.stringWidth(seg, _fn(f), size)
            y-=advance
            _drawn=True
    _put(parsed.get("title") or EDITNOTE_DEFAULT_TITLE,
         f_title, title_sz, _color("toc_title",[0,0,0]), "center", title_sz*1.8)
    _drawn=False   # 标题不计入落笔（行首 <pb> 不另起空白页）
    _lines = parsed.get("lines", []) or []
    for _li, (kind, align, text) in enumerate(_lines):
        if kind == "pb":
            # 强制分页（仅编辑说明页）：丢弃待处理空行；页首/连续/尾部 mark 不另起空白页
            _pending_gap = 0.0
            _more = any(k not in ("gap", "pb") for k, _, _ in _lines[_li + 1:])
            if _drawn and _more:
                _new_page()
            continue
        if kind=="gap":
            _pending_gap+=body_sz*0.8
            continue
        if kind=="h1":
            _put(text, f_title, title_sz, _color("toc_title",[0,0,0]), align, title_sz*1.5)
        elif kind=="h2":
            _put(text, f_title, title_sz*0.85, _color("toc_title",[0,0,0]), align, title_sz*1.3)
        elif kind=="h3":
            _put(text, f_title, title_sz*0.8, _color("toc_title",[0,0,0]), align, title_sz*1.2)
        elif kind=="h4":
            _put(text, f_title, title_sz*0.7, _color("toc_title",[0,0,0]), align, title_sz*1.1)
        elif kind=="h5":
            _put(text, f_title, title_sz*0.6, _color("toc_title",[0,0,0]), align, title_sz*1.05)
        elif kind=="b":
            _put(text, f_body, body_sz, _color("toc_item",[30,30,30]), align, body_sz*1.35, bold=True)
        else:
            _put(text, f_body, body_sz, _color("toc_item",[30,30,30]), align, body_sz*1.35)
    c.showPage()
    c.save()
    return pages


def _blank_pdf(first_src: Path, out_path: Path):
    try:
        import pymupdf
    except ImportError:
        import pymupdf as fitz
        import sys
        sys.modules['pymupdf']=fitz
        import pymupdf
    src=pymupdf.open(first_src)
    rect=src[0].rect if len(src)>0 else pymupdf.Rect(0,0,595,842)
    src.close()
    doc=pymupdf.open()
    doc.new_page(width=rect.width, height=rect.height)
    doc.save(out_path)
    return out_path

def _image_pdf(first_src: Path, image_path: Path, out_path: Path):
    # 单页图像（封面图/封底图）：与正文页同尺寸，图按 80% 居中。
    # 直接嵌入不转码：JPEG 原字节 DCT 直通；tif/png 无损嵌入（像素一致）。
    try:
        import pymupdf
    except ImportError:
        import pymupdf as fitz
        import sys
        sys.modules['pymupdf']=fitz
        import pymupdf
    try:
        src=pymupdf.open(first_src)
        rect=src[0].rect if len(src)>0 else pymupdf.Rect(0,0,595,842)
        src.close()
        width, height = rect.width, rect.height
    except:
        width, height = (595,842)
    try:
        with pymupdf.open(str(image_path)) as _im:
            _ir=_im[0].rect if len(_im)>0 else pymupdf.Rect(0,0,0,0)
            iw, ih = _ir.width, _ir.height
    except Exception:
        iw = ih = 0
    doc=pymupdf.open()
    try:
        page=doc.new_page(width=width, height=height)
        if iw>0 and ih>0:
            scale=min(width*0.8/iw, height*0.8/ih)
            w, h = iw*scale, ih*scale
            page.insert_image(pymupdf.Rect((width-w)/2, (height-h)/2,
                                           (width+w)/2, (height+h)/2),
                              filename=str(image_path))
    except Exception as e:
        print("image pdf fail", e)
    doc.save(out_path)
    doc.close()
    return out_path

def _add_toc_links(doc, link_rects, page_nums):
    # 目录页条目加跳转链接（PyMuPDF 坐标自顶向下，需翻转 reportlab 的 y）
    try:
        import pymupdf
    except ImportError:
        import pymupdf as fitz
        import sys
        sys.modules['pymupdf']=fitz
        import pymupdf
    for (fp, ytop, ybot), pnum in zip(link_rects, page_nums):
        if fp<1 or fp>len(doc):
            continue
        page=doc[fp-1]
        h=page.rect.height
        r=pymupdf.Rect(30, h-(ybot if ybot<=h else ytop), page.rect.width-30, h-(ytop if ytop<=h else ybot))
        try:
            page.insert_link({"kind": pymupdf.LINK_GOTO, "from": r, "page": max(0, pnum-1)})
        except Exception as e:
            print("toc link fail", e)

def merge_pdfs(sources: list[Path], out: Path, split_pages: int = 5000, titles: list[str]=None, collection_name: str=None, organizer: str="", cover_config: dict=None, intro: dict=None, progress=None, editnote: dict=None) -> list[Path]:
    if not sources:
        return []
    if not (cover_config or {}).get("enabled", True):
        return _merge_pdfs_bare(sources, out, split_pages, titles, progress)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir=out.parent / "_tmp_cover"
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)   # 清理上次异常残留
    tmp_dir.mkdir(exist_ok=True)
    try:
        return _merge_pdfs_impl(sources, out, tmp_dir, split_pages, titles, collection_name, organizer, cover_config, intro, progress, editnote)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)   # 无论成功/异常都清除


def _merge_pdfs_bare(sources, out, split_pages, titles, progress=None):
    # 关闭封面/封底：直接拼接原文件，不做任何处理，仅生成书签；
    # 原书自带书签降一级，归入对应书的书签下
    try:
        import pymupdf
    except ImportError:
        import pymupdf as fitz
    out.parent.mkdir(parents=True, exist_ok=True)
    merged=pymupdf.open()
    parts=[]; cur_pages=0; part_idx=1; toc_entries=[]
    def _flush():
        nonlocal merged, cur_pages, part_idx, toc_entries
        if len(merged)>0:
            if toc_entries:
                merged.set_toc(toc_entries)
            part=out if not parts else out.parent/f"{out.stem}_part{part_idx}.pdf"
            merged.save(part)
            parts.append(part)
            merged=pymupdf.open()
            cur_pages=0
            toc_entries=[]
            part_idx+=1
    bi=0
    total=len([s for s in sources if s.exists()])
    for s in sources:
        if not s.exists():
            continue
        doc=pymupdf.open(s)
        if split_pages and cur_pages+len(doc)>split_pages and cur_pages>0:
            _flush()
        label=(titles[bi] if titles and bi<len(titles) else Path(s).stem)
        if progress and not progress(bi, total, f"{label}（{Path(s).name}）"):
            raise MergeCancelled()
        toc_entries.append([1, label, cur_pages+1, BOOKMARK_TOP_MARGIN])
        try:
            src_toc=doc.get_toc() or []
        except Exception:
            src_toc=[]
        for lvl, t, p in src_toc:
            if isinstance(p, int) and 1<=p<=len(doc):
                toc_entries.append([min(int(lvl)+1, 6), t, cur_pages+p, BOOKMARK_TOP_MARGIN])
        merged.insert_pdf(doc)
        cur_pages+=len(doc)
        bi+=1
    _flush()
    return parts


def _merge_pdfs_impl(sources, out, tmp_dir, split_pages, titles, collection_name, organizer, cover_config, intro=None, progress=None, editnote=None):
    try:
        import pymupdf
    except ImportError:
        import pymupdf as fitz
    cfg=cover_config or {}
    mode=cfg.get("mode","print")
    pad=(mode=="print")   # 打印=补空白；阅读=去空白
    first=sources[0]
    _resolved_imgs={}
    def _resolved_img(key):
        if key not in _resolved_imgs:
            _resolved_imgs[key]=resolve_cover_image(cfg.get("images",{}), key)
        return _resolved_imgs[key]
    def _blank(name):
        b=tmp_dir/name
        _blank_pdf(first, b)
        return b
    def _img_ok(key):
        p=_resolved_img(key)
        return p is not None and p.is_file()
    def _img_pdf(key, name):
        w=tmp_dir/name
        _image_pdf(first, _resolved_img(key), w)
        return w
    def _pdf_pages(path):
        # 前置文件真实页数（多页的编辑说明/说明/目录不能按“1 文件=1 页”算）
        try:
            with pymupdf.open(path) as _d:
                return len(_d)
        except Exception:
            return 0
    def _front_pages():
        return sum(_pdf_pages(p) for p in front)
    name=collection_name or out.stem
    cover=tmp_dir/"cover.pdf"
    _cover_pdf(first, name, cover, organizer=organizer, config=cfg)
    # ---- 前置页（目录之前）：封面[→空白][→封面图[→空白]] ----
    front=[cover]
    if pad:
        front.append(_blank("blank_cover.pdf"))
    if _img_ok("buddha"):
        front.append(_img_pdf("buddha", "img_buddha.pdf"))
        if pad:
            front.append(_blank("blank_buddha.pdf"))
    # ---- 编辑说明（TXT 转排版）：说明页之前；可多页（全局 + 丛书特定）----
    _en_items=[]   # [(front 起始索引, 标题)]
    for _eni, _en in enumerate(_as_editnotes(editnote)):
        _en_start=len(front)
        _en_title=_en.get("title") or EDITNOTE_DEFAULT_TITLE
        _en_pdf=tmp_dir/f"editnote_{_eni}.pdf"
        _en_pages=_editnote_pdf(_en, first, _en_pdf, config=cfg)
        front.append(_en_pdf)
        if pad and _en_pages%2==1:
            front.append(_blank(f"blank_editnote_{_eni}.pdf"))
        _en_items.append((_en_start, _en_title))
    # ---- 说明页（部类统计 + 清单）：封面之后、目录之前 ----
    # 打印模式保证从奇数页起（前面页数为奇数时垫一张；多页前置按真实页数算）
    intro_start=None
    if intro:
        if pad and _front_pages()%2==1:
            front.append(_blank("blank_before_intro.pdf"))
        intro_start=len(front)
        intro_pdf=tmp_dir/"intro.pdf"
        intro_pages=_intro_pdf(intro, first, intro_pdf, config=cfg)
        front.append(intro_pdf)
        if pad and intro_pages%2==1:
            front.append(_blank("blank_intro.pdf"))
    toc_start=len(front)
    toc_start_page=_front_pages()+1   # 目录首页在成品中的真实页码（1-based）
    toc_titles=titles or [s.stem for s in sources]
    toc=tmp_dir/"toc.pdf"
    # 第一遍生成目录以获取页数（不影响后续页码计算）
    # toc_start_index 为 0-based 偏移（link_rects 内 toc_pg 从 1 起）
    _toc_pdf(toc_titles, first, toc, config=cfg, page_nums=None, toc_start_index=toc_start_page-1)
    toc_pages=len(pymupdf.open(toc))
    # ---- 计算正文每部真实起始页（1-based） ----
    pre_body_pages=_front_pages()+toc_pages
    if pad and toc_pages%2==1:
        pre_body_pages+=1   # 目录单数页补空白
    page_nums=[]
    off=pre_body_pages+1
    body_sources=[s for s in sources if s.exists()]
    for s in body_sources:
        with pymupdf.open(s) as doc:
            n=len(doc)
        if pad and n%2==1:
            n+=1
        page_nums.append(off)
        off+=n
    page_nums=page_nums[:len(toc_titles)]
    # 第二遍生成目录（真实页码；布局不变，页数一致）
    link_rects=_toc_pdf(toc_titles, first, toc, config=cfg, page_nums=page_nums, toc_start_index=toc_start_page-1)
    # ---- 组装页面序列 ----
    pre=list(front)
    pre.append(toc)
    if pad and toc_pages%2==1:
        pre.append(_blank("blank_toc_odd.pdf"))
    # 前置各段真实起始页（1-based）：多页的编辑说明/说明/目录逐文件累加
    _pre_pages=[_pdf_pages(p) for p in pre]
    def _pre_page(idx):
        return sum(_pre_pages[:idx])+1
    back=[]
    if _img_ok("weituo"):
        # 封底图后不再垫空白（后面已无内容）：尾部恒为 [封底图?, 封底空白]
        back.append(_img_pdf("weituo", "img_weituo.pdf"))
    if pad:
        back.append(_blank("blank_back.pdf"))   # 封底（空白，无图也保留）
    body_indices=set(range(len(pre), len(pre)+len(body_sources)))
    all_sources=pre+body_sources+back
    toc_entries=[[1, "封面", 1, BOOKMARK_TOP_MARGIN]]
    for _en_start, _en_title in _en_items:
        toc_entries.append([1, _en_title or EDITNOTE_DEFAULT_TITLE, _pre_page(_en_start), BOOKMARK_TOP_MARGIN])
    if intro_start is not None:
        toc_entries.append([1, intro.get("title","说明"), _pre_page(intro_start), BOOKMARK_TOP_MARGIN])
    toc_entries.append([1, "目录", _pre_page(toc_start), BOOKMARK_TOP_MARGIN])
    merged = pymupdf.open()
    parts=[]
    cur_pages=0
    part_idx=1
    body_i=0
    for idx, s in enumerate(all_sources):
        if not s.exists():
            continue
        doc=pymupdf.open(s)
        is_body=idx in body_indices
        if is_body and pad and len(doc)%2==1:
            doc.new_page(width=doc[0].rect.width, height=doc[0].rect.height)
        if is_body:
            ti=body_i if body_i<len(toc_titles) else None
            label=toc_titles[ti] if ti is not None else s.stem
            if progress and not progress(body_i, len(body_sources), f"{label}（{Path(s).name}）"):
                raise MergeCancelled()
            toc_entries.append([1, label, cur_pages+1, BOOKMARK_TOP_MARGIN])
            body_i+=1
        if split_pages and cur_pages + len(doc) > split_pages and cur_pages>0:
            if toc_entries:
                merged.set_toc(toc_entries)
            part = out.parent / f"{out.stem}_part{part_idx}.pdf"
            merged.save(part)
            parts.append(part)
            merged=pymupdf.open()
            cur_pages=0
            toc_entries=[]
            part_idx+=1
        merged.insert_pdf(doc)
        cur_pages+=len(doc)
    if len(merged)>0:
        if not parts and link_rects and page_nums:
            _add_toc_links(merged, link_rects, page_nums)
        if toc_entries:
            merged.set_toc(toc_entries)
        part = out if not parts else out.parent / f"{out.stem}_part{part_idx}.pdf"
        merged.save(part)
        parts.append(part)
    return parts

def _epub_editnote_page(parsed: dict, config: dict=None, idx: int=1):
    """EPUB 编辑说明页：mini-syntax 转原生标签＋内联样式。
    字号沿用封面设置（h1=toc_title 比率，h2–h5 依次缩小，正文 1.0em）。
    idx>1 时用独立文件名（editnote_2.xhtml…），支持全局 + 丛书特定多页。"""
    import html as _html
    from ebooklib import epub
    title = (parsed or {}).get("title") or EDITNOTE_DEFAULT_TITLE
    styles = ((config or {}).get("styles", {}) or {})
    sizes = ((config or {}).get("sizes", {}) or {})

    def _ratio(name, default):
        if name in styles and "ratio" in styles[name]:
            try:
                return float(styles[name]["ratio"])
            except Exception:
                return default
        return sizes.get("ratios", {}).get(name, default)
    try:
        r_t = float(_ratio("toc_title", 1.9))
    except Exception:
        r_t = 1.9
    parts = ['<html xmlns="http://www.w3.org/1999/xhtml"><head/><body>']
    parts.append(f'<h1 style="text-align:center;text-indent:0;font-size:{r_t:.2f}em;">'
                 f'{_html.escape(title)}</h1>')
    for kind, align, text in (parsed or {}).get("lines", []) or []:
        if kind == "pb":
            # EPUB 无固定页：空 break-div 尽力分页（认的阅读器另起一页，
            # 不认的零高度无残留）；不切文件，spine/toc/nav 不动
            parts.append('<div style="break-before:page;page-break-before:always;"></div>')
            continue
        # HTML 塌缩空白：行首半角空格/制表转 &#160; 保留缩进；全角空格原生保留
        _stripped = text.lstrip(" \t")
        t = "&#160;" * (len(text) - len(_stripped)) + _html.escape(_stripped)
        if kind == "gap":
            # 空行：无边距＋单倍行高，合计约一倍字高（nbsp 防阅读器吞空段）；
            # 旧 margin:0.4em 叠出一倍行高＋0.8em 边距，目测约两倍字高
            parts.append('<p style="margin:0;line-height:1.0;">&#160;</p>')
            continue
        tag = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4", "h5": "h5"}.get(kind, "p")
        if kind == "h1":
            fs = r_t
        elif kind == "h2":
            fs = r_t * 0.85
        elif kind == "h3":
            fs = r_t * 0.8
        elif kind == "h4":
            fs = r_t * 0.7
        elif kind == "h5":
            fs = r_t * 0.6
        else:
            fs = 1.0
        style = [f"font-size:{fs:.2f}em", "text-indent:0"]
        if tag == "p":
            # 正文行：收紧段间距与行高（与说明页一致），否则阅读器默认
            # p{margin:1em 0} 会让逐行成段的说明文字显得双倍行距
            style.append("margin:0.3em 0;line-height:1.2")
        else:
            # 标题行：阅读器默认边距按标题字号算（如 h1 下边距约 1.27em），
            # 紧跟的空行/正文会被撑高；显式收紧（上宽下窄，下沿与正文同节奏）
            style.append("margin:0.8em 0 0.3em")
        if align == "center":
            style.append("text-align:center")
        elif align == "right":
            style.append("text-align:right")
        inner = f"<b>{t}</b>" if kind == "b" else t
        parts.append(f'<{tag} style="{";".join(style)}">{inner}</{tag}>')
    parts.append('</body></html>')
    _fn = "editnote.xhtml" if idx <= 1 else f"editnote_{idx}.xhtml"
    c = epub.EpubHtml(title=title, file_name=_fn, lang="zh")
    c.content = "".join(parts)
    return c


def _epub_intro_page(intro: dict):
    # EPUB 说明页（部类统计 + 完整清单）：纯流式 + 内联样式，弱 CSS 阅读器友好
    import html as _html
    from ebooklib import epub
    c=epub.EpubHtml(title=intro.get("title","说明"), file_name="intro.xhtml", lang="zh")
    parts=['<html xmlns="http://www.w3.org/1999/xhtml"><head/><body>']
    parts.append(f'<h1 style="text-align:center;font-size:1.8em;">{_html.escape(intro.get("title","说明"))}</h1>')
    if intro.get("note"):
        parts.append(f'<p style="text-align:center;margin:0.2em 0 1.2em;">{_html.escape(str(intro["note"]))}</p>')
    for ln in intro.get("summary",[]) or []:
        parts.append(f'<p style="margin:0.3em 0;line-height:1.2;'
                     f'font-family:\'FangSong\',\'仿宋\',serif;">{_html.escape(ln)}</p>')
    for header, rows in intro.get("sections",[]) or []:
        # 部类/刊本信息：含路径（" / "）时每段一行；字体字号沿用目录条目
        parts.append('<div style="margin-top:1.0em;">')
        for seg in [s for s in re.split(r"\s*/\s*", str(header)) if s]:
            parts.append(f'<p style="margin:0.15em 0;">{_html.escape(seg)}</p>')
        parts.append('</div>')
        parts.append('<div style="margin-left:1em;">')
        for r in rows:
            parts.append(f'<p style="margin:0.15em 0;font-size:0.95em;">{_html.escape(r)}</p>')
        parts.append('</div>')
    parts.append('</body></html>')
    c.content="".join(parts)
    return c


def _epub_cover_page(collection_name: str, organizer: str, titles: list=None, cover_config: dict=None):
    # EPUB 丛书封面页：纯流式 + 内联样式，不依赖页高类 CSS，
    # ebooklib 只重建 <head>，正文元素的内联 style 会原样保留，弱 CSS 阅读器也不会重叠。
    # E2：字号取 styles[*].ratio（base=1em）、颜色取 styles[*].color；边距/位置仍用固定 em。
    from ebooklib import epub
    cfg=cover_config or {}
    styles=cfg.get("styles",{}) or {}
    def _ratio(name, default):
        s=styles.get(name)
        if isinstance(s, dict) and "ratio" in s:
            try:
                return float(s["ratio"])
            except Exception:
                return default
        return default
    def _color(name, default):
        s=styles.get(name)
        if isinstance(s, dict) and s.get("color"):
            c=s["color"]
            try:
                return "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))
            except Exception:
                return default
        return default
    r_cb=_ratio("cbeta", 1.0)
    r_title=_ratio("title", 3.0)
    r_date=_ratio("date", 1.0)
    r_org=r_date   # 整理者字号与日期一致
    col_cb=_color("cbeta", "#333333")
    col_title=_color("title", "#000000")
    col_org=_color("organizer", "#333333")
    col_date=_color("date", "#666666")
    c=epub.EpubHtml(title="封面", file_name="cover.xhtml", lang="zh")
    import html as _html
    _date_text=_resolve_cover_date(cfg)
    date=_date_text
    org=organizer or ""
    topleft=_html.escape(cfg.get("imprint", "CBETA 電子佛典自選叢書") or "")
    _cn=str(collection_name or "")
    _cp=_cn.split("｜")
    _cmain=_cp[0] if _cp else ""
    _cgroup=_cp[1] if len(_cp)>1 else ""
    _group_html="".join(
        f'<p style="font-size:1em;margin:0.2em 0;color:{col_title};">{_html.escape(x)}</p>'
        for x in re.split(r"\s*/\s*", _cgroup) if x)
    c.content=(
        '<html xmlns="http://www.w3.org/1999/xhtml"><head/><body>'
        '<div style="text-align:center;">'
        f'<p style="text-align:left;font-size:{r_cb}em;color:{col_cb};">{topleft}</p>'
        f'<h1 style="font-size:{r_title}em;line-height:1.5;margin-top:1.5em;color:{col_title};">{_html.escape(_cmain)}</h1>'
        + _group_html +
        f'<p style="font-size:{r_org}em;margin-top:19em;color:{col_org};">{org}</p>'
        + (f'<p style="font-size:{r_date}em;color:{col_date};">{_html.escape(date)}</p>' if date else '') +
        '</div></body></html>'
    )
    return c


# 共享样式：目录 / 每本封面图（丛书封面自包含内联样式，不再依赖此前缀）
_EPUB_CSS = (
    b"html,body{margin:0;padding:0;height:100%;}"
    b".cover{height:100%;margin:0;padding:0;display:flex;"
    b"align-items:center;justify-content:center;}"
    b".cover img{width:100%;height:100%;object-fit:contain;}"
    b"nav{text-align:center;}"
    b"nav ol,nav ul{display:inline-block;text-align:left;margin-top:3em;margin-left:2em;}"
    b"nav a{text-decoration:none;font-weight:bold;}"
    b"nav li{margin-bottom:0.6em;}"
)


def _prefix_href(href, stem):
    if not href or "://" in href or href.startswith(("mailto:", "#", "/")):
        return href
    return f"{stem}/{href}"


def _convert_toc(toc_items, stem):
    # 原书目录 href 加书前缀、补 uid（NCX 嵌套条目要求 uid 非空唯一）
    import re
    from ebooklib import epub
    seq=[0]
    def _uid(raw):
        seq[0]+=1
        return f"{stem}_{seq[0]}_{re.sub(r'[^A-Za-z0-9_-]+', '_', raw or 'x')}"
    def _conv(x):
        if isinstance(x, epub.Link):
            return epub.Link(_prefix_href(x.href, stem), x.title, _uid(x.uid or x.href or x.title))
        if isinstance(x, epub.EpubHtml):
            return epub.Link(_prefix_href(x.file_name, stem), x.title or x.get_id(), _uid(x.get_id()))
        if isinstance(x, epub.Section):
            return epub.Section(x.title, href=_prefix_href(x.href, stem))
        return x
    def _walk(items):
        out=[]
        for x in items or []:
            if isinstance(x, (tuple, list)):
                out.append((_conv(x[0]), _walk(x[1] if len(x)>1 else [])))
            else:
                out.append(_conv(x))
        return out
    return _walk(toc_items)


def _merge_epubs_bare(sources, out, split_items, titles, collection_name, progress=None):
    # 关闭封面/封底：纯拼接，不删除不增加任何内容页；
    # 各书条目原样保留（含自带目录/前言/后记/封面页），spine 按原书顺序直接串联；
    # 书签（侧边栏，不占页面）：每书一条，原书目录降一级归入其下
    import ebooklib
    from ebooklib import epub
    DOC_TYPE=ebooklib.ITEM_DOCUMENT
    out.parent.mkdir(parents=True, exist_ok=True)
    books=[]   # [stem, title, ordered_items, nested_toc, first_doc]
    for si, s in enumerate(sources):
        if not s.exists():
            continue
        try:
            b=epub.read_epub(str(s))
        except Exception as e:
            print(f"epub read {s} fail {e}")
            continue
        stem=Path(s).stem
        order=[]
        for sp in b.spine:
            sid=(sp[0] if isinstance(sp, tuple) else sp)
            sid=getattr(sid, "get_id", lambda: sid)()
            order.append(str(sid))
        def _key(it):
            iid=it.get_id()
            return order.index(iid) if iid in order else 999
        # 仅跳过 ncx 元数据文件（非内容页）；其余全部保留
        items=sorted([it for it in b.get_items() if it.get_type()!=ebooklib.ITEM_NAVIGATION], key=_key)
        ordered=[]
        for it in items:
            nid=it.get_id()
            it.id=f"{stem}_{nid}"
            it.file_name=f"{stem}/{it.get_name()}"
            ordered.append(it)
        docs=[it for it in ordered if it.get_type()==DOC_TYPE]
        if not docs:
            continue
        wtitle=(titles[si] if titles and si<len(titles) else stem)
        books.append([stem, wtitle, ordered, _convert_toc(b.toc, stem), docs[0]])
    if not books:
        return []

    state={"done": 0}
    total_books=len(books)

    def build_part(chunk, part_out):
        merged=epub.EpubBook()
        merged.set_identifier(str(part_out))
        merged.set_title(collection_name or out.stem)
        merged.set_language("zh")
        toc=[]
        docs_spine=[]
        for stem, wtitle, ordered, nested, first_doc in chunk:
            state["done"]+=1
            if progress and not progress(state["done"], total_books, f"{wtitle}（{stem}.epub）"):
                raise MergeCancelled()
            for it in ordered:
                merged.add_item(it)
                if it.get_type()==DOC_TYPE:
                    docs_spine.append(it)
            toc.append((epub.Link(first_doc.file_name,
                                  _epub_seq_title(state["done"], total_books, wtitle),
                                  first_doc.id), nested))
        merged.add_item(epub.EpubNcx())
        merged.add_item(epub.EpubNav())
        merged.toc=tuple(toc)
        merged.spine=docs_spine
        epub.write_epub(str(part_out), merged)

    parts=[]
    total=sum(len([1 for it in ordered if it.get_type()==DOC_TYPE]) for _,_,ordered,_,_ in books)
    if total>split_items and split_items>0:
        def _ndocs(d):
            return len([1 for it in d[2] if it.get_type()==DOC_TYPE])
        idx=1
        cur=[]; cnt=0
        for d in books:
            if cnt and cnt+_ndocs(d)>split_items:
                p=out.parent/f"{out.stem}_part{idx}.epub"
                build_part(cur, p); parts.append(p); idx+=1; cur=[]; cnt=0
            cur.append(d); cnt+=_ndocs(d)
        if cur:
            p=out if not parts else out.parent/f"{out.stem}_part{idx}.epub"
            build_part(cur, p); parts.append(p)
    else:
        build_part(books, out)
        parts=[out]
    return parts


def merge_epubs(sources: list[Path], out: Path, split_items: int = 500,
                collection_name: str=None, organizer: str="", titles: list=None,
                cover_config: dict=None, intro: dict=None, progress=None, editnote: dict=None) -> list[Path]:
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        print("ebooklib not installed, stub")
        return []
    DOC_TYPE=ebooklib.ITEM_DOCUMENT
    NAV_TYPE=ebooklib.ITEM_NAVIGATION
    out.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.rmtree(out.parent / "_tmp_cover", ignore_errors=True)   # 清理 PDF 合成残留
    name=collection_name or out.stem
    if not (cover_config or {}).get("enabled", True):
        return _merge_epubs_bare(sources, out, split_items, titles, name, progress)
    # 排除每本自带的「目录/导航」；封面 titlepage、样式资源保留
    # front(编辑说明) 只保留第一本、back(后记) 只保留最后一本
    EXCLUDE={"toc","nav","ncx"}
    books=[]   # [[stem, title, ordered, first_doc, front_item, back_item, cover_rel]]
    for si, s in enumerate(sources):
        if not s.exists():
            continue
        try:
            b=epub.read_epub(str(s))
        except Exception as e:
            print(f"epub read {s} fail {e}")
            continue
        stem=s.stem
        # 原书 spine 顺序
        order=[]
        for sp in b.spine:
            sid=(sp[0] if isinstance(sp, tuple) else sp)
            sid=getattr(sid, "get_id", lambda: sid)()
            order.append(str(sid))
        def _key(it):
            iid=it.get_id()
            return order.index(iid) if iid in order else 999
        items=sorted([it for it in b.get_items() if it.get_type()!=NAV_TYPE], key=_key)
        ordered=[]
        first_doc=None
        front_item=None
        back_item=None
        for it in items:
            nid=it.get_id()
            base=Path(it.get_name()).stem
            if nid in EXCLUDE or base in EXCLUDE:
                continue
            # 唯一化 id / 文件名（统一加前缀，保持书内相对路径 ../cbeta.css、images/cover.jpg 有效）
            it.id=f"{stem}_{nid}"
            it.file_name=f"{stem}/{it.get_name()}"
            ordered.append(it)
            if base=="front":
                front_item=it
            elif base=="back":
                back_item=it
            if first_doc is None and it.get_type()==DOC_TYPE:
                first_doc=it
        if not ordered or first_doc is None:
            continue
        # ebooklib 读取会丢失 <head> 内样式链接：按书内相对路径用 add_link 重新挂上
        import os
        css_items=[it for it in ordered if it.get_type()==ebooklib.ITEM_STYLE or (it.media_type=="text/css")]
        for it in ordered:
            if it.get_type()!=DOC_TYPE:
                continue
            for css in css_items:
                rel=os.path.relpath(css.file_name, os.path.dirname(it.file_name) or ".").replace("\\","/")
                if not hasattr(it, "add_link"):
                    break
                it.add_link(href=rel, rel="stylesheet", type="text/css")
                break
        # 封面页改为铺满并居中的图片（配合 build 时的 cover.css）
        imgs=[it for it in ordered if it.get_type()==ebooklib.ITEM_IMAGE]
        cover_img=next((im for im in imgs if "cover" in im.get_name().lower()), (imgs[0] if imgs else None))
        cover_rel=""
        for it in ordered:
            if it.get_type()==DOC_TYPE and Path(it.get_name()).stem=="titlepage" and cover_img is not None:
                cover_rel=os.path.relpath(cover_img.file_name, os.path.dirname(it.file_name) or ".").replace("\\","/")
                it.title=""
                it.set_content(('<html><head/><body>'
                                f'<div class="cover"><img src="{cover_rel}" alt=""/></div>'
                                '</body></html>').encode("utf-8"))
        wtitle=(titles[si] if titles and si<len(titles) else stem)
        books.append([stem, wtitle, ordered, first_doc, front_item, back_item, cover_rel])

    if not books:
        return []
    # 编辑说明只留第一本，后记只留最后一本
    first_front=next((b[4] for b in books if b[4] is not None), None)
    last_back=next((b[5] for b in reversed(books) if b[5] is not None), None)
    for entry in books:
        for it in list(entry[2]):
            base=Path(it.get_name()).stem
            if base=="front" and it is not first_front:
                entry[2].remove(it)
            elif base=="back" and it is not last_back:
                entry[2].remove(it)

    state={"done": 0}
    total_books=len(books)
    _en_first=[True]   # 编辑说明只进第一个合并文件

    def build_part(chunk, part_out):
        _ens = _as_editnotes(editnote) if _en_first[0] else []
        _en_first[0]=False
        merged=epub.EpubBook()
        merged.set_identifier(str(part_out))
        merged.set_title(name)
        merged.set_language("zh")
        merged.add_metadata("DC", "creator", organizer or "CBETA")
        merged.add_metadata("DC", "publisher", "CBETA")
        cover=_epub_cover_page(name, organizer, cover_config=cover_config)
        merged.add_item(cover)
        en_pages=[]
        for _eni, _en in enumerate(_ens, 1):
            _pg=_epub_editnote_page(_en, cover_config, idx=_eni)
            merged.add_item(_pg)
            en_pages.append(_pg)
        intro_page=None
        if intro:
            intro_page=_epub_intro_page(intro)
            merged.add_item(intro_page)
        # 共享样式（目录 / 每本封面图；丛书封面自包含，不挂此外链）
        cover_css=epub.EpubItem(uid="cover_css", file_name="cover.css",
                                media_type="text/css", content=_EPUB_CSS)
        merged.add_item(cover_css)
        toc=[]
        docs_spine=[]
        for stem, wtitle, ordered, first_doc, _front, _back, cover_rel in chunk:
            state["done"]+=1
            if progress and not progress(state["done"], total_books, f"{wtitle}（{stem}.epub）"):
                raise MergeCancelled()
            for it in ordered:
                merged.add_item(it)
                if it.get_type()==DOC_TYPE:
                    docs_spine.append(it)
                    if cover_rel and Path(it.get_name()).stem=="titlepage":
                        rel=os.path.relpath("cover.css", os.path.dirname(it.file_name) or ".").replace("\\","/")
                        it.add_link(href=rel, rel="stylesheet", type="text/css")
            toc.append(epub.Link(first_doc.file_name,
                                  _epub_seq_title(state["done"], total_books, wtitle),
                                  first_doc.id))
        merged.add_item(epub.EpubNcx())
        nav=epub.EpubNav(title="丛书目录")
        nav.add_link(href="cover.css", rel="stylesheet", type="text/css")
        merged.add_item(nav)
        if intro_page is not None:
            toc.insert(0, epub.Link("intro.xhtml", intro.get("title","说明"), "intro"))
        # 编辑说明可多页（全局 + 丛书特定）：按顺序插在目录最前（封面之前）
        for _eni, _en in enumerate(reversed(list(enumerate(_ens, 1)))):
            _idx, _note = _en
            _fn = "editnote.xhtml" if _idx <= 1 else f"editnote_{_idx}.xhtml"
            toc.insert(0, epub.Link(_fn,
                                    _note.get("title") or EDITNOTE_DEFAULT_TITLE,
                                    f"editnote{_idx}"))
        toc.insert(0, epub.Link("nav.xhtml", "丛书目录", "nav"))
        toc.insert(0, epub.Link("cover.xhtml", "封面", "cover"))
        merged.toc=tuple(toc)
        # 封面→[编辑说明→]说明→丛书目录→各书(封面页+正文)；nav 紧随封面，避免目录落在最后
        spine=[cover]
        spine.extend(en_pages)
        if intro_page is not None:
            spine.append(intro_page)
        merged.spine=spine+["nav"]+docs_spine
        epub.write_epub(str(part_out), merged)

    parts=[]
    total=sum(len([1 for it in ordered if it.get_type()==DOC_TYPE]) for _,_,ordered,_,_,_,_ in books)
    if total>split_items and split_items>0:
        def _ndocs(d):
            return len([1 for it in d[2] if it.get_type()==DOC_TYPE])
        idx=1
        cur=[]; cnt=0
        for d in books:
            if cnt and cnt+_ndocs(d)>split_items:
                p=out.parent/f"{out.stem}_part{idx}.epub"
                build_part(cur, p); parts.append(p); idx+=1; cur=[]; cnt=0
            cur.append(d); cnt+=_ndocs(d)
        if cur:
            p=out if not parts else out.parent/f"{out.stem}_part{idx}.epub"
            build_part(cur, p); parts.append(p)
    else:
        build_part(books, out)
        parts=[out]
    return parts
