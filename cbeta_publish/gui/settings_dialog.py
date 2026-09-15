# -*- coding: utf-8 -*-
"""统一设置对话框：数据目录 / 封面版式（含背景色、图像）/ 外观。"""
import json, shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QLabel, QFileDialog, QColorDialog, QMessageBox, QDialogButtonBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QApplication,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "app.json"
BACKUP_DIR = PROJECT_ROOT / "mulu" / "backup"
IMAGES_DIR = PROJECT_ROOT / "assets" / "images"
DEFAULT_IMAGES_DIR = IMAGES_DIR / "default"

DEFAULT_CONFIG = {
    "book_dir": str(PROJECT_ROOT / "cbeta_xml"),
    "official_ebooks_dir": str(PROJECT_ROOT / "cbeta_ebooks"),
    "mulu_dir": str(PROJECT_ROOT / "mulu"),
    "collections_dir": str(PROJECT_ROOT / "collections"),
    "theme": {"mode": "system", "accent": "#8B4513"},
    "language": "zh-Hans",
    "update_interval": "weekly",
    "local_xml_root": "E:/CBETA/CBReader2X/Bookcase/CBETA/XML",
    "output_dir": "my_books",
    "ui": {"tree_expand": {"mode": "depth", "depth": 2},
           "app_font": "Microsoft YaHei", "app_font_size": 9,
           "supplement_ttf": "E:/dev/cbeta/xml2pdf/cbeta/CBETA 補充字型/CBETASupplement.ttf"},
    "default_source": "official",
    "pdf": {"split_pages": 5000},
    "epub": {"split_items": 500},
    "merge": {"by_volume": False},
    "xml2pdf": {"path": "E:/dev/cbeta/xml2pdf", "page": "a4", "font_lang": "zh-Hant", "engine": "docx2pdf", "vertical": False},
    "catalog": {"filters": {"tripitaka": {"hidden": []}, "dynasty": {"hidden": []}, "vol": {"hidden": []}}},
    "cover": {
        "organizer": "CBETA 整理",
        "imprint": "CBETA 電子佛典自選叢書",
        "mode": "print",
        "enabled": True,
        "intro": {"enabled": True, "title": "说明", "list": True},
        "images": {
            "buddha": {"file": "assets/images/buddha.jpg", "enabled": True},
            "weituo": {"file": "assets/images/weituo.jpg", "enabled": True},
        },
        "sizes": {
            "body_a5": 10, "body_a4": 12, "body_16k": 11, "body_32k": 9,
            "margins": {
                "a5": {"left": 36, "right": 36, "top": 40, "bottom": 40},
                "a4": {"left": 48, "right": 48, "top": 48, "bottom": 48},
                "16k": {"left": 42, "right": 42, "top": 44, "bottom": 44},
                "32k": {"left": 32, "right": 32, "top": 36, "bottom": 36},
            },
            "margin_ratio": {"left": 0.07, "right": 0.07, "top": 0.05, "bottom": 0.05},
        },
        "styles": {
            "title": {"font": "C:/Windows/Fonts\\Source Han Serif SC Heavy (TrueType).ttf", "color": [0, 0, 0], "ratio": 3.0},
            "organizer": {"font": "C:/Windows/Fonts\\Source Han Serif SC Heavy (TrueType).ttf", "color": [51, 51, 51], "ratio": 1.35},
            "date": {"font": "C:/Windows/Fonts\\simhei.ttf", "color": [100, 100, 100], "ratio": 1.0},
            "toc_title": {"font": "C:/Windows/Fonts\\Source Han Serif SC Heavy (TrueType).ttf", "color": [0, 0, 0], "ratio": 2.0},
            "toc_item": {"font": "C:/Windows/Fonts\\simhei.ttf", "color": [30, 30, 30], "delta": 2},
            "toc_page": {"font": "C:/Windows/Fonts\\simhei.ttf", "color": [100, 100, 100], "ratio": 1.0},
            "background": {"color": [250, 245, 230]},
        },
        "positions": {
            "cbeta_left_mm": 18, "cbeta_top_mm": 12,
            "title_y_ratio": 0.30, "organizer_y_ratio": 0.84, "date_y_ratio": 0.89,
            "toc_y_ratio": 0.15, "toc_item_y_ratio": 0.25,
        },
    },
}


def _ensure_original_backup():
    """首次启动/首次保存前：建立出厂原始配置备份（mulu/backup/original）。"""
    if not CONFIG_PATH.exists():
        return
    orig_dir = BACKUP_DIR / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)
    target = orig_dir / "app.json"
    if not target.exists():
        shutil.copy2(str(CONFIG_PATH), str(target))


def _backup_last():
    """保存前：当前配置快照到 mulu/backup/last。"""
    if not CONFIG_PATH.exists():
        return
    last_dir = BACKUP_DIR / "last"
    last_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(CONFIG_PATH), str(last_dir / "app.json"))


