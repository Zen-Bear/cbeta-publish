# -*- coding: utf-8 -*-
"""统一设置对话框：数据目录 / 封面版式（含背景色、图像）/ 外观。"""
import json, os, shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QLabel, QFileDialog, QColorDialog, QMessageBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QApplication,
    QListWidget, QListWidgetItem, QRadioButton, QButtonGroup,
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor

from cbeta_publish.paths import app_root

PROJECT_ROOT = app_root()
CONFIG_PATH = PROJECT_ROOT / "config" / "app.json"
BACKUP_DIR = PROJECT_ROOT / "mulu" / "backup"
IMAGES_DIR = PROJECT_ROOT / "assets" / "images"

DEFAULT_CONFIG = {
    "official_ebooks_dir": str(PROJECT_ROOT / "cbeta_ebooks"),
    "official_library": {"root": "", "overrides": {}},
    "xml_to_ebooks_dir": str(PROJECT_ROOT / "cbeta_xml_ebooks"),
    "verify_dir": str(PROJECT_ROOT / "cbeta_verify"),
    "mulu_dir": str(PROJECT_ROOT / "mulu"),
    "collections_dir": str(PROJECT_ROOT / "collections"),
    "theme": {"mode": "system", "accent": "#8B4513"},
    "language": "zh-Hans",
    "update_interval": "weekly",
    "output_dir": str(PROJECT_ROOT / "collections_books"),
    "ui": {"tree_expand": {"mode": "depth", "depth": 2}, "layout": "three",
           "app_font": "SimSun", "app_font_size": 9,
           "supplement_ttf": "E:/dev/cbeta/xml2pdf/cbeta/CBETA 補充字型/CBETASupplement.ttf"},
    "default_source": "official",
    "default_formats": {
        "merge": ["pdf", "epub"],
        "official": ["pdf", "epub", "html", "docx", "txt"],
        "xml": ["pdf", "docx"],
    },
    "pdf": {"split_pages": 0},
    "epub": {"split_items": 0},
    "merge": {"mode": "none", "depth": 2, "by_volume": False, "name_template": "{coll}.{nn}.{seg}"},
    "xml2pdf": {"path": "E:/dev/cbeta/xml2pdf",
                "cbeta_ebook": str(PROJECT_ROOT / "cbeta_xml"),
                "preset": "", "verify_build": False,
                "verify_max_diff": 5, "verify_diff_lines": 5},
    "catalog": {"filters": {"tripitaka": {"hidden": []}, "dynasty": {"hidden": []}, "vol": {"hidden": []}}},
    "cover": {
        "organizer": "CBETA 整理",
        "imprint": "CBETA 電子佛典自選叢書",
        "date_text": "{date}",
        "mode": "print",
        "enabled": True,
        "intro": {"enabled": True, "title": "说明", "note": "依 CBETA XML 自制", "list": True},
        "bulei": {"enabled": True, "depth": 0, "layout": "lines", "sep": "·",
                  "show_num": False, "titles": "none"},
        "edit_note": {"file": "", "enabled": False},
        "images": {
            "buddha": {"file": "", "enabled": True},
            "weituo": {"file": "", "enabled": True},
        },
        "sizes": {
            "body_a5": 10, "body_a4": 12, "body_16k": 11, "body_32k": 9,
            "editnote_body": 12,
            "margins": {
                "a5": {"left": 36, "right": 36, "top": 40, "bottom": 40},
                "a4": {"left": 48, "right": 48, "top": 48, "bottom": 48},
                "16k": {"left": 42, "right": 42, "top": 44, "bottom": 44},
                "32k": {"left": 32, "right": 32, "top": 36, "bottom": 36},
            },
            "margin_ratio": {"left": 0.07, "right": 0.07, "top": 0.05, "bottom": 0.05},
        },
        "styles": {
            "title": {"font": "C:/Windows/Fonts/Source Han Serif SC Heavy (TrueType).ttf", "color": [0, 0, 0], "ratio": 3.0},
            "organizer": {"font": "C:/Windows/Fonts/Source Han Serif SC Heavy (TrueType).ttf", "color": [51, 51, 51], "ratio": 1.35},
            "date": {"font": "C:/Windows/Fonts/simhei.ttf", "color": [100, 100, 100], "ratio": 1.0},
            "toc_title": {"font": "C:/Windows/Fonts/Source Han Serif SC Heavy (TrueType).ttf", "color": [0, 0, 0], "ratio": 2.0},
            "toc_item": {"font": "C:/Windows/Fonts/simhei.ttf", "color": [30, 30, 30], "delta": 2},
            "intro_summary": {"font": "C:/Windows/Fonts/simfang.ttf", "color": [30, 30, 30]},
            "toc_page": {"font": "C:/Windows/Fonts/simhei.ttf", "color": [100, 100, 100], "ratio": 1.0},
            "background": {"color": [250, 245, 230]},
        },
        "positions": {
            "cbeta_left_mm": 18, "cbeta_top_mm": 12,
            "title_y_ratio": 0.25, "group_y_ratio": 0.30,
            "organizer_y_ratio": 0.84, "date_y_ratio": 0.89,
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
        tabs.addTab(self._tab_dirs(), "数据/输出")
        tabs.addTab(self._tab_cover(), "封面/版式")
        tabs.addTab(self._tab_made(), "自制E书")
        tabs.addTab(self._tab_cache(), "缓存")
        tabs.addTab(self._tab_filters(), "目录过滤")
        tabs.addTab(self._tab_update(), "更新源")
        tabs.addTab(self._tab_appearance(), "外观")
        v.addWidget(tabs)
        self._sync_from_cfg()

        btns = QHBoxLayout()
        self._btn_row = btns
        self._btn_apply = QPushButton("确定")
        self._btn_save = QPushButton("保存")
        self._btn_default = QPushButton("恢复默认")
        self._btn_default.setToolTip("恢复为内置默认设置（仅改动本窗口控件，需点「确定/保存」才生效）")
        self._btn_original = QPushButton("恢复原始")
        self._btn_original.setToolTip("从 mulu/backup/original/app.json 恢复初始配置（仅改动本窗口控件，需点「确定/保存」才生效）")
        self._btn_cancel = QPushButton("取消")
        # 确定=默认按钮（回车触发）；恢复默认/恢复原始靠左，其余靠右
        self._btn_apply.setDefault(True)
        self._btn_apply.setToolTip("不保存到 config/app.json，仅本次运行生效")
        btns.addWidget(self._btn_default)
        btns.addWidget(self._btn_original)
        btns.addStretch(1)
        for _b in (self._btn_apply, self._btn_save, self._btn_cancel):
            btns.addWidget(_b)
        self._btn_apply.clicked.connect(self._apply)
        self._btn_save.clicked.connect(self._save)
        self._btn_default.clicked.connect(self._restore_default)
        self._btn_original.clicked.connect(self._restore_original)
        self._btn_cancel.clicked.connect(self.reject)
        v.addLayout(btns)

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
    def _dir_row(self, edit):
        # 目录行：输入框 + 浏览按钮（打开目录为当前值所在目录）
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(edit, 1)
        btn = QPushButton("浏览…")
        btn.setFixedWidth(64)
        btn.clicked.connect(lambda: self._pick_dir(edit))
        h.addWidget(btn)
        return row

    def _pick_dir(self, edit):
        from pathlib import Path as _P
        start = (edit.text() or "").strip()
        if not _P(start).is_dir():
            start = str(_P(start).parent) if start else ""
        if not _P(start).is_dir():
            start = str(PROJECT_ROOT)
        d = QFileDialog.getExistingDirectory(self, "选择目录", start)
        if d:
            edit.setText(d)

    def _lib_overrides_from_ui(self):
        return {f: ed.text().strip() for f, ed in self.lib_override_edits.items()
                if ed.text().strip()}

    def _refresh_lib_map(self, show_popup=False):
        # 解析映射并回填覆盖占位；show_popup 时弹窗说明结果
        notes = []
        try:
            from cbeta_publish.books import official_ebook_source as _oes
            root = (self.ed_official_lib.text() or "").strip()
            ov = self._lib_overrides_from_ui()
            if not root:
                notes = ["未配置本地库（仅网上下载）"]
            else:
                _mapping, notes = _oes.resolve_library_map(root, ov)
            for f, ed in self.lib_override_edits.items():
                auto = None
                if root:
                    _m, _ = _oes.resolve_library_map(root, {})
                    _d = _m.get(f, {}).get("dir")
                    auto = _d.name if _d is not None else None
                ed.setPlaceholderText(f"自动{('：' + auto) if auto else '（留空）'}")
        except Exception as e:
            notes = [f"扫描失败：{e}"]
        if show_popup:
            QMessageBox.information(self, "格式映射扫描结果", "\n".join(notes) if notes else "无可用格式")
        return notes

    def _tab_dirs(self):
        w = QWidget()
        form = QFormLayout(w)
        form.setVerticalSpacing(2)   # 路径行与页签面板贴紧，默认 6 太空
        self.ed_mulu = QLineEdit(self._cfg.get("mulu_dir", ""))
        self.ed_collections = QLineEdit(self._cfg.get("collections_dir", ""))
        self.ed_ebooks = QLineEdit(self._cfg.get("official_ebooks_dir", ""))
        self.ed_output = QLineEdit(
            self._native_path(self._resolve_out_dir(self._cfg.get("output_dir"))))
        form.addRow("目录数据", self._dir_row(self.ed_mulu))
        form.addRow("丛书数据", self._dir_row(self.ed_collections))
        form.addRow("官方电子书", self._dir_row(self.ed_ebooks))
        form.addRow("输出目录", self._dir_row(self.ed_output))
        # E书默认来源和格式（来源单选 + 合并/ZIP/导出 默认勾选格式）
        def_box = QGroupBox("E书默认来源和格式")
        def_form = QFormLayout(def_box)
        self.src_default_box = QWidget()
        _sdb = QHBoxLayout(self.src_default_box)
        _sdb.setContentsMargins(0, 0, 0, 0)
        self.src_default_group = QButtonGroup(self.src_default_box)
        self.rb_src_official = QRadioButton("官方")
        self.rb_src_made = QRadioButton("自制")
        self.rb_src_official.setToolTip("从 CBETA 官方下载成品电子书")
        self.rb_src_made.setToolTip("电子书由程序根据官方 XML 制作（经 xml2pdf 生成）")
        for _i, _rb in enumerate((self.rb_src_official, self.rb_src_made)):
            _sdb.addWidget(_rb)
            self.src_default_group.addButton(_rb, _i)
        _made_note = QLabel("（PDF/DOCX 优化，其它格式推荐官方）")
        _made_note.setStyleSheet("color: gray;")
        _sdb.addWidget(_made_note)
        _sdb.addStretch()
        def_form.addRow("默认E书来源", self.src_default_box)
        df = self._cfg.get("default_formats", {}) or {}
        r, self.fmt_merge_boxes = self._fmt_check_row(["pdf", "epub"], df.get("merge"))
        def_form.addRow("合并默认格式", r)
        # 官方/自制两组默认格式（各自同时用于 ZIP 与 导出）
        ro, self.fmt_off_boxes = self._fmt_check_row(self._official_pack_fmts(),
                                                     df.get("official"))
        rx, self.fmt_made_boxes = self._fmt_check_row(self._made_pack_fmts(),
                                                      df.get("xml"))
        def_form.addRow("官方 ZIP/导出默认", ro)
        def_form.addRow("自制 ZIP/导出默认", rx)
        # 以下三组改 tab 面板（顺序：分册模式 / E书默认来源和格式 / 官方电子书本地库）
        # （addRow 改到末尾统一加页签，此处不再直接加行）
        # 官方电子书本地库（冻结快照；本地优先、缺失回退下载）
        lib_box = QGroupBox("官方电子书本地库（本地优先）")
        lib_form = QFormLayout(lib_box)
        self.ed_official_lib = QLineEdit((self._cfg.get("official_library") or {}).get("root", ""))
        self.ed_official_lib.setPlaceholderText("本地库根目录（空=关闭，仅网上下载），如 E:/CBETA/2026r2")
        self.ed_official_lib.editingFinished.connect(self._refresh_lib_map)
        lib_form.addRow("本地库目录", self._dir_row(self.ed_official_lib))
        _map_row = QWidget()
        _mrh = QHBoxLayout(_map_row)
        _mrh.setContentsMargins(0, 0, 0, 0)
        _mrh.addStretch()
        self.btn_lib_refresh = QPushButton("重新扫描")
        self.btn_lib_refresh.setToolTip("按关键字＋文件形态自动探测各格式子目录，结果弹窗说明")
        self.btn_lib_refresh.clicked.connect(lambda: self._refresh_lib_map(show_popup=True))
        _mrh.addWidget(self.btn_lib_refresh)
        lib_form.addRow("格式映射", _map_row)
        self.lib_override_edits = {}
        _ov = (self._cfg.get("official_library") or {}).get("overrides") or {}
        for _f in ("pdf", "epub", "html", "docx", "odt", "txt", "txt_notes"):
            _ed = QLineEdit(str(_ov.get(_f, "") or ""))
            _ed.setPlaceholderText("自动（留空）")
            _ed.setToolTip(f"手动指定 { _f} 的子目录名；留空走自动探测")
            self.lib_override_edits[_f] = _ed
            lib_form.addRow(f"覆盖:{_f}", _ed)
        self._refresh_lib_map()
        # 分册模式：合并时按此分组；「合并时选择」则每次点合并弹框
        mode_box = QGroupBox("分册模式（合并）")
        mv = QVBoxLayout(mode_box)
        mv.setSpacing(2)   # 标签行/控件行贴紧，默认 6 太空
        mv.setContentsMargins(4, 9, 4, 2)   # 压 GroupBox 内边距，顶部 9 与另两页签对齐
        self.merge_mode_group = QButtonGroup(mode_box)
        self.rb_merge_none = QRadioButton("不分册")
        self.rb_merge_volume = QRadioButton("按刊本册")
        self.rb_merge_catalog = QRadioButton("按目录（部类）")
        self.rb_merge_manual = QRadioButton("按手工分册（右栏）")
        self.rb_merge_ask = QRadioButton("合并时选择（每次弹框）")
        self.rb_merge_volume.setToolTip("按 mulu/vol.json 的刊本/册分组（一册一个文件）")
        self.rb_merge_catalog.setToolTip("按部类树路径分组（如 01 阿含部類 / 長阿含經）")
        self.rb_merge_manual.setToolTip("按右栏「手工分册」的卷分组（未分组自成一组）")
        self.rb_merge_ask.setToolTip("每次点合并时弹框选择分册模式与深度")
        _mrow = QWidget()
        _mh = QHBoxLayout(_mrow)
        _mh.setContentsMargins(0, 0, 0, 0)
        for _i, _rb in enumerate((self.rb_merge_none, self.rb_merge_volume,
                                  self.rb_merge_catalog, self.rb_merge_manual,
                                  self.rb_merge_ask)):
            _mh.addWidget(_rb)
            self.merge_mode_group.addButton(_rb, _i)
        _mh.addStretch()
        mv.addWidget(_mrow)
        _drow = QWidget()
        _dh = QHBoxLayout(_drow)
        _dh.setContentsMargins(0, 0, 0, 0)
        _dh.addWidget(QLabel("深度（按刊本册/按目录）"))
        self.sp_merge_depth = self._no_wheel_until_focused(QSpinBox())
        self.sp_merge_depth.setRange(1, 5)
        self.sp_merge_depth.setValue(int((self._cfg.get("merge", {}) or {}).get("depth", 2) or 2))
        self.sp_merge_depth.setToolTip("路径取前 N 段：1=按刊本名/顶层部类；2=刊本名_册、部类_子组（默认）")
        _dh.addWidget(self.sp_merge_depth)
        _dh.addStretch()
        mv.addWidget(_drow)
        _nrow = QWidget()
        _nh = QHBoxLayout(_nrow)
        _nh.setContentsMargins(0, 0, 0, 0)
        _nh.addWidget(QLabel("分册文件名模板"))
        self.ed_merge_name = QLineEdit()
        self.ed_merge_name.setText(str((self._cfg.get("merge", {}) or {}).get("name_template", "{coll}.{nn}.{seg}") or "{coll}.{nn}.{seg}"))
        self.ed_merge_name.setToolTip("分册文件名模板（变量见下方示例）；缺省 {coll}.{nn}.{seg}")
        self.ed_merge_name.setPlaceholderText("{coll}.{nn}.{seg}")
        _nh.addWidget(self.ed_merge_name, 1)
        mv.addWidget(_nrow)
        _nhint = QLabel("例：{coll} {seg} → 太虛大師全書 01 編纂說明；{coll} {nn} {seg}.{count}册 → 太虛大師全書 02 法藏.12册")
        _nhint.setStyleSheet("color: gray;")
        _nhint.setWordWrap(True)
        mv.addWidget(_nhint)
        _seghint = QLabel("变量（以分段 06 寶積部類 / 淨土經／論／疏 / 阿彌陀經 为例）："
                          "{seg0}→06；{seg1}→寶積部類；{seg2}→淨土經／論／疏；"
                          "{seg3}→阿彌陀經；{seg}＝末段；{stem}→下划线全路径；"
                          "{label}→斜杠全路径；{n}→序号（不补零）；{nn}→序号"
                          "（自适应补零，宽度看总文件数）；{count}→本组部数；"
                          "{coll}→丛书名。超段变量置空。")
        _seghint.setStyleSheet("color: gray;")
        _seghint.setWordWrap(True)
        mv.addWidget(_seghint)
        mv.addStretch(1)   # 余高沉底：行只取自然高度，不均摊拉高（否则行间空两行）
        dirs_tabs = QTabWidget()
        self._dirs_tabs = dirs_tabs
        dirs_tabs.addTab(mode_box, "分册模式")
        dirs_tabs.addTab(def_box, "E书默认来源和格式")
        dirs_tabs.addTab(lib_box, "官方电子书本地库")
        form.addRow(dirs_tabs)
        self._set_merge_mode()
        # 分册阈值：0=不分册（默认）；暂隐藏，值仍随保存/载入
        self.split_box = QGroupBox("分册（0=不分册）")
        split_form = QFormLayout(self.split_box)
        self.sp_split_pdf = self._no_wheel_until_focused(QSpinBox())
        self.sp_split_pdf.setRange(0, 99999)
        self.sp_split_pdf.setValue(int((self._cfg.get("pdf", {}) or {}).get("split_pages", 0) or 0))
        split_form.addRow("PDF 分册页数", self.sp_split_pdf)
        self.sp_split_epub = self._no_wheel_until_focused(QSpinBox())
        self.sp_split_epub.setRange(0, 99999)
        self.sp_split_epub.setValue(int((self._cfg.get("epub", {}) or {}).get("split_items", 0) or 0))
        split_form.addRow("EPUB 分册文档数", self.sp_split_epub)
        form.addRow(self.split_box)
        self.split_box.setVisible(False)
        # 内容超高：套卷动窗（同封面/版式页），对话框保持 680×560
        from PySide6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setWidget(w)
        return sc

    def _merge_mode_value(self):
        if self.rb_merge_volume.isChecked():
            return "volume"
        if self.rb_merge_catalog.isChecked():
            return "catalog"
        if self.rb_merge_manual.isChecked():
            return "manual"
        if self.rb_merge_ask.isChecked():
            return "ask"
        return "none"

    def _set_merge_mode(self):
        m = (self._cfg.get("merge", {}) or {}).get("mode")
        if m not in ("none", "volume", "catalog", "manual", "ask"):
            m = "volume" if (self._cfg.get("merge", {}) or {}).get("by_volume") else "none"
        ({"volume": self.rb_merge_volume, "catalog": self.rb_merge_catalog,
          "manual": self.rb_merge_manual,
          "ask": self.rb_merge_ask}.get(m, self.rb_merge_none)).setChecked(True)

    def _sync_merge_defaults(self, c):
        self._set_merge_mode()
        try:
            d = int((c.get("merge", {}) or {}).get("depth", 2) or 2)
        except Exception:
            d = 2
        self.sp_merge_depth.setValue(max(1, min(5, d)))
        self.ed_merge_name.setText(str((c.get("merge", {}) or {}).get("name_template", "{coll}.{nn}.{seg}") or "{coll}.{nn}.{seg}"))

    @staticmethod
    def _official_pack_fmts():
        return ["pdf", "epub", "html", "docx", "odt", "txt", "txt_notes"]

    @staticmethod
    def _made_pack_fmts():
        return ["pdf", "docx", "epub"]

    def _fmt_check_row(self, fmts, checked):
        """一行多选（单侧）→ (row, {fmt: QCheckBox})；未给 checked 时按 fmts 全选。"""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        boxes = {}
        want = set(checked if checked is not None else fmts)
        label_map = {"txt_notes": "txt含注释"}
        for f in fmts:
            cb = QCheckBox(label_map.get(f, f))
            cb.setChecked(f in want)
            h.addWidget(cb)
            boxes[f] = cb
        h.addStretch()
        return row, boxes

    # ---------- 页签：自制E书 ----------
    def _tab_made(self):
        w = QWidget()
        form = QFormLayout(w)
        # 自制程序与目录（原在「数据/输出」的「自制」组框）
        self.ed_x2p = QLineEdit(self._cfg.get("xml2pdf", {}).get("path", ""))
        self.ed_x2p_ebook = QLineEdit(
            (self._cfg.get("xml2pdf", {}) or {}).get("cbeta_ebook")
            or str(PROJECT_ROOT / "cbeta_xml"))
        self.ed_x2p_ebook.setPlaceholderText("CBETA XML 目录（不可为空；空则用默认 cbeta_xml）")
        self.ed_xmlbooks = QLineEdit()
        self.ed_verify = QLineEdit()
        self.ed_verify.setPlaceholderText("校验工作目录（默认 cbeta_verify）")
        self.cb_preset = self._no_wheel_until_focused(QComboBox())
        self._reload_preset_combo()
        # 制作书籍：右栏「自制/重制」按钮是否带校验（校验通过才导入）
        self.build_verify_box = QWidget()
        _bvb = QHBoxLayout(self.build_verify_box)
        _bvb.setContentsMargins(0, 0, 0, 0)
        self.build_verify_group = QButtonGroup(self.build_verify_box)
        self.rb_build_verify = QRadioButton("校验")
        self.rb_build_noverify = QRadioButton("无校验")
        self.rb_build_verify.setToolTip("右栏「自制/重制」生成后逐本校验，仅校验通过的才导入自制书目录")
        self.rb_build_noverify.setToolTip("右栏「自制/重制」只生成，不校验（默认）")
        for _i, _rb in enumerate((self.rb_build_verify, self.rb_build_noverify)):
            _bvb.addWidget(_rb)
            self.build_verify_group.addButton(_rb, _i)
        _bvb.addStretch()
        (self.rb_build_verify if (self._cfg.get("xml2pdf", {}) or {}).get("verify_build")
         else self.rb_build_noverify).setChecked(True)
        form.addRow("制作书籍", self.build_verify_box)
        _x2p = self._cfg.get("xml2pdf", {}) or {}
        self.sp_verify_maxdiff = self._no_wheel_until_focused(QSpinBox())
        self.sp_verify_maxdiff.setRange(0, 50)
        self.sp_verify_maxdiff.setValue(int(_x2p.get("verify_max_diff", 5) or 5))
        self.sp_verify_maxdiff.setToolTip(
            "校验阈值：报告里 缺失+多余 行数 ≤ 此值判为通过（默认 5；透传上游 --verify-max-diff）")
        form.addRow("校验阈值（缺+多）", self.sp_verify_maxdiff)
        self.sp_verify_difflines = self._no_wheel_until_focused(QSpinBox())
        self.sp_verify_difflines.setRange(0, 50)
        self.sp_verify_difflines.setValue(int(_x2p.get("verify_diff_lines", 5) or 5))
        self.sp_verify_difflines.setToolTip(
            "失败时报告里列出的上下文对比行数（默认 5；透传上游 --verify-diff-lines）")
        form.addRow("报告失败上下文行数", self.sp_verify_difflines)
        form.addRow("自制程序路径", self._dir_row(self.ed_x2p))
        form.addRow("CBETA XML 目录", self._dir_row(self.ed_x2p_ebook))
        form.addRow("自制电子书", self._dir_row(self.ed_xmlbooks))
        form.addRow("校验工作目录", self._dir_row(self.ed_verify))
        form.addRow("默认预设", self.cb_preset)
        hint = QLabel("自制：电子书由程序根据官方 XML 制作。默认预设用于来源选自制、且未另选预设时。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow(hint)
        return w


    def _reload_preset_combo(self, keep=None):
        # 预设下拉：xml2pdf 仓库 presets/ 下的预设名 + 首项"出厂默认"（空值）
        from cbeta_publish.books import xml2pdf_bridge as _b
        names = _b.list_presets(self._cfg)
        cur = self.cb_preset.currentData() if self.cb_preset.count() else (keep if keep is not None else None)
        if cur is None:
            cur = (self._cfg.get("xml2pdf", {}) or {}).get("preset", "")
        self.cb_preset.blockSignals(True)
        self.cb_preset.clear()
        self.cb_preset.addItem("出厂默认", "")
        for n in names:
            self.cb_preset.addItem(n, n)
        i = self.cb_preset.findData(cur)
        self.cb_preset.setCurrentIndex(i if i >= 0 else 0)
        self.cb_preset.blockSignals(False)

    def _set_mode(self, mode):
        # 单选按钮与 cover.mode（"print"/"reading"）互转
        _m = (mode or "print").strip()
        self.rb_reading.setChecked(_m == "reading")
        self.rb_print.setChecked(not self.rb_reading.isChecked())

    def _mode(self):
        return "reading" if self.rb_reading.isChecked() else "print"

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
        outer = QVBoxLayout(w)
        form = QFormLayout()
        self._cover_form = form
        cover = self._cfg.setdefault("cover", {})
        self._migrate_series_imprint(cover)
        # 通用项（书籍署名/开关），版式细节见下方子页签
        self.ed_organizer = QLineEdit(cover.get("organizer", "CBETA 整理"))
        self.ed_imprint = QLineEdit(cover.get("imprint", "CBETA 電子佛典自選叢書"))
        self.ed_imprint.setToolTip("封面左上角文字；可填系列名（如太虛大師全書）或落款；留空则不绘制")
        self.ed_date = QLineEdit(cover.get("date_text", "{date}"))
        self.ed_date.setToolTip("封面日期行（整理者之后）；{date}=今天，可直接写任意文字；留空则不绘制")
        # PDF 合并模式：打印模式（补空白页）/ 阅读模式（去空白）
        self.cb_mode = QWidget()
        _mh = QHBoxLayout(self.cb_mode)
        _mh.setContentsMargins(0, 0, 0, 0)
        self.rb_print = QRadioButton("打印模式")
        self.rb_reading = QRadioButton("阅读模式")
        self.rb_print.setToolTip("打印模式：补空白页（封面/封面图/目录/正文/封底图/封底按页序对齐）")
        self.rb_reading.setToolTip("阅读模式：去空白（去掉空白页，适合屏幕阅读）")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_print)
        self.mode_group.addButton(self.rb_reading)
        _mh.addWidget(self.rb_print)
        _mh.addWidget(self.rb_reading)
        _mh.addStretch()
        self._set_mode(cover.get("mode", "print"))
        form.addRow("左上角系列名", self.ed_imprint)
        form.addRow("整理者署名", self.ed_organizer)
        form.addRow("日期", self.ed_date)
        form.addRow("PDF 合并模式", self.cb_mode)
        # 以下行组进 Tab 首项「封面/说明」：合并开关/编辑说明/说明页/部类行
        _cpage = QWidget()
        cform = QFormLayout(_cpage)
        self.chk_cover_enabled = QCheckBox("合并时加封面封底、说明（以下所有内容）")
        self.chk_cover_enabled.setToolTip("关闭后直接拼接原文件，仅生成书签（原书签降一级归入对应书下）")
        self.chk_cover_enabled.setChecked(bool(cover.get("enabled", True)))
        cform.addRow(self.chk_cover_enabled)
        # 编辑说明（TXT 转排版，插在说明页之前、仅第一分册；默认关闭）：
        # 复选框＋浏览按钮＋输入框同一行（无单独标签行）
        _en = cover.setdefault("edit_note", {"file": "", "enabled": False})
        self.ed_editnote = QLineEdit(_en.get("file", ""))
        self.ed_editnote.setReadOnly(True)
        self.ed_editnote.setPlaceholderText("未关联（合并时不插编辑说明页）")
        _enrow = QWidget()
        _enh = QHBoxLayout(_enrow)
        _enh.setContentsMargins(0, 0, 0, 0)
        self.chk_editnote_enabled = QCheckBox("插入编辑说明页")
        self.chk_editnote_enabled.setChecked(bool(_en.get("enabled", False)))
        self.btn_editnote_file = QPushButton("（内容文件）")
        self.btn_editnote_file.setToolTip("选择编辑说明 TXT 文件")
        self.btn_editnote_file.clicked.connect(self._pick_editnote)
        _enh.addWidget(self.chk_editnote_enabled)
        _enh.addWidget(self.btn_editnote_file)
        _enh.addWidget(self.ed_editnote, 1)
        cform.addRow(_enrow)
        # 说明页（部类统计 + 完整清单，自动从书单推导；仅封面模式生效）：
        # 标题标签＋输入框并到复选框同一行右侧
        intro = cover.setdefault("intro", {"enabled": True, "title": "说明", "note": "依 CBETA XML 自制", "list": True})
        _inrow = QWidget()
        _inh = QHBoxLayout(_inrow)
        _inh.setContentsMargins(0, 0, 0, 0)
        self.chk_intro_enabled = QCheckBox("插入说明页（部类统计 + 完整清单）")
        self.chk_intro_enabled.setChecked(bool(intro.get("enabled", True)))
        self.ed_intro_title = QLineEdit(intro.get("title", "说明"))
        _inh.addWidget(self.chk_intro_enabled)
        _inh.addWidget(QLabel("说明页标题"))
        _inh.addWidget(self.ed_intro_title, 1)
        cform.addRow(_inrow)
        self.ed_intro_note = QLineEdit(intro.get("note", "依 CBETA XML 自制"))
        self.ed_intro_note.setToolTip("说明页标题下一行（居中）；仅来源=自制时显示。留空则不显示。")
        cform.addRow("自制书说明", self.ed_intro_note)
        hint_intro = QLabel("部类统计与清单自动从丛书书单推导；仅在「合并时加封面封底、说明（以下所有内容）」开启时插入。")
        hint_intro.setStyleSheet("color: gray;")
        hint_intro.setWordWrap(True)
        cform.addRow(hint_intro)
        # 封面部类行（分册副标题显示形态；不分册无副标题）
        _bl = cover.setdefault("bulei", {"enabled": True, "depth": 0, "layout": "lines",
                                          "sep": "·", "show_num": False, "titles": "none"})
        _brow = QWidget()
        _bh = QHBoxLayout(_brow)
        _bh.setContentsMargins(0, 0, 0, 0)
        _bh.addWidget(QLabel("封面部类行"))
        self.chk_bulei_show = QCheckBox("显示部类/书名")
        self.chk_bulei_show.setChecked(bool(_bl.get("enabled", True)))
        self.chk_bulei_show.setToolTip("总开关：关则封面只剩丛书名，不画部类行与书名")
        _bh.addWidget(self.chk_bulei_show)
        self.cb_bulei_titles = QComboBox()
        self.cb_bulei_titles.addItem("不显示书名", "none")
        self.cb_bulei_titles.addItem("显示所有书名", "all")
        _ti = max(0, self.cb_bulei_titles.findData(_bl.get("titles", "none")))
        self.cb_bulei_titles.setCurrentIndex(_ti)
        self.cb_bulei_titles.setToolTip("显示所有书名：一行一个，不跟部类行设置")
        _bh.addWidget(self.cb_bulei_titles)
        _bh.addStretch()
        cform.addRow(_brow)
        _brow2 = QWidget()
        _bh2 = QHBoxLayout(_brow2)
        _bh2.setContentsMargins(0, 0, 0, 0)
        _bh2.addWidget(QLabel("部类行细节"))
        self.sp_bulei_depth = self._no_wheel_until_focused(QSpinBox())
        self.sp_bulei_depth.setRange(0, 5)
        try:
            _bd = int((_bl.get("depth", 0) or 0))
        except Exception:
            _bd = 0
        self.sp_bulei_depth.setValue(max(0, min(5, _bd)))
        self.sp_bulei_depth.setToolTip("显示深度：0=跟随分册深度；1–5 取全路径前 N 段")
        _bh2.addWidget(self.sp_bulei_depth)
        self.cb_bulei_layout = QComboBox()
        self.cb_bulei_layout.addItem("每层一行", "lines")
        self.cb_bulei_layout.addItem("一行", "one")
        _li = max(0, self.cb_bulei_layout.findData(_bl.get("layout", "lines")))
        self.cb_bulei_layout.setCurrentIndex(_li)
        _bh2.addWidget(self.cb_bulei_layout)
        self.ed_bulei_sep = QLineEdit(str(_bl.get("sep", "·") or "·"))
        self.ed_bulei_sep.setMaximumWidth(40)
        self.ed_bulei_sep.setToolTip("一行模式分隔符（默认 ·）")
        _bh2.addWidget(self.ed_bulei_sep)
        self.chk_bulei_num = QCheckBox("显示序号前缀（如 06）")
        self.chk_bulei_num.setChecked(bool(_bl.get("show_num", False)))
        _bh2.addWidget(self.chk_bulei_num)
        _bh2.addStretch()
        cform.addRow(_brow2)
        outer.addLayout(form)
        # 版式子页签（按使用顺序）：封面/说明 → 封面/封底图、背景色 → 字体 → 基准字号 → 边距
        sub = QTabWidget()
        self._cover_subtabs = sub
        sub.addTab(_cpage, "封面/说明")
        sub.addTab(self._cover_tab_images(cover), "封面/封底图、背景色")
        sub.addTab(self._cover_tab_fonts(cover), "字体")
        sub.addTab(self._cover_tab_sizes(cover), "基准字号")
        sub.addTab(self._cover_tab_margins(cover), "边距")
        outer.addWidget(sub)
        # 面板过长：套卷动窗
        from PySide6.QtWidgets import QScrollArea
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QScrollArea.NoFrame)
        sc.setWidget(w)
        return sc

    def _cover_tab_images(self, cover):
        # 子页签 1：封面图/封底图 + 背景色
        w = QWidget()
        form = QFormLayout(w)
        images = cover.setdefault("images", {
            "buddha": {"file": "", "enabled": True},
            "weituo": {"file": "", "enabled": True},
        })
        self.img_rows = {}
        for key, label in [("buddha", "封面图"), ("weituo", "封底图")]:
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
            # 启用即选默认：空/失效路径自动填入 images/ 下的 1.*/2.*
            self._ensure_default_image(key, chk, ed)
            chk.toggled.connect(lambda _on, k=key, c=chk, e=ed: self._ensure_default_image(k, c, e))
            form.addRow(label, box)
        hint = QLabel("启用后自动选用 assets/images/ 下的 B01.jpg（封面图）/ B02.jpg（封底图）；"
                      "文件不存在时回退 1.* / 2.*（后缀不限）；「浏览…」可换图（按编号存放）。"
                      "关闭图像开关后，合成时不插入该图及其前后空白页。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        form.addRow(hint)
        # 封面背景色
        styles = cover.setdefault("styles", {})
        bg = styles.setdefault("background", {"color": [250, 245, 230]})
        self._bg_color = QColor(*bg.get("color", [250, 245, 230]))
        self.btn_bg = QPushButton()
        self.btn_bg.setFixedWidth(80)
        self._refresh_bg_btn()
        self.btn_bg.clicked.connect(self._pick_bg)
        form.addRow("封面背景色", self.btn_bg)
        # 说明页/目录页背景色（缺席＝跟随封面背景色；单独选色后独立）
        self._bg_colors = {}
        self._bg_btns = {}
        self._bg_custom = set()
        for _key, _label in (("intro_background", "说明页背景色"),
                             ("toc_background", "目录页背景色")):
            _btn = QPushButton()
            _btn.setFixedWidth(80)
            self._bg_btns[_key] = _btn
            _btn.clicked.connect(lambda _, k=_key, t=_label: self._pick_bg_for(k, t))
            form.addRow(_label, _btn)
        self._sync_bg_colors(cover)
        return w

    def _sync_bg_colors(self, cover):
        # 说明/目录背景色回读：有显式值则独立显示并记 custom；无则显示封面色（跟随）
        styles = cover.setdefault("styles", {})
        _cover_bg = ((styles.get("background") or {}).get("color")
                     or [250, 245, 230])
        for _key in ("intro_background", "toc_background"):
            _info = styles.get(_key) or {}
            _c = _info.get("color") if isinstance(_info, dict) else None
            if isinstance(_c, (list, tuple)) and len(_c) == 3:
                self._bg_custom.add(_key)
            else:
                self._bg_custom.discard(_key)
                _c = list(_cover_bg)
            self._bg_colors[_key] = QColor(*_c)
            self._refresh_bg_btn_for(_key)

    def _cover_tab_fonts(self, cover):
        # 子页签 2：字体（封面/目录/说明页）：styles.<key>.font
        w = QWidget()
        form = QFormLayout(w)
        styles = cover.setdefault("styles", {})
        self.font_rows = {}
        font_labels = [
            ("cbeta", "左上角系列名"), ("title", "封面标题"), ("organizer", "整理者"),
            ("date", "日期"), ("toc_title", "目录/说明标题"),
            ("toc_item", "目录/说明条目"), ("toc_page", "目录页码"),
            ("intro_summary", "说明页简介"),
            ("editnote_title", "编辑说明标题"), ("editnote_body", "编辑说明正文"),
        ]
        _font_defaults = {"intro_summary": "C:/Windows/Fonts/simfang.ttf",
                          "editnote_title": "C:/Windows/Fonts/msyhbd.ttc",
                          "editnote_body": "C:/Windows/Fonts/simsun.ttc"}
        for key, label in font_labels:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            cur = styles.get(key, {}).get("font", "") or _font_defaults.get(key, "")
            ed = QLineEdit(self._native_path(cur))
            ed.setToolTip("缺繁体字形时按顺序回退到系统全字库（黑体simhei → 微软雅黑msyh → 宋体simsun）")
            ed.editingFinished.connect(lambda _k=key, _e=ed: self._check_font_row(_k, _e))
            btn = QPushButton("浏览…")
            btn.clicked.connect(lambda _, k=key, e=ed: self._pick_font(k, e))
            h.addWidget(ed, 1); h.addWidget(btn)
            self.font_rows[key] = ed
            self._check_font_row(key, ed)
            form.addRow(label, row)
        return w

    def _check_font_row(self, key, ed):
        # 字体路径存在性检测：缺失标红框（保存不断言，合并时按既有规则回退）
        _tip = "缺繁体字形时按顺序回退到系统全字库（黑体simhei → 微软雅黑msyh → 宋体simsun）"
        try:
            cur = (ed.text() or "").strip()
            ed.setStyleSheet("")
            ed.setToolTip(_tip)
            if not cur:
                return
            p = Path(cur)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if not p.is_file():
                ed.setStyleSheet("border: 1px solid red;")
                ed.setToolTip(f"路径不存在：{cur}（合并时将回退系统全字库）")
        except Exception:
            pass

    def _cover_tab_sizes(self, cover):
        # 子页签 3：封面页基准字号（纸张联动基准）＋编辑说明正文字号
        w = QWidget()
        form = QFormLayout(w)
        sizes = cover.setdefault("sizes", {})
        self.sp_body = {}
        for paper in ["a5", "a4", "16k", "32k"]:
            self.sp_body[paper] = self._no_wheel_until_focused(QSpinBox())
            self.sp_body[paper].setRange(6, 40)
            self.sp_body[paper].setValue(int(sizes.get(f"body_{paper}", {"a5":10,"a4":12,"16k":11,"32k":9}[paper])))
            form.addRow(f"封面页基准字号（{paper}）", self.sp_body[paper])
        self.sp_editnote_body = self._no_wheel_until_focused(QSpinBox())
        self.sp_editnote_body.setRange(6, 40)
        try:
            _eb = int(sizes.get("editnote_body", 12) or 12)
        except Exception:
            _eb = 12
        self.sp_editnote_body.setValue(max(6, min(40, _eb)))
        self.sp_editnote_body.setToolTip("编辑说明页正文（PDF）字号，不跟页面基准")
        form.addRow("编辑说明正文字号", self.sp_editnote_body)
        hint = QLabel("基准字号按源 PDF 纸张自动选用；其余位置/字号由此派生。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        form.addRow(hint)
        return w

    def _cover_tab_margins(self, cover):
        # 子页签 4：每纸张边距(pt)：封面/目录/说明页统一以边距为准
        w = QWidget()
        v = QVBoxLayout(w)
        sizes = cover.setdefault("sizes", {})
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
        v.addWidget(mg_box)
        hint_mg = QLabel("封面文本、目录、说明页均以该边距为界（未配置纸张时回退到内部默认）。")
        hint_mg.setStyleSheet("color: gray;")
        hint_mg.setWordWrap(True)
        v.addWidget(hint_mg)
        v.addStretch(1)
        return w

    def _sync_from_cfg(self):
        """恢复默认/原始后，将 self._cfg 的值重新填充到所有控件。"""
        c = self._cfg
        self.ed_mulu.setText(self._native_path(c.get("mulu_dir", "")))
        self.ed_collections.setText(self._native_path(c.get("collections_dir", "")))
        self.ed_ebooks.setText(self._native_path(c.get("official_ebooks_dir", "")))
        _lib = c.get("official_library") or {}
        self.ed_official_lib.setText(self._native_path(_lib.get("root", "")))
        _ov = _lib.get("overrides") or {}
        for _f, _ed in self.lib_override_edits.items():
            _ed.setText(str(_ov.get(_f, "") or ""))
        self._refresh_lib_map()
        self.ed_xmlbooks.setText(self._native_path(
            c.get("xml_to_ebooks_dir") or str(PROJECT_ROOT / "cbeta_xml_ebooks")))
        self.ed_verify.setText(self._native_path(
            c.get("verify_dir", str(PROJECT_ROOT / "cbeta_verify"))))
        self.ed_output.setText(self._native_path(self._resolve_out_dir(c.get("output_dir"))))
        iv = c.get("update_interval", "weekly")
        if iv in ["daily", "weekly", "monthly", "manual"]:
            self.cb_interval.setCurrentText(iv)
        src = c.get("default_source", "official")
        (self.rb_src_made if src == "xml" else self.rb_src_official).setChecked(True)
        df = c.get("default_formats", {}) or {}
        for f, cb in self.fmt_merge_boxes.items():
            cb.setChecked(f in (df.get("merge") or ["pdf", "epub"]))
        for boxes, key, default in ((self.fmt_off_boxes, "official", self._official_pack_fmts()),
                                    (self.fmt_made_boxes, "xml", self._made_pack_fmts())):
            want = set(df.get(key) if df.get(key) is not None else default)
            for f, cb in boxes.items():
                cb.setChecked(f in want)
        x2p = c.get("xml2pdf", {}) or {}
        self.ed_x2p.setText(self._native_path(x2p.get("path", "")))
        self.ed_x2p_ebook.setText(self._native_path(
            x2p.get("cbeta_ebook") or str(PROJECT_ROOT / "cbeta_xml")))
        self._reload_preset_combo(keep=x2p.get("preset", ""))
        (self.rb_build_verify if x2p.get("verify_build") else self.rb_build_noverify).setChecked(True)
        self.sp_verify_maxdiff.setValue(max(0, min(50, int(x2p.get("verify_max_diff", 5) or 5))))
        self.sp_verify_difflines.setValue(max(0, min(50, int(x2p.get("verify_diff_lines", 5) or 5))))
        cover = c.setdefault("cover", {})
        self._migrate_series_imprint(cover)
        self.ed_organizer.setText(cover.get("organizer", "CBETA 整理"))
        self.ed_imprint.setText(cover.get("imprint", "CBETA 電子佛典自選叢書"))
        self.ed_date.setText(cover.get("date_text", "{date}"))
        self._set_mode(cover.get("mode", "print"))
        self.chk_cover_enabled.setChecked(bool(cover.get("enabled", True)))
        _en = cover.setdefault("edit_note", {"file": "", "enabled": False})
        self.ed_editnote.setText(_en.get("file", ""))
        self.chk_editnote_enabled.setChecked(bool(_en.get("enabled", False)))
        intro = cover.setdefault("intro", {})
        self.chk_intro_enabled.setChecked(bool(intro.get("enabled", True)))
        self.ed_intro_title.setText(intro.get("title", "说明"))
        self.ed_intro_note.setText(intro.get("note", "依 CBETA XML 自制"))
        _bl = cover.setdefault("bulei", {"enabled": True, "depth": 0, "layout": "lines",
                                          "sep": "·", "show_num": False, "titles": "none"})
        self.chk_bulei_show.setChecked(bool(_bl.get("enabled", True)))
        _ti = max(0, self.cb_bulei_titles.findData(_bl.get("titles", "none")))
        self.cb_bulei_titles.setCurrentIndex(_ti)
        try:
            _bd = int((_bl.get("depth", 0) or 0))
        except Exception:
            _bd = 0
        self.sp_bulei_depth.setValue(max(0, min(5, _bd)))
        _li = max(0, self.cb_bulei_layout.findData(_bl.get("layout", "lines")))
        self.cb_bulei_layout.setCurrentIndex(_li)
        self.ed_bulei_sep.setText(str(_bl.get("sep", "·") or "·"))
        self.chk_bulei_num.setChecked(bool(_bl.get("show_num", False)))
        sizes = cover.setdefault("sizes", {})
        for paper, sp in self.sp_body.items():
            sp.setValue(int(sizes.get(f"body_{paper}", {"a5":10,"a4":12,"16k":11,"32k":9}[paper])))
        try:
            _eb = int(sizes.get("editnote_body", 12) or 12)
        except Exception:
            _eb = 12
        self.sp_editnote_body.setValue(max(6, min(40, _eb)))
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
        self._sync_bg_colors(cover)
        images = cover.setdefault("images", {})
        for key, (chk, ed) in self.img_rows.items():
            info = images.setdefault(key, {"file": "", "enabled": True})
            chk.setChecked(bool(info.get("enabled", True)))
            ed.setText(info.get("file", ""))
            self._ensure_default_image(key, chk, ed)
        pdf_cfg = c.setdefault("pdf", {})
        self.sp_split_pdf.setValue(int(pdf_cfg.get("split_pages", 0) or 0))
        epub_cfg = c.setdefault("epub", {})
        self.sp_split_epub.setValue(int(epub_cfg.get("split_items", 0) or 0))
        self._sync_merge_defaults(c)
        styles = cover.setdefault("styles", {})
        _font_defaults = {"intro_summary": "C:/Windows/Fonts/simfang.ttf",
                          "editnote_title": "C:/Windows/Fonts/msyhbd.ttc",
                          "editnote_body": "C:/Windows/Fonts/simsun.ttc"}
        for key, ed in self.font_rows.items():
            cur = styles.get(key, {}).get("font", "") or _font_defaults.get(key, "")
            ed.setText(self._native_path(cur))
            self._check_font_row(key, ed)
        theme = c.setdefault("theme", {"mode": "system", "accent": "#8B4513"})
        self._set_radio(self.theme_radios, theme.get("mode", "system"), "system")
        self.ed_accent.setText(theme.get("accent", "#8B4513"))
        self._set_radio(self.lang_radios, c.get("language", "zh-Hans"), "zh-Hans")
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
        self.ed_app_font.setText(ui.get("app_font", "SimSun"))
        self.sp_app_font_size.setValue(int(ui.get("app_font_size") or 9))
        self.ed_supplement.setText(self._native_path(ui.get("supplement_ttf", "")))
        self._populate_filter_lists()

    # ---------- 页签：缓存 ----------
    def _tab_cache(self):
        w = QWidget()
        form = QFormLayout(w)
        self._cache_rows = {}
        from cbeta_publish.books import xml2pdf_bridge
        specs = [
            ("ebooks", "官方电子书缓存", lambda: self._cfg.get("official_ebooks_dir", "")),
            # 自制电子书：用 bridge 默认兜底（配置缺省也有值），保证能统计/清理
            ("xmlbooks", "自制电子书", lambda: str(xml2pdf_bridge.xml_books_dir(self._cfg))),
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
        # 更新频率（原在「数据/输出」）：目录/元数据后台检查周期
        interval_row = QWidget()
        _ir = QHBoxLayout(interval_row)
        _ir.setContentsMargins(0, 0, 0, 0)
        _ir.addWidget(QLabel("更新频率"))
        self.cb_interval = self._no_wheel_until_focused(QComboBox())
        self.cb_interval.addItems(["daily", "weekly", "monthly", "manual"])
        cur = self._cfg.get("update_interval", "weekly")
        if cur in ["daily", "weekly", "monthly", "manual"]:
            self.cb_interval.setCurrentText(cur)
        self.cb_interval.setToolTip("启动时是否后台检查目录/元数据更新：daily=每天一次 / "
                                    "weekly=每周 / monthly=每月 / manual=只手动检查")
        _ir.addWidget(self.cb_interval)
        _ir.addStretch()
        v.addWidget(interval_row)
        self.lbl_last_check = QLabel()
        v.addWidget(self.lbl_last_check)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["分类", "名称", "远端 URL", "本地文件", "状态"])
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.verticalHeader().setDefaultSectionSize(28)
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
        btn_r_orig = QPushButton("恢复原始（目录数据）")
        btn_r_orig.clicked.connect(lambda: self._restore_mulu("original"))
        btn_r_last = QPushButton("恢复上一次（目录数据）")
        btn_r_last.clicked.connect(lambda: self._restore_mulu("last"))
        h.addWidget(btn_check); h.addWidget(btn_r_orig); h.addWidget(btn_r_last); h.addStretch()
        v.addWidget(row)
        hint = QLabel("权威源为 cbdata/stable scope-selector（部类/朝代/作者）；更新前旧文件自动快照到 mulu/backup/last/。")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self._reload_update_table()
        return w

    @staticmethod
    def _ro_field(text: str) -> QLineEdit:
        # 只读文本框：内容可完整查看/选中拷贝（表格单元格会截断长 URL/路径）
        ed = QLineEdit(text)
        ed.setReadOnly(True)
        ed.setToolTip(f"{text}\n（只读，可选中拷贝）")
        ed.setCursorPosition(0)
        return ed

    def _reload_update_table(self):
        from cbeta_publish.books.remote_sources import SOURCES, local_path
        self.tbl.setRowCount(0)
        for key, cat, url, rel in SOURCES:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            p = local_path(rel)
            for c, val in enumerate([cat, key]):
                item = QTableWidgetItem(val)
                item.setToolTip(val)
                self.tbl.setItem(r, c, item)
            # URL / 本地文件：只读文本框（可查看/拷贝完整内容）
            self.tbl.setCellWidget(r, 2, self._ro_field(url))
            self.tbl.setCellWidget(r, 3, self._ro_field(str(p)))
            st = QTableWidgetItem("已就绪" if p.exists() else "缺失")
            st.setToolTip(f"{rel}")
            self.tbl.setItem(r, 4, st)
        self.tbl.resizeRowsToContents()
        self.tbl.setColumnWidth(0, 60)
        self.tbl.setColumnWidth(1, 130)
        self.tbl.setColumnWidth(4, 70)
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
    def _radio_row(self, items, cur, group_attr=None):
        """一组互斥单选：items=[(显示, 值)]；返回 (容器, QButtonGroup, {值: 单选})。"""
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        group = QButtonGroup(box)
        radios = {}
        for i, (label, value) in enumerate(items):
            rb = QRadioButton(label)
            rb.setProperty("value", value)
            lay.addWidget(rb)
            group.addButton(rb, i)
            radios[value] = rb
        lay.addStretch()
        for value, rb in radios.items():
            rb.setChecked(value == cur)
        if group_attr:
            setattr(self, group_attr, group)
        return box, group, radios

    @staticmethod
    def _radio_value(group, radios):
        btn = group.checkedButton()
        return btn.property("value") if btn is not None else ""

    @staticmethod
    def _set_radio(radios, value, default=""):
        rb = radios.get(value) or radios.get(default)
        if rb is None and radios:
            rb = next(iter(radios.values()))
        if rb is not None:
            rb.setChecked(True)

    def _tab_appearance(self):
        w = QWidget()
        form = QFormLayout(w)
        theme = self._cfg.setdefault("theme", {"mode": "system", "accent": "#8B4513"})
        self.theme_box, self.theme_group, self.theme_radios = self._radio_row(
            [("浅色", "light"), ("深色", "dark"), ("跟随系统", "system")],
            theme.get("mode", "system"))
        self.ed_accent = QLineEdit(theme.get("accent", "#8B4513"))
        self.lang_box, self.lang_group, self.lang_radios = self._radio_row(
            [("简体", "zh-Hans"), ("繁体", "zh-Hant"), ("English", "en")],
            self._cfg.get("language", "zh-Hans"))
        self.cb_tree_expand = self._no_wheel_until_focused(QComboBox())
        self.cb_tree_expand.addItems(["不展开", "展开1层", "展开2层", "展开3层", "全部展开"])
        ui = self._cfg.setdefault("ui", {})
        self.ed_app_font = QLineEdit(ui.get("app_font", "SimSun"))
        self.sp_app_font_size = self._no_wheel_until_focused(QSpinBox())
        self.sp_app_font_size.setRange(6, 24)
        self.sp_app_font_size.setValue(int(ui.get("app_font_size") or 9))
        srow = QWidget()
        sfh = QHBoxLayout(srow)
        sfh.setContentsMargins(0, 0, 0, 0)
        sfh.addWidget(self.ed_app_font, 1)
        sfh.addWidget(QLabel("字号"))
        sfh.addWidget(self.sp_app_font_size)
        self.ed_supplement = QLineEdit(self._native_path(ui.get("supplement_ttf", "")))
        sbtn = QPushButton("浏览…")
        sbtn.clicked.connect(lambda: self._pick_supplement())
        sup = QWidget()
        suph = QHBoxLayout(sup)
        suph.setContentsMargins(0, 0, 0, 0)
        suph.addWidget(self.ed_supplement, 1)
        suph.addWidget(sbtn)
        form.addRow("主题", self.theme_box)
        form.addRow("强调色", self.ed_accent)
        form.addRow("语言", self.lang_box)
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
    def _refresh_bg_btn_for(self, key):
        if key == "background":
            c = self._bg_color
            btn = self.btn_bg
        else:
            c = self._bg_colors[key]
            btn = self._bg_btns[key]
        btn.setStyleSheet(
            f"background-color: rgb({c.red()},{c.green()},{c.blue()});"
            f"border:1px solid #999; color: rgb({255-c.red()},{255-c.green()},{255-c.blue()});"
        )
        btn.setText(f"#{c.red():02X}{c.green():02X}{c.blue():02X}")

    def _refresh_bg_btn(self):
        self._refresh_bg_btn_for("background")

    def _pick_bg_for(self, key, title):
        if key == "background":
            cur = self._bg_color
        else:
            cur = self._bg_colors[key]
        c = QColorDialog.getColor(cur, self, title)
        if c.isValid():
            if key == "background":
                self._bg_color = c
            else:
                self._bg_colors[key] = c
                self._bg_custom.add(key)   # 单独选色后独立，不再跟随封面
            self._refresh_bg_btn_for(key)

    def _pick_bg(self):
        self._pick_bg_for("background", "封面背景色")

    def _pick_font(self, key, ed):
        # 起始目录：当前字体所在目录（无则系统字体目录）
        start = str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")
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
            ed.setText(self._native_path(f))
            self._check_font_row(key, ed)

    @staticmethod
    def _native_path(p):
        # 用当前系统的默认分隔符显示（Windows 为反斜杠）
        if not p:
            return ""
        try:
            return str(Path(p))
        except Exception:
            return p

    @staticmethod
    def _resolve_out_dir(p):
        """丛书输出目录：空则默认 collections_books；相对按工程根解析为全路径。"""
        p = (p or "").strip()
        if not p:
            return str(PROJECT_ROOT / "collections_books")
        pp = Path(p)
        return str(pp if pp.is_absolute() else PROJECT_ROOT / pp)

    #: 图片槽→编号：封面图=1.*，封底图=2.*（后缀不限）
    _IMG_NUM = {"buddha": "1", "weituo": "2"}
    #: 图片槽→默认文件：优先取该固定文件（存在才用），否则仍按编号找
    _IMG_DEFAULT_FILE = {"buddha": "B01.jpg", "weituo": "B02.jpg"}

    def _ensure_default_image(self, key, chk, ed):
        # 启用即选默认：勾选且路径空/失效时，先取 B01.jpg/B02.jpg，再找 1.*/2.*
        try:
            if not chk.isChecked():
                return
            cur = (ed.text() or "").strip()
            if cur and Path(cur).is_file():
                return
            hit = None
            fixed = IMAGES_DIR / self._IMG_DEFAULT_FILE.get(key, "")
            if fixed.name and fixed.is_file():
                hit = fixed
            if hit is None:
                from cbeta_publish.books.ebook_merger import find_numbered_image
                hit = find_numbered_image(IMAGES_DIR, self._IMG_NUM.get(key, key))
            if hit is not None:
                ed.setText(str(hit))
        except Exception:
            pass

    def _pick_editnote(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择说明 TXT 文件", "",
                                           "文本 (*.txt)")
        if f:
            self.ed_editnote.setText(f)

    def _pick_image(self, key, ed):
        f, _ = QFileDialog.getOpenFileName(self, f"选择{key}图片", str(IMAGES_DIR),
                                           "图片 (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.gif)")
        if not f:
            return
        try:
            from cbeta_publish.books.ebook_merger import COVER_IMAGE_SUFFIXES
            num = self._IMG_NUM.get(key, key)
            src = Path(f)
            suffix = src.suffix.lower()
            if suffix not in COVER_IMAGE_SUFFIXES:
                suffix = ".png"
            # 按编号落盘，同号其它后缀先清（保证 1.* / 2.* 唯一）
            for old in IMAGES_DIR.glob(f"{num}.*"):
                try:
                    if old.is_file() and old.suffix.lower() != suffix:
                        old.unlink()
                except OSError:
                    pass
            target = IMAGES_DIR / f"{num}{suffix}"
            shutil.copy2(str(src), str(target))
            ed.setText(str(target))
        except Exception as e:
            QMessageBox.warning(self, "失败", f"拷贝图片失败：{e}")

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
        # 数据目录（统一本地分隔符落盘）
        c["mulu_dir"] = self._native_path(self.ed_mulu.text().strip())
        c["collections_dir"] = self._native_path(self.ed_collections.text().strip())
        c["official_ebooks_dir"] = self._native_path(self.ed_ebooks.text().strip())
        c["official_library"] = {
            "root": self._native_path(self.ed_official_lib.text().strip()),
            "overrides": {f: ed.text().strip() for f, ed in self.lib_override_edits.items()
                          if ed.text().strip()},
        }
        try:
            from cbeta_publish.books import official_ebook_source as _oes
            _oes.refresh_library_map()
        except Exception:
            pass
        c["xml_to_ebooks_dir"] = self._native_path(self.ed_xmlbooks.text().strip()) \
            or str(PROJECT_ROOT / "cbeta_xml_ebooks")
        c["verify_dir"] = self._native_path(self.ed_verify.text().strip()) \
            or str(PROJECT_ROOT / "cbeta_verify")
        c["output_dir"] = self._native_path(self._resolve_out_dir(self.ed_output.text()))
        c["update_interval"] = self.cb_interval.currentText()
        c["default_source"] = "xml" if self.rb_src_made.isChecked() else "official"
        c["default_formats"] = {
            "merge": [f for f in ("pdf", "epub") if self.fmt_merge_boxes[f].isChecked()],
            "official": [f for f, b in self.fmt_off_boxes.items() if b.isChecked()],
            "xml": [f for f, b in self.fmt_made_boxes.items() if b.isChecked()],
        }
        c.setdefault("xml2pdf", {})
        # 旧逐项（page/font_lang/engine/vertical）照读兼容，不再写入/使用，preset 为准；
        # regen 生成策略已移除（合并/ZIP/导出恒仅缺，全部重生成用「重制」）
        for _k in ("page", "font_lang", "engine", "vertical", "preset_dir", "regen"):
            c["xml2pdf"].pop(_k, None)
        c["xml2pdf"].update({
            "path": self._native_path(self.ed_x2p.text().strip()),
            "cbeta_ebook": self._native_path(self.ed_x2p_ebook.text().strip())
            or str(PROJECT_ROOT / "cbeta_xml"),
            "preset": self.cb_preset.currentData() or "",
            "verify_build": self.rb_build_verify.isChecked(),
            "verify_max_diff": self.sp_verify_maxdiff.value(),
            "verify_diff_lines": self.sp_verify_difflines.value(),
        })
        # 封面/版式
        cover = c.setdefault("cover", {})
        cover["organizer"] = self.ed_organizer.text().strip()
        cover["imprint"] = self.ed_imprint.text().strip()
        cover["date_text"] = self.ed_date.text().strip()
        cover["edit_note"] = {"file": self.ed_editnote.text().strip(),
                              "enabled": self.chk_editnote_enabled.isChecked()}
        cover.pop("series", None)
        cover["mode"] = self._mode()
        cover["enabled"] = self.chk_cover_enabled.isChecked()
        cover.setdefault("intro", {})["enabled"] = self.chk_intro_enabled.isChecked()
        cover["intro"]["title"] = self.ed_intro_title.text().strip() or "说明"
        cover["intro"]["note"] = self.ed_intro_note.text().strip()
        cover["bulei"] = {"enabled": self.chk_bulei_show.isChecked(),
                          "depth": int(self.sp_bulei_depth.value()),
                          "layout": self.cb_bulei_layout.currentData() or "lines",
                          "sep": self.ed_bulei_sep.text().strip() or "·",
                          "show_num": self.chk_bulei_num.isChecked(),
                          "titles": self.cb_bulei_titles.currentData() or "none"}
        sizes = cover.setdefault("sizes", {})
        for paper, sp in self.sp_body.items():
            sizes[f"body_{paper}"] = sp.value()
        sizes["editnote_body"] = self.sp_editnote_body.value()
        margins = sizes.setdefault("margins", {})
        for paper, sides in self.sp_margins.items():
            margins[paper] = {side: sp.value() for side, sp in sides.items()}
        styles = cover.setdefault("styles", {})
        styles["background"] = {"color": [self._bg_color.red(), self._bg_color.green(), self._bg_color.blue()]}
        for _key in ("intro_background", "toc_background"):
            # 未单独选色（也不曾有显式值）则不写盘＝继续跟随封面
            if _key in self._bg_custom or _key in styles:
                _c = self._bg_colors[_key]
                styles[_key] = {"color": [_c.red(), _c.green(), _c.blue()]}
            else:
                styles.pop(_key, None)
        for key, ed in self.font_rows.items():
            styles.setdefault(key, {})["font"] = ed.text().strip()
        images = cover.setdefault("images", {})
        for key, (chk, ed) in self.img_rows.items():
            images[key] = {"file": ed.text().strip(), "enabled": chk.isChecked()}
        c.setdefault("pdf", {})["split_pages"] = self.sp_split_pdf.value()
        c.setdefault("epub", {})["split_items"] = self.sp_split_epub.value()
        c.setdefault("merge", {})["by_volume"] = (self._merge_mode_value() == "volume")
        c["merge"]["mode"] = self._merge_mode_value()
        c["merge"]["depth"] = int(self.sp_merge_depth.value())
        c["merge"]["name_template"] = self.ed_merge_name.text().strip() or "{coll}.{nn}.{seg}"
        # 外观
        c.setdefault("theme", {})["mode"] = self._radio_value(self.theme_group, self.theme_radios)
        c["theme"]["accent"] = self.ed_accent.text().strip()
        c["language"] = self._radio_value(self.lang_group, self.lang_radios)
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
        ui["app_font"] = self.ed_app_font.text().strip() or "SimSun"
        ui["app_font_size"] = self.sp_app_font_size.value()
        ui["supplement_ttf"] = self._native_path(self.ed_supplement.text().strip())
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