class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(680, 560)
        self._cfg = json.loads(json.dumps(config))  # 深拷贝
        self._cfg_path = CONFIG_PATH

        v = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._tab_filters(), "目录过滤")
        tabs.addTab(self._tab_dirs(), "数据/输出")
        tabs.addTab(self._tab_cover(), "封面/版式")
        tabs.addTab(self._tab_cache(), "缓存")
        tabs.addTab(self._tab_update(), "更新源")
        tabs.addTab(self._tab_appearance(), "外观")
        v.addWidget(tabs)
        self._sync_from_cfg()

        btns = QDialogButtonBox()
        self._btn_apply = btns.addButton("确定", QDialogButtonBox.ApplyRole)
        self._btn_save = btns.addButton("保存", QDialogButtonBox.AcceptRole)
        self._btn_default = btns.addButton("恢复默认", QDialogButtonBox.ResetRole)
        self._btn_original = btns.addButton("恢复原始", QDialogButtonBox.ResetRole)
        self._btn_cancel = btns.addButton("取消", QDialogButtonBox.RejectRole)
        self._btn_apply.setToolTip("不保存到 config/app.json，仅本次运行生效")
        self._btn_apply.clicked.connect(self._apply)
        self._btn_save.clicked.connect(self._save)
        self._btn_default.clicked.connect(self._restore_default)
        self._btn_original.clicked.connect(self._restore_original)
        self._btn_cancel.clicked.connect(self.reject)
        v.addWidget(btns)

    def _no_wheel_until_focused(self, widget):
        widget.setFocusPolicy(Qt.StrongFocus)
        widget.installEventFilter(self)
        return widget

    def eventFilter(self, obj, event):
        if isinstance(obj, (QSpinBox, QDoubleSpinBox, QComboBox)) and event.type() == QEvent.Type.Wheel:
            if not obj.hasFocus():
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    # ---------- 页签：数据/输出 ----------
    def _tab_dirs(self):
        w = QWidget()
        form = QFormLayout(w)
        self.ed_mulu = QLineEdit(self._cfg.get("mulu_dir", ""))
        self.ed_collections = QLineEdit(self._cfg.get("collections_dir", ""))
        self.ed_book = QLineEdit(self._cfg.get("book_dir", ""))
        self.ed_ebooks = QLineEdit(self._cfg.get("official_ebooks_dir", ""))
        self.ed_xmlroot = QLineEdit(self._cfg.get("local_xml_root", ""))
        self.ed_output = QLineEdit(self._cfg.get("output_dir", "my_books"))
        self.cb_interval = self._no_wheel_until_focused(QComboBox())
        self.cb_interval.addItems(["daily", "weekly", "monthly", "manual"])
        cur = self._cfg.get("update_interval", "weekly")
        if cur in ["daily", "weekly", "monthly", "manual"]:
            self.cb_interval.setCurrentText(cur)
        form.addRow("目录数据", self.ed_mulu)
        form.addRow("丛书数据", self.ed_collections)
        form.addRow("XML 缓存", self.ed_book)
        form.addRow("官方电子书", self.ed_ebooks)
        form.addRow("本地 CBReader XML", self.ed_xmlroot)
        form.addRow("输出目录", self.ed_output)
        form.addRow("更新频率", self.cb_interval)
        # 链路 B
        self.cb_default_source = self._no_wheel_until_focused(QComboBox())
        self.cb_default_source.addItems(["official", "xml"])
        self.ed_x2p = QLineEdit(self._cfg.get("xml2pdf", {}).get("path", ""))
        self.cb_x2p_page = self._no_wheel_until_focused(QComboBox())
        self.cb_x2p_page.addItems(["a4", "a5", "16k", "32k", "book", "letter"])
        self.cb_x2p_font = self._no_wheel_until_focused(QComboBox())
        self.cb_x2p_font.addItems(["zh-Hant", "zh-Hans"])
        self.ed_x2p_engine = QLineEdit(self._cfg.get("xml2pdf", {}).get("engine", "docx2pdf"))
        self.chk_x2p_v = QCheckBox("竖排")
        form.addRow("默认来源（新建丛书）", self.cb_default_source)
        form.addRow("xml2pdf 路径", self.ed_x2p)
        form.addRow("链路B 纸张", self.cb_x2p_page)
        form.addRow("链路B 字库语言", self.cb_x2p_font)
        form.addRow("链路B 引擎", self.ed_x2p_engine)
        form.addRow("链路B", self.chk_x2p_v)
        hint = QLabel("链路B：丛书来源选 xml 时，用 cbeta_xml 经 xml2pdf 生成后再合并（见 docs/链路B-设计契约.md）。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow(hint)
        # 分册：0=不分册
        split_box = QGroupBox("分册（0=不分册）")
        split_form = QFormLayout(split_box)
        self.sp_split_pdf = self._no_wheel_until_focused(QSpinBox())
        self.sp_split_pdf.setRange(0, 99999)
        self.sp_split_pdf.setValue(int((self._cfg.get("pdf", {}) or {}).get("split_pages", 5000) or 0))
        split_form.addRow("PDF 分册页数", self.sp_split_pdf)
        self.sp_split_epub = self._no_wheel_until_focused(QSpinBox())
        self.sp_split_epub.setRange(0, 99999)
        self.sp_split_epub.setValue(int((self._cfg.get("epub", {}) or {}).get("split_items", 500) or 0))
        split_form.addRow("EPUB 分册文档数", self.sp_split_epub)
        form.addRow(split_box)
        # 按册分册：来自 mulu/vol.json 的册（原书分卷）归属
        self.chk_by_volume = QCheckBox("按册分册（按原书分卷各一个文件，如 法藏/制藏/論藏/雜藏）")
        self.chk_by_volume.setChecked(bool((self._cfg.get("merge", {}) or {}).get("by_volume", False)))
        form.addRow(self.chk_by_volume)
        return w

    @staticmethod
    def _migrate_series_imprint(cover: dict):
        # 系列名/左上角文字二合一：旧 cover.series 非空则一次性并入 imprint
        if isinstance(cover, dict) and cover.get("series"):
            cover["imprint"] = cover.pop("series")
        elif isinstance(cover, dict):
            cover.pop("series", None)

    # ---------- 页签：封面/版式 ----------
    def _tab_cover(self):
        w = QWidget()
        form = QFormLayout(w)
        self._cover_form = form
        cover = self._cfg.setdefault("cover", {})
        self._migrate_series_imprint(cover)
        # 整理者 + 模式 + 左上角系列名
        self.ed_organizer = QLineEdit(cover.get("organizer", "CBETA 整理"))
        self.ed_imprint = QLineEdit(cover.get("imprint", "CBETA 電子佛典自選叢書"))
        self.ed_imprint.setToolTip("封面左上角文字；可填系列名（如太虛大師全書）或落款；留空则不绘制")
        self.cb_mode = self._no_wheel_until_focused(QComboBox())
        self.cb_mode.addItems(["print", "reading"])
        self.cb_mode.setCurrentText(cover.get("mode", "print"))
        form.addRow("整理者署名", self.ed_organizer)
        form.addRow("左上角系列名", self.ed_imprint)
        form.addRow("发布模式", self.cb_mode)
        form.addRow(QLabel("打印=补空白页（封面/佛像/目录/正文/韦陀/封底）；阅读=去空白"))
        self.chk_cover_enabled = QCheckBox("合并时使用封面/封底页")
        self.chk_cover_enabled.setChecked(bool(cover.get("enabled", True)))
        form.addRow(self.chk_cover_enabled)
        hint_cover = QLabel("关闭后直接拼接原文件，仅生成书签（原书书签降一级归入对应书下）。")
        hint_cover.setStyleSheet("color: gray;")
        form.addRow(hint_cover)
        # 说明页（部类统计 + 完整清单，自动从书单推导；仅封面模式生效）
        intro = cover.setdefault("intro", {"enabled": True, "title": "说明", "list": True})
        self.chk_intro_enabled = QCheckBox("插入说明页（部类统计 + 完整清单）")
        self.chk_intro_enabled.setChecked(bool(intro.get("enabled", True)))
        form.addRow(self.chk_intro_enabled)
        self.ed_intro_title = QLineEdit(intro.get("title", "说明"))
        form.addRow("说明页标题", self.ed_intro_title)
        hint_intro = QLabel("部类统计与清单自动从丛书书单推导；仅在「合并时使用封面/封底页」开启时插入。")
        hint_intro.setStyleSheet("color: gray;")
        form.addRow(hint_intro)
        # 封面页基准字号（纸张联动基准）
        sizes = cover.setdefault("sizes", {})
        self.sp_body = {}
        for paper in ["a5", "a4", "16k", "32k"]:
            self.sp_body[paper] = self._no_wheel_until_focused(QSpinBox())
            self.sp_body[paper].setRange(6, 40)
            self.sp_body[paper].setValue(int(sizes.get(f"body_{paper}", {"a5":10,"a4":12,"16k":11,"32k":9}[paper])))
            form.addRow(f"封面页基准字号（{paper}）", self.sp_body[paper])
        # 封面背景色
        styles = cover.setdefault("styles", {})
        bg = styles.setdefault("background", {"color": [250, 245, 230]})
        self._bg_color = QColor(*bg.get("color", [250, 245, 230]))
        self.btn_bg = QPushButton()
        self.btn_bg.setFixedWidth(80)
        self._refresh_bg_btn()
        self.btn_bg.clicked.connect(self._pick_bg)
        form.addRow("封面背景色", self.btn_bg)
        # 字体（封面/目录/说明页）：styles.<key>.font
        font_box = QGroupBox("字体（封面/目录/说明页）")
        font_form = QFormLayout(font_box)
        self.font_rows = {}
        font_labels = [
            ("cbeta", "左上角文字"), ("title", "封面标题"), ("organizer", "整理者"),
            ("date", "日期"), ("toc_title", "目录/说明标题"),
            ("toc_item", "目录/说明条目"), ("toc_page", "目录页码"),
        ]
        for key, label in font_labels:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            ed = QLineEdit(self._slash(styles.get(key, {}).get("font", "")))
            ed.setReadOnly(True)
            ed.setToolTip("缺繁体字形时按顺序回退到系统全字库（黑体simhei → 微软雅黑msyh → 宋体simsun）")
            btn = QPushButton("浏览…")
            btn.clicked.connect(lambda _, k=key, e=ed: self._pick_font(k, e))
            h.addWidget(ed, 1); h.addWidget(btn)
            self.font_rows[key] = ed
            font_form.addRow(label, row)
        form.addRow(font_box)
        # 每纸张边距(pt)：封面/目录/说明页统一以边距为准
        margins = sizes.setdefault("margins", {})
        mg_box = QGroupBox("每纸张边距(pt)")
        mg_grid = QGridLayout(mg_box)
        for col, name in enumerate(["纸张", "左", "右", "上", "下"]):
            mg_grid.addWidget(QLabel(name), 0, col)
        default_margins = {
            "a5": {"left":36,"right":36,"top":40,"bottom":40},
            "a4": {"left":48,"right":48,"top":48,"bottom":48},
            "16k": {"left":42,"right":42,"top":44,"bottom":44},
            "32k": {"left":32,"right":32,"top":36,"bottom":36},
        }
        self.sp_margins = {}
        for row, paper in enumerate(["a5", "a4", "16k", "32k"], start=1):
            mg_grid.addWidget(QLabel(paper), row, 0)
            self.sp_margins[paper] = {}
            cur = margins.get(paper, {}) if isinstance(margins.get(paper), dict) else {}
            for col, side in enumerate(["left", "right", "top", "bottom"], start=1):
                sp = self._no_wheel_until_focused(QSpinBox())
                sp.setRange(0, 200)
                sp.setValue(int(cur.get(side, default_margins[paper][side])))
                self.sp_margins[paper][side] = sp
                mg_grid.addWidget(sp, row, col)
        form.addRow(mg_box)
        hint_mg = QLabel("封面文本、目录、说明页均以该边距为界（未配置纸张时回退到内部默认）。")
        hint_mg.setStyleSheet("color: gray;")
        form.addRow(hint_mg)
        # 图像（佛像/韦陀）
        images = cover.setdefault("images", {
            "buddha": {"file": "assets/images/buddha.jpg", "enabled": True},
            "weituo": {"file": "assets/images/weituo.jpg", "enabled": True},
        })
        self.img_rows = {}
        for key, label in [("buddha", "佛像"), ("weituo", "韦陀菩萨像")]:
            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(0, 0, 0, 0)
            chk = QCheckBox("启用")
            info = images.setdefault(key, {"file": "", "enabled": True})
            chk.setChecked(bool(info.get("enabled", True)))
            ed = QLineEdit(info.get("file", ""))
            ed.setReadOnly(True)
            btn = QPushButton("浏览…")
            btn.clicked.connect(lambda _, k=key, e=ed: self._pick_image(k, e))
            h.addWidget(chk); h.addWidget(ed, 1); h.addWidget(btn)
            self.img_rows[key] = (chk, ed)
            form.addRow(label, box)
        self.btn_reset_images = QPushButton("恢复默认图片（从 assets/images/default/）")
        self.btn_reset_images.clicked.connect(self._reset_images)
        form.addRow(self.btn_reset_images)
        hint = QLabel("关闭图像开关后，合成时不插入该图及其前后空白页。")
        hint.setStyleSheet("color: gray;")
        form.addRow(hint)
        # 面板过长：套卷动窗
        from PySide6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setWidget(w)
        return sc

    def _sync_from_cfg(self):
        """恢复默认/原始后，将 self._cfg 的值重新填充到所有控件。"""
        c = self._cfg
        self.ed_mulu.setText(c.get("mulu_dir", ""))
        self.ed_collections.setText(c.get("collections_dir", ""))
        self.ed_book.setText(c.get("book_dir", ""))
        self.ed_ebooks.setText(c.get("official_ebooks_dir", ""))
        self.ed_xmlroot.setText(c.get("local_xml_root", ""))
        self.ed_output.setText(c.get("output_dir", "my_books"))
        iv = c.get("update_interval", "weekly")
        if iv in ["daily", "weekly", "monthly", "manual"]:
            self.cb_interval.setCurrentText(iv)
        self.cb_default_source.setCurrentText(c.get("default_source", "official"))
        x2p = c.get("xml2pdf", {}) or {}
        self.ed_x2p.setText(x2p.get("path", ""))
        if x2p.get("page", "a4") in [self.cb_x2p_page.itemText(i) for i in range(self.cb_x2p_page.count())]:
            self.cb_x2p_page.setCurrentText(x2p.get("page", "a4"))
        self.cb_x2p_font.setCurrentText(x2p.get("font_lang", "zh-Hant"))
        self.ed_x2p_engine.setText(x2p.get("engine", "docx2pdf"))
        self.chk_x2p_v.setChecked(bool(x2p.get("vertical", False)))
        cover = c.setdefault("cover", {})
        self._migrate_series_imprint(cover)
        self.ed_organizer.setText(cover.get("organizer", "CBETA 整理"))
        self.ed_imprint.setText(cover.get("imprint", "CBETA 電子佛典自選叢書"))
        self.cb_mode.setCurrentText(cover.get("mode", "print"))
        self.chk_cover_enabled.setChecked(bool(cover.get("enabled", True)))
        intro = cover.setdefault("intro", {})
        self.chk_intro_enabled.setChecked(bool(intro.get("enabled", True)))
        self.ed_intro_title.setText(intro.get("title", "说明"))
        sizes = cover.setdefault("sizes", {})
        for paper, sp in self.sp_body.items():
            sp.setValue(int(sizes.get(f"body_{paper}", {"a5":10,"a4":12,"16k":11,"32k":9}[paper])))
        margins = sizes.setdefault("margins", {})
        defaults = {
            "a5": {"left":36,"right":36,"top":40,"bottom":40},
            "a4": {"left":48,"right":48,"top":48,"bottom":48},
            "16k": {"left":42,"right":42,"top":44,"bottom":44},
            "32k": {"left":32,"right":32,"top":36,"bottom":36},
        }
        for paper, sides in self.sp_margins.items():
            cur = margins.get(paper, {}) if isinstance(margins.get(paper), dict) else {}
            for side, sp in sides.items():
                sp.setValue(int(cur.get(side, defaults[paper][side])))
        styles = cover.setdefault("styles", {})
        bg = styles.setdefault("background", {"color": [250, 245, 230]})
        self._bg_color = QColor(*bg.get("color", [250, 245, 230]))
        self._refresh_bg_btn()
        images = cover.setdefault("images", {})
        for key, (chk, ed) in self.img_rows.items():
            info = images.setdefault(key, {"file": "", "enabled": True})
            chk.setChecked(bool(info.get("enabled", True)))
            ed.setText(info.get("file", ""))
        pdf_cfg = c.setdefault("pdf", {})
        self.sp_split_pdf.setValue(int(pdf_cfg.get("split_pages", 5000) or 0))
        epub_cfg = c.setdefault("epub", {})
        self.sp_split_epub.setValue(int(epub_cfg.get("split_items", 500) or 0))
        self.chk_by_volume.setChecked(bool((c.get("merge", {}) or {}).get("by_volume", False)))
        styles = cover.setdefault("styles", {})
        for key, ed in self.font_rows.items():
            ed.setText(self._slash(styles.get(key, {}).get("font", "")))
        theme = c.setdefault("theme", {"mode": "system", "accent": "#8B4513"})
        self.cb_theme.setCurrentText(theme.get("mode", "system"))
        self.ed_accent.setText(theme.get("accent", "#8B4513"))
        self.cb_lang.setCurrentText(c.get("language", "zh-Hans"))
        te = c.get("ui", {}).get("tree_expand", {}) or {}
        mode = te.get("mode", "depth")
        try:
            depth = int(te.get("depth", 2))
        except Exception:
            depth = 2
        if mode == "all":
            idx = 4
        elif mode == "none":
            idx = 0
        else:
            idx = min(3, max(1, depth))
        self.cb_tree_expand.setCurrentIndex(idx)
        ui = c.setdefault("ui", {})
        self.ed_app_font.setText(ui.get("app_font", "Microsoft YaHei"))
        self.sp_app_font_size.setValue(int(ui.get("app_font_size") or 9))
        self.ed_supplement.setText(ui.get("supplement_ttf", ""))
        self._populate_filter_lists()

    # ---------- 页签：缓存 ----------
    def _tab_cache(self):
        w = QWidget()
        form = QFormLayout(w)
        self._cache_rows = {}
        specs = [
            ("ebooks", "官方电子书缓存", lambda: self._cfg.get("official_ebooks_dir", "")),
            ("xml", "XML 缓存", lambda: self._cfg.get("book_dir", "")),
            ("convert", "输出中间文件", lambda: str(Path(self._cfg.get("output_dir", "my_books")) / "_xml_convert")),
        ]
        for key, label, getter in specs:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel("…")
            lbl.setMinimumWidth(150)
            btn = QPushButton("清理")
            btn.clicked.connect(lambda _, k=key, g=getter: self._clean_cache(k, g()))
            h.addWidget(lbl, 1); h.addWidget(btn)
            self._cache_rows[key] = (getter, lbl)
            form.addRow(label, row)
        self._refresh_cache_stats()
        btn_refresh = QPushButton("刷新统计")
        btn_refresh.clicked.connect(self._refresh_cache_stats)
        form.addRow(btn_refresh)
        hint = QLabel("清理会删除对应目录下的全部文件（保留目录本身）；官方电子书清理后需重新下载。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        form.addRow(hint)
        return w

    def _refresh_cache_stats(self):
        from cbeta_publish.books.cache_manager import dir_stats, human
        for key, (getter, lbl) in self._cache_rows.items():
            d = getter()
            if not d:
                lbl.setText("（未配置）")
                continue
            st = dir_stats(d)
            lbl.setText(f"{human(st['bytes'])} / {st['files']} 文件")

    def _clean_cache(self, key, path):
        if not path:
            QMessageBox.information(self, "提示", "未配置该目录")
            return
        if QMessageBox.question(self, "清理缓存", f"删除以下目录的全部内容？\n{path}") != QMessageBox.Yes:
            return
        from cbeta_publish.books.cache_manager import clean, human
        r = clean(path)
        QMessageBox.information(self, "完成", f"已删除 {r['removed_files']} 个文件（{human(r['removed_bytes'])}）")
        self._refresh_cache_stats()

    # ---------- 页签：更新源 ----------
    def _tab_update(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.lbl_last_check = QLabel()
        v.addWidget(self.lbl_last_check)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["分类", "名称", "远端 URL", "本地文件", "状态"])
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        v.addWidget(self.tbl, 1)
        self.lbl_upd_log = QLabel("")
        self.lbl_upd_log.setWordWrap(True)
        self.lbl_upd_log.setStyleSheet("color: gray;")
        v.addWidget(self.lbl_upd_log)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        btn_check = QPushButton("立即检查更新")
        btn_check.clicked.connect(self._check_update)
        btn_r_orig = QPushButton("恢复原始（mulu）")
        btn_r_orig.clicked.connect(lambda: self._restore_mulu("original"))
        btn_r_last = QPushButton("恢复上一次（mulu）")
        btn_r_last.clicked.connect(lambda: self._restore_mulu("last"))
        h.addWidget(btn_check); h.addWidget(btn_r_orig); h.addWidget(btn_r_last); h.addStretch()
        v.addWidget(row)
        hint = QLabel("权威源为 cbdata/stable scope-selector（部类/朝代/作者）；更新前旧文件自动快照到 mulu/backup/last/。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self._reload_update_table()
        return w

    def _reload_update_table(self):
        from cbeta_publish.books.remote_sources import SOURCES, local_path
        self.tbl.setRowCount(0)
        for key, cat, url, rel in SOURCES:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            p = local_path(rel)
            vals = [cat, key, url, rel, "已就绪" if p.exists() else "缺失"]
            for c, val in enumerate(vals):
                self.tbl.setItem(r, c, QTableWidgetItem(val))
        try:
            import json as _json
            meta = _json.loads((PROJECT_ROOT / "mulu" / "cache" / "meta.json").read_text(encoding="utf-8")) if (PROJECT_ROOT / "mulu" / "cache" / "meta.json").exists() else {}
            self.lbl_last_check.setText(f"上次检查：{meta.get('last_check', '从未')}")
        except Exception:
            self.lbl_last_check.setText("上次检查：从未")

    def _check_update(self):
        from cbeta_publish.books.remote_manager import RemoteManager
        from cbeta_publish.books.remote_sources import SOURCES
        rm = RemoteManager(PROJECT_ROOT / "mulu" / "cache" / "meta.json")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        logs = []
        def progress(msg):
            logs.append(msg)
            self.lbl_upd_log.setText(" / ".join(logs[-4:]))
            QApplication.processEvents()
        try:
            result = rm.update_all(SOURCES, BACKUP_DIR, progress=progress)
        finally:
            QApplication.restoreOverrideCursor()
        upd = [k for k, v in result.items() if v == "updated"]
        fail = [k for k, v in result.items() if v == "failed"]
        self._reload_update_table()
        QMessageBox.information(self, "检查更新",
                                f"更新 {len(upd)} 项，失败 {len(fail)} 项，其余已最新。\n"
                                + (f"失败：{', '.join(fail)}" if fail else ""))

    def _restore_mulu(self, which: str):
        src_dir = BACKUP_DIR / which
        if not src_dir.exists() or not any(src_dir.iterdir()):
            QMessageBox.information(self, "提示", f"备份目录为空：{src_dir}")
            return
        label = "出厂原始" if which == "original" else "上一次"
        if QMessageBox.question(self, "恢复", f"用「{label}」备份覆盖 mulu 元数据？") != QMessageBox.Yes:
            return
        try:
            mulu = PROJECT_ROOT / "mulu"
            names = []
            for f in src_dir.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(mulu / f.name))
                    names.append(f.name)
            QMessageBox.information(self, "完成", f"已恢复 {len(names)} 个文件：{', '.join(names[:5])}）")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"恢复失败：{e}")

    # ---------- 页签：目录过滤 ----------
    def _tab_filters(self):
        w = QWidget()
        v = QVBoxLayout(w)
        tip = QLabel("勾选=显示；取消=在该视图中隐藏（使目录简洁）。部類同时作用于「部类」与「三藏」视图。")
        tip.setStyleSheet("color: gray;")
        tip.setWordWrap(True)
        v.addWidget(tip)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        b_all = QPushButton("全选")
        b_none = QPushButton("全不选")
        b_all.clicked.connect(lambda: self._set_all_filters(True))
        b_none.clicked.connect(lambda: self._set_all_filters(False))
        h.addWidget(b_all); h.addWidget(b_none); h.addStretch()
        v.addWidget(row)
        # 三组过滤放入子页签，避免面板过长
        sub = QTabWidget()
        def _page(lst):
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(lst)
            return page
        self.lst_bulei = QListWidget()
        sub.addTab(_page(self.lst_bulei), "部类 / 三藏")
        self.lst_dyn = QListWidget()
        sub.addTab(_page(self.lst_dyn), "朝代")
        self.lst_vol = QListWidget()
        sub.addTab(_page(self.lst_vol), "刊本")
        v.addWidget(sub, 1)
        return w

    def _populate_filter_lists(self):
        mulu = Path(self._cfg.get("mulu_dir", ""))
        filters = self._cfg.setdefault("catalog", {}).setdefault("filters", {})
        hidden_t = set(filters.setdefault("tripitaka", {}).setdefault("hidden", []))
        hidden_d = set(filters.setdefault("dynasty", {}).setdefault("hidden", []))
        hidden_v = set(filters.setdefault("vol", {}).setdefault("hidden", []))
        # 部類标题
        self.lst_bulei.clear()
        titles = []
        try:
            from cbeta_publish.catalog.bulei_parser import parse_bulei_json, parse_bulei
            cat = mulu / "category.json"
            roots = parse_bulei_json(cat) if cat.exists() else parse_bulei(mulu / "bulei.txt")
            titles = [r.title for r in roots]
        except Exception:
            titles = []
        for t in titles:
            it = QListWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked if t in hidden_t else Qt.Checked)
            self.lst_bulei.addItem(it)
        # 朝代
        self.lst_dyn.clear()
        try:
            from cbeta_publish.catalog.dynasty_service import dynasty_titles
            dtitles = dynasty_titles(mulu / "dynasty-works.json")
        except Exception:
            dtitles = []
        if not dtitles:
            it = QListWidgetItem("（未下载 dynasty-works.json，请到「更新源」检查更新）")
            it.setFlags(Qt.NoItemFlags)
            self.lst_dyn.addItem(it)
        else:
            for t in dtitles:
                it = QListWidgetItem(t)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked if t in hidden_d else Qt.Checked)
                self.lst_dyn.addItem(it)
        # 刊本
        self.lst_vol.clear()
        try:
            from cbeta_publish.catalog.vol_service import edition_titles
            etitles = edition_titles(mulu / "vol.json")
        except Exception:
            etitles = []
        if not etitles:
            it = QListWidgetItem("（未下载 vol.json，请到「更新源」检查更新）")
            it.setFlags(Qt.NoItemFlags)
            self.lst_vol.addItem(it)
        else:
            for t in etitles:
                it = QListWidgetItem(t)
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked if t in hidden_v else Qt.Checked)
                self.lst_vol.addItem(it)

    def _set_all_filters(self, state):
        for lst in (self.lst_bulei, self.lst_dyn, self.lst_vol):
            for i in range(lst.count()):
                it = lst.item(i)
                if it.flags() & Qt.ItemIsUserCheckable:
                    it.setCheckState(Qt.Checked if state else Qt.Unchecked)

    def _gather_hidden(self, lst):
        out = []
        for i in range(lst.count()):
            it = lst.item(i)
            if (it.flags() & Qt.ItemIsUserCheckable) and it.checkState() != Qt.Checked:
                out.append(it.text())
        return out

    # ---------- 页签：外观 ----------
    def _tab_appearance(self):
        w = QWidget()
        form = QFormLayout(w)
        theme = self._cfg.setdefault("theme", {"mode": "system", "accent": "#8B4513"})
        self.cb_theme = self._no_wheel_until_focused(QComboBox())
        self.cb_theme.addItems(["light", "dark", "system"])
        self.cb_theme.setCurrentText(theme.get("mode", "system"))
        self.ed_accent = QLineEdit(theme.get("accent", "#8B4513"))
        self.cb_lang = self._no_wheel_until_focused(QComboBox())
        self.cb_lang.addItems(["zh-Hans", "zh-Hant", "en"])
        self.cb_lang.setCurrentText(self._cfg.get("language", "zh-Hans"))
        self.cb_tree_expand = self._no_wheel_until_focused(QComboBox())
        self.cb_tree_expand.addItems(["不展开", "展开1层", "展开2层", "展开3层", "全部展开"])
        ui = self._cfg.setdefault("ui", {})
        self.ed_app_font = QLineEdit(ui.get("app_font", "Microsoft YaHei"))
        self.sp_app_font_size = self._no_wheel_until_focused(QSpinBox())
        self.sp_app_font_size.setRange(6, 24)
        self.sp_app_font_size.setValue(int(ui.get("app_font_size") or 9))
        srow = QWidget()
        sfh = QHBoxLayout(srow)
        sfh.setContentsMargins(0, 0, 0, 0)
        sfh.addWidget(self.ed_app_font, 1)
        sfh.addWidget(QLabel("字号"))
        sfh.addWidget(self.sp_app_font_size)
        self.ed_supplement = QLineEdit(ui.get("supplement_ttf", ""))
        sbtn = QPushButton("浏览…")
        sbtn.clicked.connect(lambda: self._pick_supplement())
        sup = QWidget()
        suph = QHBoxLayout(sup)
        suph.setContentsMargins(0, 0, 0, 0)
        suph.addWidget(self.ed_supplement, 1)
        suph.addWidget(sbtn)
        form.addRow("主题", self.cb_theme)
        form.addRow("强调色", self.ed_accent)
        form.addRow("语言", self.cb_lang)
        form.addRow("导航树展开", self.cb_tree_expand)
        form.addRow("应用字体", srow)
        form.addRow("经文补充字型", sup)
        hint = QLabel("应用字体/字号与补充字型在下次启动生效；语言繁简/主题深色为预留框架。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        form.addRow(hint)
        return w

    def _pick_supplement(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择补充字型", "C:/Windows/Fonts",
                                           "字体 (*.ttf *.ttc *.otf)")
        if f:
            self.ed_supplement.setText(f)

    # ---------- 行为 ----------
    def _refresh_bg_btn(self):
        c = self._bg_color
        self.btn_bg.setStyleSheet(
            f"background-color: rgb({c.red()},{c.green()},{c.blue()});"
            f"border:1px solid #999; color: rgb({255-c.red()},{255-c.green()},{255-c.blue()});"
        )
        self.btn_bg.setText(f"#{c.red():02X}{c.green():02X}{c.blue():02X}")

    def _pick_bg(self):
        c = QColorDialog.getColor(self._bg_color, self, "封面背景色")
        if c.isValid():
            self._bg_color = c
            self._refresh_bg_btn()

    def _pick_font(self, key, ed):
        # 起始目录：当前字体所在目录（无则 C:/Windows/Fonts）；存正斜杠
        start = "C:/Windows/Fonts"
        cur = (ed.text() or "").strip()
        if cur:
            p = Path(cur)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if p.parent.is_dir():
                start = str(p.parent)
        f, _ = QFileDialog.getOpenFileName(self, f"选择字体（{key}）", start,
                                           "字体 (*.ttf *.ttc *.otf)")
        if f:
            ed.setText(self._slash(f))

    @staticmethod
    def _slash(p):
        # 路径统一正斜杠（配置里反斜杠显示混乱，且跨处比对需一致）
        return (p or "").replace("\\", "/")

    def _pick_image(self, key, ed):
        f, _ = QFileDialog.getOpenFileName(self, f"选择{key}图片", str(IMAGES_DIR),
                                           "图片 (*.jpg *.jpeg *.png *.gif *.bmp)")
        if not f:
            return
        try:
            src = Path(f)
            target = IMAGES_DIR / f"{key}{src.suffix.lower()}"
            shutil.copy2(str(src), str(target))
            ed.setText(str(target))
        except Exception as e:
            QMessageBox.warning(self, "失败", f"拷贝图片失败：{e}")

    def _reset_images(self):
        if not DEFAULT_IMAGES_DIR.exists():
            QMessageBox.information(self, "提示", "默认图片目录不存在：assets/images/default/")
            return
        try:
            for f in DEFAULT_IMAGES_DIR.iterdir():
                if f.is_file():
                    shutil.copy2(str(f), str(IMAGES_DIR / f.name))
            for key, (chk, ed) in self.img_rows.items():
                t = IMAGES_DIR / f"{key}{Path(ed.text()).suffix.lower() if ed.text() else '.jpg'}"
                ed.setText(str(t))
            QMessageBox.information(self, "完成", "已从 assets/images/default/ 恢复默认图片。")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"恢复默认图片失败：{e}")

    def _restore_default(self):
        if QMessageBox.question(self, "恢复默认", "恢复内置默认配置？（当前配置将覆盖，可在保存前取消）") != QMessageBox.Yes:
            return
        self._cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        self._sync_from_cfg()
        QMessageBox.information(self, "提示", "已载入默认配置，点「保存」生效。")

    def _restore_original(self):
        orig = BACKUP_DIR / "original" / "app.json"
        if not orig.exists():
            QMessageBox.information(self, "提示", "尚无出厂原始配置备份（首次保存时自动建立）。")
            return
        if QMessageBox.question(self, "恢复原始", "从 mulu/backup/original/app.json 恢复出厂配置？") != QMessageBox.Yes:
            return
        try:
            self._cfg = json.loads(orig.read_text(encoding="utf-8"))
            self._sync_from_cfg()
            QMessageBox.information(self, "提示", "已载入出厂配置，点「保存」生效。")
        except Exception as e:
            QMessageBox.warning(self, "失败", f"读取原始配置失败：{e}")

    def _collect(self):
        c = self._cfg
        # 数据目录
        c["mulu_dir"] = self.ed_mulu.text().strip()
        c["collections_dir"] = self.ed_collections.text().strip()
        c["book_dir"] = self.ed_book.text().strip()
        c["official_ebooks_dir"] = self.ed_ebooks.text().strip()
        c["local_xml_root"] = self.ed_xmlroot.text().strip()
        c["output_dir"] = self.ed_output.text().strip()
        c["update_interval"] = self.cb_interval.currentText()
        c["default_source"] = self.cb_default_source.currentText()
        c.setdefault("xml2pdf", {})
        c["xml2pdf"].update({
            "path": self.ed_x2p.text().strip(),
            "page": self.cb_x2p_page.currentText(),
            "font_lang": self.cb_x2p_font.currentText(),
            "engine": self.ed_x2p_engine.text().strip(),
            "vertical": self.chk_x2p_v.isChecked(),
        })
        # 封面/版式
        cover = c.setdefault("cover", {})
        cover["organizer"] = self.ed_organizer.text().strip()
        cover["imprint"] = self.ed_imprint.text().strip()
        cover.pop("series", None)
        cover["mode"] = self.cb_mode.currentText()
        cover["enabled"] = self.chk_cover_enabled.isChecked()
        cover.setdefault("intro", {})["enabled"] = self.chk_intro_enabled.isChecked()
        cover["intro"]["title"] = self.ed_intro_title.text().strip() or "说明"
        sizes = cover.setdefault("sizes", {})
        for paper, sp in self.sp_body.items():
            sizes[f"body_{paper}"] = sp.value()
        margins = sizes.setdefault("margins", {})
        for paper, sides in self.sp_margins.items():
            margins[paper] = {side: sp.value() for side, sp in sides.items()}
        styles = cover.setdefault("styles", {})
        styles["background"] = {"color": [self._bg_color.red(), self._bg_color.green(), self._bg_color.blue()]}
        for key, ed in self.font_rows.items():
            styles.setdefault(key, {})["font"] = ed.text().strip()
        images = cover.setdefault("images", {})
        for key, (chk, ed) in self.img_rows.items():
            images[key] = {"file": ed.text().strip(), "enabled": chk.isChecked()}
        c.setdefault("pdf", {})["split_pages"] = self.sp_split_pdf.value()
        c.setdefault("epub", {})["split_items"] = self.sp_split_epub.value()
        c.setdefault("merge", {})["by_volume"] = self.chk_by_volume.isChecked()
        # 外观
        c.setdefault("theme", {})["mode"] = self.cb_theme.currentText()
        c["theme"]["accent"] = self.ed_accent.text().strip()
        c["language"] = self.cb_lang.currentText()
        # 导航树展开
        idx = self.cb_tree_expand.currentIndex()
        if idx == 0:
            te = {"mode": "none"}
        elif idx == 4:
            te = {"mode": "all"}
        else:
            te = {"mode": "depth", "depth": idx}
        c.setdefault("ui", {})["tree_expand"] = te
        ui = c.setdefault("ui", {})
        ui["app_font"] = self.ed_app_font.text().strip() or "Microsoft YaHei"
        ui["app_font_size"] = self.sp_app_font_size.value()
        ui["supplement_ttf"] = self.ed_supplement.text().strip()
        # 目录过滤
        filters = c.setdefault("catalog", {}).setdefault("filters", {})
        filters.setdefault("tripitaka", {})["hidden"] = self._gather_hidden(self.lst_bulei)
        filters.setdefault("dynasty", {})["hidden"] = self._gather_hidden(self.lst_dyn)
        filters.setdefault("vol", {})["hidden"] = self._gather_hidden(self.lst_vol)
        return c

    def _apply(self):
        # 确定：不写盘，仅把当前设置交给主窗口在本次运行生效（下次启动仍读磁盘配置）
        try:
            self._saved_cfg = self._collect()
        except Exception as e:
            QMessageBox.warning(self, "失败", f"应用失败：{e}")
            return
        self._did_save = False
        self.accept()

    def _save(self):
        try:
            cfg = self._collect()
            _ensure_original_backup()
            _backup_last()
            CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            self._saved_cfg = cfg
            self._did_save = True
            QMessageBox.information(self, "已保存", "配置已保存到 config/app.json\n（前一份已备份至 mulu/backup/last/）")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "失败", f"保存失败：{e}")

    def result_config(self):
        return getattr(self, "_saved_cfg", None)