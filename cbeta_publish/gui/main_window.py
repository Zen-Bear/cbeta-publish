# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QSplitter, QSplitterHandle, QLabel, QPushButton, QToolButton, QLineEdit, QComboBox, QInputDialog, QMessageBox, QApplication, QTabWidget, QTextBrowser, QSizePolicy, QProgressDialog, QScrollArea, QGroupBox, QRadioButton, QButtonGroup
from PySide6.QtCore import Qt, QEvent, QTimer, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from pathlib import Path
import json, os, re

from cbeta_publish.catalog.bulei_parser import parse_bulei, parse_bulei_json
from cbeta_publish.catalog.sutra_service import SutraService
from cbeta_publish.catalog.mapping_service import MappingService
from cbeta_publish.creators.creator_service import CreatorService
from cbeta_publish.collection.category_manager import CategoryManager
from cbeta_publish.collection.tags_manager import TagsManager
from cbeta_publish.collection.collection_model import create_collection, slugify
from cbeta_publish.utils import text_util
from cbeta_publish.books import official_ebook_source
from cbeta_publish.catalog import work_id
from cbeta_publish.collection.collection_model import normalize_collection, write_index

WORK_RE = re.compile(r"[A-Z]+[0-9A-Za-z]+")
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "app.json"


class _PanelHandle(QSplitterHandle):
    # 分隔条上的收起/恢复按钮（操作其左侧的那一栏）
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._saved = None
        self._pidx = None      # 缓存本分隔条左侧栏索引（判定一次后固定）
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        def mk(text, tip, slot):
            b = QToolButton(self)
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setFixedSize(16, 18)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            return b
        v.addStretch()
        v.addWidget(mk("◀", "收起左侧栏", self._collapse))
        v.addWidget(mk("▶", "恢复左侧栏", self._restore))
        v.addStretch()

    def _left_index(self):
        # 判定本分隔条左侧的那一栏：取「右边缘」离分隔条「左边缘」最近的一栏，
        # 某栏折叠为 0 宽时该判据依然成立（用中心点比较会指错栏）。
        sp = self.splitter()
        if sp is None or sp.count() == 0:
            return 0
        horiz = sp.orientation() == Qt.Horizontal
        h = self.geometry()
        h_lo = h.left() if horiz else h.top()
        best, best_gap = 0, None
        for i in range(sp.count()):
            g = sp.widget(i).geometry()
            g_hi = (g.left() + g.width()) if horiz else (g.top() + g.height())
            gap = abs(g_hi - h_lo)
            if best_gap is None or gap < best_gap:
                best, best_gap = i, gap
        return best

    def _panel(self):
        # 只判定一次并缓存：栏被折叠成 0 宽后几何判定可能指错栏，导致
        # 「收起→恢复→再收起」第二次收起作用在别的栏（表现为按钮失效）。
        if self._pidx is None:
            self._pidx = self._left_index()
        return self._pidx

    def _collapse(self):
        sp = self.splitter()
        if sp is None:
            return
        k = self._panel()
        sizes = sp.sizes()
        if k >= len(sizes) or sizes[k] <= 0:
            return
        # 存整组宽度，恢复时原样写回（保证各栏回到收起前的位置）
        self._saved = list(sizes)
        sizes[k] = 0
        sp.setSizes(sizes)

    def _restore(self):
        sp = self.splitter()
        if sp is None:
            return
        k = self._panel()
        sizes = sp.sizes()
        if k >= len(sizes) or sizes[k] > 0:
            return
        if getattr(self, "_saved", None) and len(self._saved) == sp.count():
            # 原样恢复收起前的整组宽度（不受最小宽度重分配干扰）
            sp.setSizes(list(self._saved))
            return
        want = 300
        donor = k + 1 if k + 1 < sp.count() else k - 1
        sizes[donor] = max(120, sizes[donor] - want)
        sizes[k] = want
        sp.setSizes(sizes)


class _Splitter(QSplitter):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)

    def createHandle(self):
        return _PanelHandle(self.orientation(), self)


def _log_replace_last(view, html: str) -> bool:
    """把日志面板最后一段替换为 html（用于「下载 X ...」与「完成 X」合并成一行）。

    成功替换返回 True；面板为空（无可替换行）返回 False，由调用方改为追加。
    """
    from PySide6.QtGui import QTextCursor
    doc = view.document()
    if doc.blockCount() <= 1 and not doc.toPlainText().strip():
        return False
    # 只替换最后一段的文本（EndOfBlock 不含段落分隔符，避免与前一段合并）
    blk = doc.lastBlock()
    cur = QTextCursor(blk)
    cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
    cur.removeSelectedText()
    cur.insertHtml(html)
    return True


def apply_ui_fonts(ui: dict):
    """即时应用界面字体/字号与补充字型（设置保存后调用，无需重启）。"""
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    ui = ui or {}
    ttf = Path(ui.get("supplement_ttf") or "")
    if str(ttf) and ttf.exists():
        QFontDatabase.addApplicationFont(str(ttf))
    try:
        font_size = int(ui.get("app_font_size") or 9)
    except (TypeError, ValueError):
        font_size = 9
    app = QApplication.instance()
    if app is None:
        return
    font = QFont(str(ui.get("app_font") or "SimSun"), font_size)
    app.setFont(font)
    # 已存在的控件（尤其 QAbstractItemView 的 viewport：列表/表格/树/表头）
    # 不一定跟随 app 字体变化 → 显式刷新一遍（本工程无逐控件自定义字体，安全）
    for w in app.allWidgets():
        try:
            w.setFont(font)
            vp = w.viewport() if hasattr(w, "viewport") else None
            if vp is not None:
                vp.setFont(font)
        except Exception:
            pass


class _RadioBar(QWidget):
    """一排互斥单选，接口仿 QComboBox（currentText / currentTextChanged / setCurrentText）。

    便于把原来的下拉框原地换成单选按钮，调用方（含既有测试）无需改动。
    """
    currentTextChanged = Signal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._group = QButtonGroup(self)
        self._btns = []
        for i, name in enumerate(items):
            rb = QRadioButton(str(name))
            lay.addWidget(rb)
            self._group.addButton(rb, i)
            self._btns.append(rb)
        lay.addStretch()
        if self._btns:
            self._btns[0].setChecked(True)
        self._group.buttonClicked.connect(self._on_clicked)

    def _on_clicked(self, btn):
        if not self.signalsBlocked():
            self.currentTextChanged.emit(btn.text())

    def currentText(self):
        b = self._group.checkedButton()
        return b.text() if b is not None else ""

    def setCurrentText(self, text):
        for rb in self._btns:
            if rb.text() == text:
                was = rb.isChecked()
                rb.setChecked(True)
                if not was and not self.signalsBlocked():
                    self.currentTextChanged.emit(text)
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config=config
        self._config_path=config.get("_config_path") or CONFIG_PATH
        self.setWindowTitle("CBETA 发布管理器")
        # 启动窗口大小：二栏收窄（中栏隐藏，不需要那么宽）；三栏用默认宽度
        if (config.get("ui",{}) or {}).get("layout")=="two":
            self.resize(1000,720)
        else:
            self.resize(1240,720)
        mulu=Path(config["mulu_dir"])
        try:
            self.sutra = SutraService(mulu/"SutraList.json")
            self.mapping = MappingService(mulu/"sutra_mapping.txt")
            self.creator = CreatorService(mulu/"all-creators-with-alias.json", mulu/"creators-by-strokes-with-works.json")
        except Exception as e:
            print("service load fail", e)
        self._bulei_roots=[]
        self._workspace=[]     # 唯一内存目录（中栏「工作区」与左栏工作区面板共用）
        self._selected=set()   # 工作区勾选集合
        self._search_results=[]# 当前搜索结果（仅左栏结果视图用；不写入工作区）
        self._sort_mode="原始顺序"
        self._collections=[]
        self._coll_changed=False
        self._coll_originals={}
        self._changed_colls=set()
        self._last_coll_path=(config.get("ui",{}) or {}).get("last_collection") or None
        self._last_publish={}
        self._work_groups={}   # {work_id: 册标签}（从刊本树拖入时记录，供「按册分册」）
        self._left_search_active=False   # 左栏当前是否显示「搜索结果」（导航树被暂存）
        self._nav_stash=None   # 搜索结果占用左栏时暂存的导航树顶层项（供搜索/恢复）
        self._tmp_preset=None  # 「调整…」本次临时预设文件（不落盘；作用于 自制/合并 等）

        splitter=_Splitter(Qt.Horizontal)
        left=QWidget()
        lv=QVBoxLayout(left)
        self.nav_combo=_RadioBar(["部类","三藏","刊本","朝代","作者","丛书"])
        lv.addWidget(self.nav_combo)
        self.bulei_filter=QComboBox()
        self.bulei_filter.setEditable(True)
        self.bulei_filter.setPlaceholderText("全部部类（可输入筛选）")
        self.bulei_filter.addItem("全部部类", None)
        lv.addWidget(self.bulei_filter)
        # 三藏视图二级过滤：部类
        self.tripitaka_filter=QComboBox()
        self.tripitaka_filter.setToolTip("二级过滤：部类")
        self.tripitaka_filter.addItem("全部部类", None)
        lv.addWidget(self.tripitaka_filter)
        # 刊本视图二级过滤：刊本（一级目录本身）
        self.vol_filter=QComboBox()
        self.vol_filter.setToolTip("过滤：刊本")
        self.vol_filter.addItem("全部刊本", None)
        lv.addWidget(self.vol_filter)
        self.coll_filter=QComboBox()
        self.coll_filter.addItem("分类：全部", None)
        lv.addWidget(self.coll_filter)
        self.coll_tag_filter=QComboBox()
        self.coll_tag_filter.addItem("标签：全部", None)
        lv.addWidget(self.coll_tag_filter)
        # 作者排序：单选按钮（原下拉框）
        self.author_sort_row=QWidget()
        asr=QHBoxLayout(self.author_sort_row)
        asr.setContentsMargins(0,0,0,0)
        self.author_sort_group=QButtonGroup(self.author_sort_row)
        self.author_radios={}
        for _i, _name in enumerate(["拼音排序","笔画排序","朝代排序"]):
            rb=QRadioButton(_name)
            asr.addWidget(rb)
            self.author_sort_group.addButton(rb, _i)
            self.author_radios[_name]=rb
        self.author_radios["拼音排序"].setChecked(True)
        asr.addStretch()
        lv.addWidget(self.author_sort_row)
        self.author_filter=QComboBox()
        self.author_filter.setEditable(True)
        self.author_filter.setPlaceholderText("笔画：全部")
        lv.addWidget(self.author_filter)
        self.search=QLineEdit()
        self.search.setPlaceholderText("经名/作者/经号（全局）")
        search_row=QWidget()
        sh=QHBoxLayout(search_row)
        sh.setContentsMargins(0,0,0,0)
        sh.addWidget(QLabel("搜索："))
        sh.addWidget(self.search, 1)
        self.btn_clear_search=QPushButton("✕")
        self.btn_clear_search.setFixedWidth(28)
        self.btn_clear_search.setToolTip("清除搜索与过滤条件，显示完整目录")
        self.btn_clear_search.clicked.connect(self._clear_search)
        sh.addWidget(self.btn_clear_search)
        self.btn_ws_add=QPushButton("＋")
        self.btn_ws_add.setFixedWidth(28)
        self.btn_ws_add.setToolTip("把当前搜索结果一键加入工作区")
        self.btn_ws_add.clicked.connect(self._ws_add_search)
        sh.addWidget(self.btn_ws_add)
        self.btn_workspace=QPushButton("工作区")
        self.btn_workspace.setCheckable(True)
        self.btn_workspace.setToolTip("显示工作区面板（目录面板随之隐藏）；搜索结果可一键加入，右栏移除的书也会到这里")
        self.btn_workspace.toggled.connect(self._toggle_workspace)
        sh.addWidget(self.btn_workspace)
        lv.addWidget(search_row)
        self.tree=QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.mimeData = self._tree_mimeData   # 提供 text/plain（默认只有内部模型格式）
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setMinimumWidth(260)
        # 选中/悬停（与中栏书籍列表完全一致）；书叶文字黑色见 _expand_tree
        self.tree.setMouseTracking(True)
        self.tree.setStyleSheet(
            "QTreeWidget::item:selected { background: #bbdefb; color: #000; }"
            "QTreeWidget::item:hover { background: #fff3c4; }"
            "QTreeWidget::item:selected:hover { background: #90caf9; color: #000; }")
        lv.addWidget(self.tree)
        # 工作区面板：与目录树二选一显示（二栏时显示；三栏时中栏就是工作区，按钮隐藏）
        self.ws_page=QWidget()
        wv=QVBoxLayout(self.ws_page)
        wv.setContentsMargins(0,0,0,0)
        ws_top=QWidget()
        wth=QHBoxLayout(ws_top)
        wth.setContentsMargins(0,0,0,0)
        self.ws_count=QLabel("工作区（0 部）")
        wth.addWidget(self.ws_count)
        wth.addStretch()
        wv.addWidget(ws_top)
        # 与中栏一致的控制行：排序 + 全选/不选/加入已选/全删（共用同一批 handler）
        ws_ctl=QWidget()
        wch=QHBoxLayout(ws_ctl)
        wch.setContentsMargins(0,0,0,0)
        self.ws_sort_combo=QComboBox()
        self.ws_sort_combo.addItems(["原始顺序","经号排序","经名排序"])
        self.ws_sort_combo.currentTextChanged.connect(self._set_sort_mode)
        wch.addWidget(self.ws_sort_combo)
        self.ws_btn_all=QPushButton("全选")
        self.ws_btn_none=QPushButton("不选")
        self.ws_btn_none.setToolTip("取消全部勾选（不删除书籍）")
        self.ws_btn_add_sel=QPushButton("加入已选")
        self.ws_btn_clear_list=QPushButton("全删")
        self.ws_btn_clear_list.setToolTip("清空工作区")
        for _b, _fn in ((self.ws_btn_all, self._select_all), (self.ws_btn_none, self._clear_all),
                        (self.ws_btn_add_sel, self._add_selected_to_coll),
                        (self.ws_btn_clear_list, self._ws_clear)):
            _b.clicked.connect(_fn)
            wch.addWidget(_b)
        wch.addStretch()
        wv.addWidget(ws_ctl)
        self.ws_tree=QTreeWidget()
        self.ws_tree.setHeaderHidden(True)
        self.ws_tree.setDragEnabled(True)
        self.ws_tree.setAcceptDrops(True)
        self.ws_tree.mimeData = self._tree_mimeData   # 与目录树同格式，可拖入右栏
        self.ws_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.ws_tree.setMinimumWidth(260)
        self.ws_tree.setMouseTracking(True)
        self.ws_tree.setStyleSheet(
            "QTreeWidget::item:selected { background: #bbdefb; color: #000; }"
            "QTreeWidget::item:hover { background: #fff3c4; }"
            "QTreeWidget::item:selected:hover { background: #90caf9; color: #000; }")
        wv.addWidget(self.ws_tree)
        self.ws_page.setVisible(False)
        lv.addWidget(self.ws_page)
        self.lbl_hint=QLabel("")
        self.lbl_hint.setStyleSheet("color: gray;")
        self.lbl_hint.setWordWrap(True)
        lv.addWidget(self.lbl_hint)
        splitter.addWidget(left)

        mid=QWidget()
        mid.setMinimumWidth(280)
        self.mid=mid
        mv=QVBoxLayout(mid)
        mid_top=QWidget()
        mth=QHBoxLayout(mid_top)
        mth.setContentsMargins(0,0,0,0)
        mth.addWidget(QLabel("工作区"))
        self.sort_combo=QComboBox()
        self.sort_combo.addItems(["原始顺序","经号排序","经名排序"])
        mth.addWidget(self.sort_combo)
        mth.addStretch()
        self.lbl_sel_count=QLabel("已选 0 部")
        mth.addWidget(self.lbl_sel_count)
        mv.addWidget(mid_top)
        mid_top2=QWidget()
        mth2=QHBoxLayout(mid_top2)
        mth2.setContentsMargins(0,0,0,0)
        self.btn_all=QPushButton("全选")
        self.btn_clear=QPushButton("不选")
        self.btn_clear.setToolTip("取消全部勾选（不删除书籍）")
        self.btn_add_sel=QPushButton("加入已选")
        self.btn_clear_list=QPushButton("全删")
        self.btn_clear_list.setToolTip("清空工作区")
        mth2.addWidget(self.btn_all); mth2.addWidget(self.btn_clear); mth2.addWidget(self.btn_add_sel); mth2.addWidget(self.btn_clear_list)
        mth2.addStretch()
        mv.addWidget(mid_top2)
        self.list=QListWidget()
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setAcceptDrops(True)
        self.list.setDefaultDropAction(Qt.MoveAction)
        # 选中高亮增强
        self.list.setStyleSheet("QListWidget::item:selected { background: #bbdefb; color: #000; } QListWidget::item:hover { background: #fff3c4; } QListWidget::item:selected:hover { background: #90caf9; color: #000; }")
        self.list.setMinimumWidth(280)
        mv.addWidget(self.list)
        self.detail=QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        splitter.addWidget(mid)

        right=QWidget()
        right.setMinimumWidth(300)
        rv=QVBoxLayout(right)
        rh=QHBoxLayout()
        rh.addWidget(QLabel("丛书"))
        self.coll_cat_filter=QComboBox()
        self.coll_cat_filter.setToolTip("按分类过滤下方丛书列表（与左栏目录一致）")
        rh.addWidget(self.coll_cat_filter)
        self.btn_cat_mgr=QPushButton("分类管理")
        self.btn_cat_mgr.setToolTip("分类管理：新建/改名/删除分类")
        rh.addWidget(self.btn_cat_mgr)
        self.btn_tag_mgr=QPushButton("标签管理")
        self.btn_tag_mgr.setToolTip("标签管理：新建/改名/删除标签（横切维度）")
        rh.addWidget(self.btn_tag_mgr)
        rh.addStretch()
        rv.addLayout(rh)
        self.coll_combo=QComboBox()
        self.coll_combo.setToolTip("丛书缓存 + 丛书列表（上方分类下拉可过滤）")
        rv.addWidget(self.coll_combo)
        mgmt=QWidget()
        mh=QHBoxLayout(mgmt)
        mh.setContentsMargins(0,0,0,0)
        self.btn_blank=QPushButton("空白")
        self.btn_blank.setToolTip("选择空白工作丛书（不存在则创建）")
        self.btn_save=QPushButton("保存")
        self.btn_save.setToolTip("保存所有未保存的丛书改动（去除星号）")
        self.btn_saveas=QPushButton("另存")
        self.btn_saveas.setToolTip("当前丛书改名、选择分类并保存")
        self.btn_restore=QPushButton("恢复")
        self.btn_restore.setToolTip("恢复当前丛书到上次保存时的书单，并取消星号")
        self.btn_delete=QPushButton("删除")
        self.btn_delete.setToolTip("删除当前丛书")
        self.btn_tags=QPushButton("标签…")
        self.btn_tags.setToolTip("为当前丛书设置标签（可多选）")
        mh.addWidget(self.btn_blank); mh.addWidget(self.btn_save); mh.addWidget(self.btn_saveas); mh.addWidget(self.btn_restore); mh.addWidget(self.btn_delete)
        mh.addWidget(self.btn_tags)
        mh.addStretch()
        rv.addWidget(mgmt)
        self.coll_list=QListWidget()
        self.coll_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.coll_list.setMinimumWidth(300)
        self.coll_list.setDragDropMode(QListWidget.DragDrop)
        self.coll_list.setDefaultDropAction(Qt.MoveAction)
        self.coll_list.setAcceptDrops(True)
        self.coll_list.setStyleSheet("QListWidget::item:selected { background: #bbdefb; color: #000; } QListWidget::item:hover { background: #fff3c4; } QListWidget::item:selected:hover { background: #90caf9; color: #000; }")
        rv.addWidget(self.coll_list)
        self.lbl_coll_info=QLabel("未选择丛书")
        self.lbl_coll_info.setTextFormat(Qt.RichText)
        self.lbl_coll_info.setWordWrap(True)
        self.lbl_coll_info.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.lbl_coll_info.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        btn_box=QWidget()
        hb=QHBoxLayout(btn_box)
        self.btn_remove=QPushButton("移除")
        self.btn_up=QPushButton("↑")
        self.btn_up.setFixedWidth(36)
        self.btn_up.setToolTip("上移选中（Alt+↑）")
        self.btn_down=QPushButton("↓")
        self.btn_down.setFixedWidth(36)
        self.btn_down.setToolTip("下移选中（Alt+↓）")
        self.btn_coll_sel_all=QPushButton("全选")
        self.btn_coll_sel_all.setToolTip("选中并勾选右栏全部书籍")
        self.btn_coll_sel_none=QPushButton("不选")
        self.btn_coll_sel_none.setToolTip("取消右栏全部选中与勾选（不删除书籍）")
        hb.addWidget(self.btn_up); hb.addWidget(self.btn_down)
        hb.addWidget(self.btn_coll_sel_all); hb.addWidget(self.btn_coll_sel_none)
        hb.addStretch()
        hb.addWidget(self.btn_remove)
        rv.addWidget(btn_box)
        publish_group = QGroupBox("发布")
        pg = QVBoxLayout(publish_group)
        pg.setContentsMargins(6, 6, 6, 6)
        pg.setSpacing(4)
        fmt_box=QWidget()
        fh=QHBoxLayout(fmt_box)
        fh.setContentsMargins(0,0,0,0)
        fh.addWidget(QLabel("格式:"))
        from PySide6.QtWidgets import QCheckBox
        from PySide6.QtGui import QIcon
        icon_dir=Path(__file__).parent / "theme" / "icons"
        self.chk_pdf=QCheckBox(" pdf")
        self.chk_pdf.setIcon(QIcon(str(icon_dir/"pdf.png")))
        self.chk_pdf.setChecked(True)
        self.chk_epub=QCheckBox(" epub")
        self.chk_epub.setIcon(QIcon(str(icon_dir/"epub.png")))
        fh.addWidget(self.chk_pdf); fh.addWidget(self.chk_epub)
        fh.addStretch()
        self.lbl_pack_hint=QLabel("（其它格式用ZIP/导出）")
        self.lbl_pack_hint.setStyleSheet("color: gray")
        fh.addWidget(self.lbl_pack_hint)
        pg.addWidget(fmt_box)
        # 来源 + 预设：一套丛书可按官方或自制合并，整批统一
        src_box=QWidget()
        sh=QHBoxLayout(src_box)
        sh.setContentsMargins(0,0,0,0)
        sh.addWidget(QLabel("来源:"))
        self.src_group=QButtonGroup(src_box)
        self.rb_official=QRadioButton("官方")
        self.rb_official.setToolTip("从 CBETA 官方下载成品电子书后合并")
        self.rb_made=QRadioButton("自制")
        self.rb_made.setToolTip("电子书由程序根据官方 XML 制作（经 xml2pdf 生成）后再合并")
        for _i, _rb in enumerate((self.rb_official, self.rb_made)):
            sh.addWidget(_rb)
            self.src_group.addButton(_rb, _i)
        pg.addWidget(src_box)
        preset_box=QWidget()
        ph=QHBoxLayout(preset_box)
        ph.setContentsMargins(0,0,0,0)
        self.lbl_preset=QLabel("预设:")
        ph.addWidget(self.lbl_preset)
        self.cb_preset=QComboBox()
        self.cb_preset.setToolTip("自制书的 xml2pdf 预设（预设目录下的 *.json，出厂默认=对面默认）")
        self.cb_preset.setMinimumWidth(140)
        ph.addWidget(self.cb_preset, 1)
        self.btn_preset_edit=QPushButton("调整…")
        self.btn_preset_edit.setToolTip("打开 xml2pdf 选项对话框调整，可覆盖保存或另存为新预设")
        self.btn_preset_edit.setFixedWidth(64)
        ph.addWidget(self.btn_preset_edit)
        pg.addWidget(preset_box)
        self.rb_regen_missing=QRadioButton("仅缺")
        self.rb_regen_missing.setToolTip("合并/ZIP/导出 时：已有自制书直接复用，只生成缺少的（推荐）")
        self.rb_regen_all=QRadioButton("全部")
        self.rb_regen_all.setToolTip("合并/ZIP/导出 时：忽略已有自制书，全部重新生成（改过预设后用）")
        self.regen_box=QWidget()
        self.regen_group=QButtonGroup(self.regen_box)
        rg_h=QHBoxLayout(self.regen_box)
        rg_h.setContentsMargins(0,0,0,0)
        rg_h.setSpacing(2)
        rg_h.addWidget(QLabel("（"))
        for _i, _rb in enumerate((self.rb_regen_missing, self.rb_regen_all)):
            rg_h.addWidget(_rb)
            self.regen_group.addButton(_rb, _i)
        rg_h.addWidget(QLabel("）"))
        publish_box=QWidget()
        hb2=QHBoxLayout(publish_box)
        hb2.setContentsMargins(0,0,0,0)
        self.btn_download=QPushButton("下载/更新")
        self.btn_download.setToolTip("下载/更新官方电子书（来源=官方时）")
        self.btn_make=QPushButton("自制")
        self.btn_make.setToolTip("生成缺失的自制电子书（已有产物直接复用）")
        self.btn_remake=QPushButton("重制")
        self.btn_remake.setToolTip("重新生成全部自制电子书（忽略已有产物）")
        self.btn_merge=QPushButton("合并")
        self.btn_merge.setToolTip("PDF/ePub合并成一个文件（单一格式，允许分册）")
        self.btn_zip=QPushButton("ZIP")
        self.btn_zip.setToolTip("ZIP 打包")
        self.btn_export=QPushButton("导出")
        self.btn_export.setToolTip("拷贝到指定目录")
        hb2.addWidget(self.btn_merge); hb2.addWidget(self.btn_zip); hb2.addWidget(self.btn_export)
        hb2.addWidget(self.btn_download); hb2.addWidget(self.btn_make); hb2.addWidget(self.btn_remake)
        hb2.addStretch()
        pg.addWidget(publish_box)
        # 「仅缺/全部」留在来源行、紧跟「自制」单选之后（自制/重制按钮在发布行）
        sh.addWidget(self.regen_box)
        sh.addStretch()
        self._sync_source_preset_ui()   # 依赖上面按钮存在（来源=自制时换按钮）
        rv.addWidget(publish_group)
        cache_box=QWidget()
        ch=QHBoxLayout(cache_box)
        ch.setContentsMargins(0,0,0,0)
        from cbeta_publish.books import xml2pdf_bridge as _xb
        def _dir_label(getter):
            # 目录短名显示，悬停看全路径，点击打开（路径经 getter 动态取，设置改后刷新）
            lb=QLabel()
            lb.setStyleSheet("color:#0645AD; text-decoration:underline;")
            lb.setCursor(Qt.PointingHandCursor)
            def _refresh():
                p=Path(getter())
                lb.setText(Path(p).name or str(p))
                lb.setToolTip(f"{p}\n点击在文件浏览器中打开")
            lb.refresh=_refresh
            def _open(e):
                try:
                    from PySide6.QtGui import QDesktopServices
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(getter()).resolve())))
                except Exception as ex:
                    print(ex)
            lb.mousePressEvent=_open
            _refresh()
            return lb
        ch.addWidget(QLabel("E书目录:"))
        ch.addWidget(QLabel("官方"))
        self.lbl_cache_dir=_dir_label(lambda: official_ebook_source.official_books_dir(self.config))
        ch.addWidget(self.lbl_cache_dir)
        ch.addWidget(QLabel("自制"))
        self.lbl_xml_dir=_dir_label(lambda: _xb.xml_books_dir(self.config))
        ch.addWidget(self.lbl_xml_dir)
        ch.addWidget(QLabel("丛书"))
        self.lbl_out_dir=_dir_label(lambda: self._out_dir())
        ch.addWidget(self.lbl_out_dir)
        ch.addStretch()
        rv.addWidget(cache_box)
        # 右下页签：① 书籍信息 ② 丛书信息（原「下载记录」页签删除，下载改为弹窗进度）
        self.tab_bottom=QTabWidget()
        from PySide6.QtWidgets import QScrollArea
        book_page=QWidget()
        book_layout=QVBoxLayout(book_page)
        book_layout.setContentsMargins(0,0,0,0)
        self.detail_scroll=QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QScrollArea.NoFrame)
        self.detail_scroll.setWidget(self.detail)
        book_layout.addWidget(self.detail_scroll)
        self.tab_bottom.addTab(book_page, "书籍信息")
        info_page=QWidget()
        info_layout=QVBoxLayout(info_page)
        info_layout.setContentsMargins(0,0,0,0)
        self.info_scroll=QScrollArea()
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setFrameShape(QScrollArea.NoFrame)
        self.info_scroll.setWidget(self.lbl_coll_info)
        info_layout.addWidget(self.info_scroll)
        self.tab_bottom.addTab(info_page, "丛书信息")
        self.btn_tab_toggle=QPushButton("▾")
        self.btn_tab_toggle.setFixedWidth(28)
        self.btn_tab_toggle.setToolTip("最小化/恢复下方窗格")
        self.btn_tab_toggle.clicked.connect(self._toggle_tab_pane)
        self.tab_bottom.setCornerWidget(self.btn_tab_toggle, Qt.TopRightCorner)
        self._tab_expanded=True
        self._tab_full_h=0
        QTimer.singleShot(0, self._fix_tab_height)
        rv.addWidget(self.tab_bottom)
        splitter.addWidget(right)
        splitter.setSizes([400,360,360])
        splitter.setHandleWidth(18)
        for _i in range(3):
            splitter.setCollapsible(_i, True)
        # 窗口变宽时各栏等比扩大（不固定某栏吸收）
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 0)
        self.setCentralWidget(splitter)
        self._splitter=splitter
        self._build_menu()

        self.nav_combo.currentTextChanged.connect(self._on_nav_changed)
        self.bulei_filter.currentIndexChanged.connect(self._on_bulei_filter)
        self.tripitaka_filter.currentIndexChanged.connect(self._on_tripitaka_filter)
        self.vol_filter.currentIndexChanged.connect(self._on_vol_filter)
        self.author_filter.currentIndexChanged.connect(self._on_author_filter)
        self.coll_filter.currentIndexChanged.connect(self._on_coll_filter)
        self.author_sort_group.buttonClicked.connect(lambda *_: self._refresh_author_tree())
        self.sort_combo.currentTextChanged.connect(self._set_sort_mode)
        self.tree.itemClicked.connect(self._on_tree_preview)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_click)
        # 工作区树：点书显示信息（同目录树）、双击加入右栏、可拖入右栏；
        # 右栏可拖入工作区 = 移除（书自然流入工作区）
        self.ws_tree.itemClicked.connect(self._on_tree_preview)
        self.ws_tree.itemDoubleClicked.connect(self._on_ws_double_click)
        self.ws_tree.itemChanged.connect(self._on_ws_item_changed)
        self.ws_tree.keyPressEvent = lambda e: self._ws_key_press(e)
        self.ws_tree.dragEnterEvent = lambda e: e.acceptProposedAction()
        self.ws_tree.dragMoveEvent = lambda e: self._drop_move(e, self.ws_tree)
        self.ws_tree.dropEvent = lambda e: self._ws_drop(e)
        self.list.itemChanged.connect(self._on_list_changed)
        self.list.itemClicked.connect(self._on_list_detail)
        self.list.itemDoubleClicked.connect(self._on_list_double_add)
        self.list.keyPressEvent = lambda e: self._list_key_press(e)
        self.list.dragEnterEvent = lambda e: self._list_drag_enter(e)
        self.list.dragMoveEvent = lambda e: self._drop_move(e, self.list)
        self.list.dropEvent = lambda e: self._list_drop(e)
        self.btn_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_clear_list.clicked.connect(self._ws_clear)
        self.btn_add_sel.clicked.connect(self._add_selected_to_coll)
        self.btn_cat_mgr.clicked.connect(self._category_manager_dialog)
        self.btn_tag_mgr.clicked.connect(self._tag_manager_dialog)
        self.btn_tags.clicked.connect(self._edit_coll_tags)
        self.coll_tag_filter.currentIndexChanged.connect(self._on_coll_tag_filter)
        self.btn_blank.clicked.connect(self._new_blank_collection)
        self.btn_delete.clicked.connect(self._delete_collection)
        self.btn_save.clicked.connect(self._save_collections)
        self.btn_restore.clicked.connect(self._restore_collection)
        self.btn_saveas.clicked.connect(self._save_as_collection)
        self.btn_remove.clicked.connect(self._remove_from_coll)
        self.btn_coll_sel_all.clicked.connect(self._coll_select_all)
        self.btn_coll_sel_none.clicked.connect(self._coll_clear_checks)
        self.btn_up.clicked.connect(lambda: self._move_coll_selection(-1))
        self.btn_down.clicked.connect(lambda: self._move_coll_selection(1))
        sc_up=QShortcut(QKeySequence("Alt+Up"), self.coll_list)
        sc_up.setContext(Qt.WidgetWithChildrenShortcut)
        sc_up.activated.connect(lambda: self._move_coll_selection(-1))
        sc_down=QShortcut(QKeySequence("Alt+Down"), self.coll_list)
        sc_down.setContext(Qt.WidgetWithChildrenShortcut)
        sc_down.activated.connect(lambda: self._move_coll_selection(1))
        self.btn_download.clicked.connect(self._on_download_button)
        self.btn_make.clicked.connect(lambda: self._on_make_button(False))
        self.btn_remake.clicked.connect(lambda: self._on_make_button(True))
        self.btn_merge.clicked.connect(self._merge)
        self.btn_zip.clicked.connect(self._zip)
        self.btn_export.clicked.connect(self._export)
        self.src_group.buttonClicked.connect(self._on_source_changed)
        self.regen_group.buttonClicked.connect(self._on_regen_changed)
        self.cb_preset.currentIndexChanged.connect(self._on_preset_changed)
        self.btn_preset_edit.clicked.connect(self._edit_preset)
        self.search.textChanged.connect(self._on_search)
        self.search.returnPressed.connect(lambda: self._on_search(self.search.text()))
        self.coll_combo.currentTextChanged.connect(self._on_combo_changed)
        self.coll_cat_filter.currentIndexChanged.connect(self._on_cat_filter_changed)
        self.coll_list.itemClicked.connect(self._on_coll_item_detail)
        self.coll_list.itemDoubleClicked.connect(self._on_coll_double_open)
        self.coll_list.itemSelectionChanged.connect(self._refresh_coll_text_colors)
        try:
            self.coll_list.model().rowsMoved.connect(self._on_coll_reordered)
        except: pass
        self.coll_list.dragEnterEvent = lambda e: self._coll_drag_enter(e)
        self.coll_list.dragMoveEvent = lambda e: self._drop_move(e, self.coll_list)
        self.coll_list.dropEvent = lambda e: self._coll_drop(e)
        self.coll_list.viewport().installEventFilter(self)
        self.chk_pdf.stateChanged.connect(self._load_coll_works)
        self.chk_epub.stateChanged.connect(self._load_coll_works)
        self.lbl_coll_info.linkActivated.connect(self._open_publish_link)
        self.tree.dragEnterEvent = lambda e: self._tree_drag_enter(e)
        self.tree.dragMoveEvent = lambda e: self._drop_move(e, self.tree)
        self.tree.dropEvent = lambda e: self._tree_drop(e)

        self._load_bulei()
        self._load_collections()
        # 有上次工作的丛书则保持选中；否则选中空白丛书
        self._ensure_blank_working(select=not bool(self._last_coll_path))
        # 繁简搜索：启动时生成简体标题缓存
        from cbeta_publish.utils import text_util
        text_util.init()
        self._title_s2={}
        try:
            def walk_b(nodes):
                for n in nodes:
                    for w in WORK_RE.findall(n.title):
                        if len(w)>=4 and (self.sutra.title_of(w)!=w or self.mapping.work_exists(w)):
                            t=self.sutra.title_of(w)
                            m=(self.mapping.resolve(w) or {}).get("name","")
                            self._title_s2[w]=(text_util.to_simplified(t), text_util.to_simplified(m))
                    walk_b(n.children)
            walk_b(self._bulei_roots)
        except Exception as e:
            print("s2 cache fail", e)
        # 拼音序作者列表：启动时预生成，切换即时显示（避免拼音排序卡顿）
        self._authors_pinyin_sorted=None
        # 作者朝代排序：work→朝代 映射缓存
        self._work_dyn=None
        self._dyn_order=[]
        try:
            _data=self.creator.strokes
            _groups=_data[0].get("children",[]) if (_data and len(_data)==1 and len(_data[0].get("children",[]))>=20) else _data
            _all=[]
            for g in _groups:
                for su in g.get("children",[]):
                    for a in su.get("children",[]):
                        _all.append(a)
            _all.sort(key=lambda x: self._pinyin_key(x.get("title","")))
            self._authors_pinyin_sorted=_all
        except Exception as e:
            print("pinyin cache fail", e)
        self._on_nav_changed(self.nav_combo.currentText())
        self._apply_layout()          # 布局：三栏/二栏（ui.layout）
        # 目录更新：按 update_interval 到期后台静默检查（不阻塞启动）
        self._upd_worker=None
        QTimer.singleShot(3000, self._maybe_check_update)

    def _maybe_check_update(self):
        try:
            interval=self.config.get("update_interval","weekly")
            if interval=="manual":
                return
            meta_path=Path(self.config["mulu_dir"])/"cache"/"meta.json"
            meta=json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            last=meta.get("last_check")
            days={"daily":1,"weekly":7,"monthly":30}.get(interval,7)
            if last:
                from datetime import datetime, timedelta
                try:
                    if datetime.now()-datetime.fromisoformat(last) < timedelta(days=days):
                        return
                except Exception:
                    pass
            from cbeta_publish.books.remote_sources import SOURCES
            from cbeta_publish.books.update_worker import UpdateWorker
            self._upd_worker=UpdateWorker(meta_path, SOURCES, Path(self.config["mulu_dir"])/"backup", do_update=False)
            self._upd_worker.checked.connect(self._on_update_checked)
            self._upd_worker.start()
        except Exception as e:
            print("maybe check update fail", e)

    def _on_update_checked(self, changed):
        if not changed:
            return
        ret=QMessageBox.question(self, "目录更新",
                                 f"检测到 {len(changed)} 个目录数据源有更新，是否立即更新？\n（重启后生效）",
                                 QMessageBox.Yes | QMessageBox.No)
        if ret!=QMessageBox.Yes:
            return
        from cbeta_publish.books.remote_sources import SOURCES
        from cbeta_publish.books.update_worker import UpdateWorker
        meta_path=Path(self.config["mulu_dir"])/"cache"/"meta.json"
        self._upd_worker=UpdateWorker(meta_path, SOURCES, Path(self.config["mulu_dir"])/"backup", do_update=True)
        self._upd_worker.updated.connect(self._on_update_done)
        self._upd_worker.start()

    def _on_update_done(self, result):
        upd=[k for k,v in (result or {}).items() if v=="updated"]
        fail=[k for k,v in (result or {}).items() if v=="failed"]
        QMessageBox.information(self, "目录更新", f"已更新 {len(upd)} 项，失败 {len(fail)} 项。\n重启后生效。")

    def showEvent(self, e):
        super().showEvent(e)
        # 首次显示后重新应用分栏宽度（布局前 setSizes 会失效）；二栏=隐藏中栏
        try:
            if self._layout_mode()=="two":
                self.mid.setVisible(False)
            else:
                self.mid.setVisible(True)
                self._splitter.setSizes([400,360,360])
        except Exception:
            pass
        if not getattr(self, "_focused_once", False):
            self._focused_once=True
            try:
                self.search.setFocus()
            except Exception:
                pass

    def _layout_mode(self):
        return (self.config.get("ui",{}) or {}).get("layout","three")

    def _apply_layout(self, layout=None):
        """应用布局：three=三栏；two=真二栏（隐藏中栏）。

        二栏用 setVisible(False) 隐藏中栏（QSplitter 会一并隐藏其分隔条，
        不会留下可拖动/无效的收起按钮）。中栏与左栏工作区面板是同一份数据
        （`_workspace`），切布局只切显示，不做数据搬运。
        「工作区/目录区」按钮只在二栏显示（三栏中栏就是工作区）。
        """
        if layout is None:
            layout=self._layout_mode()
        else:
            # 显式传入时同步配置并落盘，保证下次启动沿用
            self.config.setdefault("ui", {})["layout"]=layout
            self._persist_ui_layout()
        sp=getattr(self, "_splitter", None)
        if sp is None or sp.count()<3:
            return
        for _a, _lay in ((getattr(self, "act_three", None), "three"),
                         (getattr(self, "act_two", None), "two")):
            if _a is not None:
                _a.blockSignals(True)
                _a.setChecked(_lay==layout)
                _a.blockSignals(False)
        if layout=="two":
            if self.mid.isVisible():
                self._three_sizes=list(sp.sizes())
            self.mid.setVisible(False)
            self.btn_workspace.setVisible(True)
        else:
            want=getattr(self, "_three_sizes", None) if not self.mid.isVisible() else None
            self.mid.setVisible(True)
            if want and len(want)==sp.count() and want[1]>0:
                sp.setSizes(list(want))
            # 三栏没有左栏工作区按钮：强制回到目录面板
            if self.btn_workspace.isChecked():
                self.btn_workspace.setChecked(False)
            self.btn_workspace.setVisible(False)
            self.ws_page.setVisible(False)
            self.tree.setVisible(True)
        self._refresh_ws_views()
        self._render_search_to_left()

    def _fix_tab_height(self):
        # 下方页签高度固定（≈原「下载记录」高），切页时上面元素不再伸缩
        try:
            bar=self.tab_bottom.tabBar().height() or self.tab_bottom.tabBar().sizeHint().height()
            self._tab_full_h=bar+104
            if self._tab_expanded:
                self.tab_bottom.setFixedHeight(self._tab_full_h)
        except Exception:
            pass

    def _toggle_tab_pane(self):
        # 右上角箭头：最小化只留标题行 / 恢复
        try:
            bar=self.tab_bottom.tabBar().height() or 24
            if self._tab_expanded:
                self._tab_full_h=self.tab_bottom.height()
                self.tab_bottom.setFixedHeight(bar+2)
                self.btn_tab_toggle.setText("▸")
                self._tab_expanded=False
            else:
                if not self._tab_full_h:
                    self._fix_tab_height()
                self.tab_bottom.setFixedHeight(self._tab_full_h or bar+104)
                self.btn_tab_toggle.setText("▾")
                self._tab_expanded=True
        except Exception as e:
            print(e)

    # ---------- 目录加载 ----------
    def _load_bulei(self):
        try:
            mulu=Path(self.config["mulu_dir"])
            cat_json=mulu/"category.json"
            bt_txt=mulu/"bulei.txt"
            if cat_json.exists():
                # 官方 scope-selector/category.json（权威，CBETA 部類）
                self._bulei_roots=parse_bulei_json(cat_json)
                # 官方偶缺分组（如 般若部類 缺 01/09），用 bulei.txt 补同层缺失分组
                if bt_txt.exists():
                    from cbeta_publish.catalog.bulei_parser import merge_missing_children
                    merge_missing_children(self._bulei_roots, parse_bulei(bt_txt))
            else:
                self._bulei_roots=parse_bulei(bt_txt)
            self._refresh_bulei_tree()
        except Exception as e:
            print(e)

    def _refresh_bulei_tree(self, filter_node=None):
        self.tree.clear()
        hidden=set(self._catalog_filter_hidden("tripitaka"))   # 部类/三藏共用隐藏列表
        self.bulei_filter.blockSignals(True)
        cur = self.bulei_filter.currentData()
        self.bulei_filter.clear()
        self.bulei_filter.addItem("全部部类", None)
        def collect_levels(nodes, out):
            for n in nodes:
                if n.level==1:
                    out.append(n)
        levels=[]
        collect_levels(self._bulei_roots, levels)
        for n in levels:
            if n.title in hidden:
                continue
            self.bulei_filter.addItem(n.title, n)
        if cur:
            for i in range(self.bulei_filter.count()):
                if self.bulei_filter.itemData(i)==cur:
                    self.bulei_filter.setCurrentIndex(i)
                    break
        else:
            # clear()+addItem() 后可编辑 combo 可能停在 currentIndex=-1（只显示占位符）
            # → 显式回到「全部部类」并同步行编辑文本
            self.bulei_filter.setCurrentIndex(0)
        self.bulei_filter.blockSignals(False)
        # 可编辑 combo：恢复行编辑显示文本
        idx = self.bulei_filter.currentIndex()
        if idx < 0:
            idx = 0
            self.bulei_filter.setCurrentIndex(0)
        self.bulei_filter.setEditText(self.bulei_filter.itemText(idx))
        nodes = [filter_node] if filter_node else self._bulei_roots
        def add(nodes, parent):
            for n in nodes:
                if n.title in hidden:
                    continue
                item=QTreeWidgetItem([n.title])
                item.setData(0, Qt.UserRole, n)
                if parent:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                add(n.children, item)
        add(nodes, None)
        self._expand_tree()

    def _refresh_tripitaka_tree(self, filter_title=None):
        # 三藏视图：三藏→部類→…→经（复用 bulei 子树，内存重分组）；二级过滤=部类
        from cbeta_publish.catalog.tripitaka_service import group_by_pitaka
        self.tree.clear()
        groups=group_by_pitaka(self._bulei_roots)
        hidden=set(self._catalog_filter_hidden("tripitaka"))
        if filter_title is None:
            filter_title=self.tripitaka_filter.currentData()
        # 二级过滤下拉：部类（一级节点）
        self.tripitaka_filter.blockSignals(True)
        self.tripitaka_filter.clear()
        self.tripitaka_filter.addItem("全部部类", None)
        for _pitaka, _nodes in groups:
            for _n in _nodes:
                if _n.title in hidden:
                    continue
                self.tripitaka_filter.addItem(_n.title, _n.title)
        idx=0
        if filter_title:
            for i in range(self.tripitaka_filter.count()):
                if self.tripitaka_filter.itemData(i)==filter_title:
                    idx=i
                    break
        self.tripitaka_filter.setCurrentIndex(idx)
        self.tripitaka_filter.blockSignals(False)
        filter_title=self.tripitaka_filter.currentData()
        def add(nodes, parent):
            for n in nodes:
                item=QTreeWidgetItem([n.title])
                item.setData(0, Qt.UserRole, n)
                if parent:
                    parent.addChild(item)
                else:
                    self.tree.addTopLevelItem(item)
                add(n.children, item)
        for pitaka, nodes in groups:
            nodes=[n for n in nodes if n.title not in hidden]
            if filter_title:
                nodes=[n for n in nodes if n.title==filter_title]
            if not nodes:
                continue
            # 统计该三藏下经数（叶节点）
            cnt=0
            def _count(ns):
                nonlocal cnt
                for n in ns:
                    if not n.children:
                        cnt+=1
                    else:
                        _count(n.children)
            _count(nodes)
            label = f"{pitaka}藏 ({cnt}部)" if pitaka in ("經", "律", "論") else f"{pitaka} ({cnt}部)"
            p_item=QTreeWidgetItem([label])
            p_item.setData(0, Qt.UserRole, {"pitaka": pitaka})
            self.tree.addTopLevelItem(p_item)
            add(nodes, p_item)
        self._expand_tree()

    def _catalog_filter_hidden(self, kind):
        # 目录过滤：catalog.filters.<kind>.hidden 列表（部類标题/朝代标题）
        try:
            return self.config.get("catalog", {}).get("filters", {}).get(kind, {}).get("hidden", []) or []
        except Exception:
            return []

    def _expand_tree(self):
        # 按 ui.tree_expand 统一展开：mode=none 不展开 / depth 展开N层 / all 全部展开
        cfg=self.config.get("ui",{}).get("tree_expand",{}) or {}
        mode=cfg.get("mode","depth")
        try:
            depth=int(cfg.get("depth",2))
        except Exception:
            depth=2
        if mode=="all":
            self.tree.expandAll()
        elif mode=="none":
            self.tree.collapseAll()
        else:
            # depth=展开层数；0/1 折叠，depth>=2 -> expandToDepth(depth-1)
            if depth<=1:
                self.tree.collapseAll()
            else:
                self.tree.expandToDepth(depth-1)
        self._color_tree_leaves()

    def _color_tree_leaves(self, tree=None):
        """书叶（单本作品）文字用黑色；分组节点（部类/册/朝代/作者/丛书）颜色不变。"""
        from PySide6.QtGui import QBrush, QColor
        tree=tree if tree is not None else self.tree
        brush=QBrush(QColor("#000000"))
        def walk(it):
            if self._tree_item_work(it):
                it.setForeground(0, brush)
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i))

    def _refresh_vol_tree(self, filter_edition=None):
        # 刊本视图：刊本→册→经（部分刊本第二层直接是经）；受 catalog.filters.vol.hidden 过滤；
        # 过滤下拉 = 刊本（一级目录本身）
        from cbeta_publish.catalog.vol_service import load_vol
        self.tree.clear()
        path=Path(self.config["mulu_dir"])/"vol.json"
        hidden=set(self._catalog_filter_hidden("vol"))
        if not path.exists():
            self.vol_filter.blockSignals(True)
            self.vol_filter.clear(); self.vol_filter.addItem("全部刊本", None)
            self.vol_filter.blockSignals(False)
            it=QTreeWidgetItem(["（未下载 vol.json，请到 设置→更新源 检查更新）"])
            it.setForeground(0, Qt.gray)
            self.tree.addTopLevelItem(it)
            return
        entries=load_vol(path)
        if filter_edition is None:
            filter_edition=self.vol_filter.currentData()
        # 过滤下拉：刊本（一级）
        self.vol_filter.blockSignals(True)
        self.vol_filter.clear()
        self.vol_filter.addItem("全部刊本", None)
        for entry in entries:
            edition=entry["edition"]
            if edition in hidden:
                continue
            self.vol_filter.addItem(edition, edition)
        idx=0
        if filter_edition:
            for i in range(self.vol_filter.count()):
                if self.vol_filter.itemData(i)==filter_edition:
                    idx=i
                    break
        self.vol_filter.setCurrentIndex(idx)
        self.vol_filter.blockSignals(False)
        filter_edition=self.vol_filter.currentData()
        for entry in entries:
            edition=entry["edition"]
            if edition in hidden:
                continue
            if filter_edition and edition!=filter_edition:
                continue
            vols=entry.get("vols", [])
            works=entry.get("works", [])
            total=sum(len(v["works"]) for v in vols)+len(works)
            e_item=QTreeWidgetItem([f"{edition} ({len(vols)}册/{total}部)"])
            e_item.setData(0, Qt.UserRole, {"vol": edition})
            self.tree.addTopLevelItem(e_item)
            for wid, wtitle in works:
                e_item.addChild(self._work_item(wid, wtitle))
            for vol in vols:
                v_item=QTreeWidgetItem([f"{vol['title']} ({len(vol['works'])}部)"])
                v_item.setData(0, Qt.UserRole, {"vol_title": vol["title"], "edition": edition})
                e_item.addChild(v_item)
                for wid, wtitle in vol["works"]:
                    v_item.addChild(self._work_item(wid, wtitle))
        self._expand_tree()

    def _refresh_dynasty_tree(self):
        # 朝代视图：朝代→经（读 mulu/dynasty-works.json；受 catalog.filters.dynasty.hidden 过滤）
        from cbeta_publish.catalog.dynasty_service import load_dynasty
        self.tree.clear()
        path=Path(self.config["mulu_dir"])/"dynasty-works.json"
        hidden=set(self._catalog_filter_hidden("dynasty"))
        if not path.exists():
            it=QTreeWidgetItem(["（未下载 dynasty-works.json，请到 设置→更新源 检查更新）"])
            it.setForeground(0, Qt.gray)
            self.tree.addTopLevelItem(it)
            return
        for title, works in load_dynasty(path):
            if title in hidden:
                continue
            d_item=QTreeWidgetItem([f"{title} ({len(works)}部)"])
            d_item.setData(0, Qt.UserRole, {"dynasty": title})
            self.tree.addTopLevelItem(d_item)
            for wid, wtitle in works:
                l_item=QTreeWidgetItem([wtitle])
                l_item.setData(0, Qt.UserRole, {"key": wid, "title": wtitle})
                d_item.addChild(l_item)
        self._expand_tree()

    def _on_bulei_filter(self, idx):
        node=self.bulei_filter.currentData()
        # 延迟到 combo 选中完成后再刷新树，避免重建 combo 破坏当前选中
        QTimer.singleShot(0, lambda n=node: self._refresh_bulei_tree(filter_node=n))
        self.list.clear()

    def _on_tripitaka_filter(self, idx):
        # 三藏视图二级过滤：按部类标题过滤
        title=self.tripitaka_filter.currentData()
        QTimer.singleShot(0, lambda t=title: self._refresh_tripitaka_tree(filter_title=t))
        self.list.clear()

    def _on_vol_filter(self, idx):
        # 刊本视图过滤：按刊本（一级目录）过滤
        key=self.vol_filter.currentData()
        QTimer.singleShot(0, lambda k=key: self._refresh_vol_tree(filter_edition=k))
        self.list.clear()

    def _author_sort_mode(self):
        for name, rb in self.author_radios.items():
            if rb.isChecked():
                return name
        return "拼音排序"

    def _on_author_filter(self, idx):
        d=self.author_filter.currentData()
        if self._author_sort_mode() in ("拼音排序","朝代排序"):
            QTimer.singleShot(0, lambda l=d: self._refresh_author_tree(filter_letter=l))
        else:
            QTimer.singleShot(0, lambda s=d: self._refresh_author_tree(filter_stroke=s))

    def _on_coll_filter(self, idx):
        cat=self.coll_filter.currentData()
        QTimer.singleShot(0, lambda c=cat: self._refresh_coll_tree(filter_cat=c))

    # ---------- 作者树 ----------
    def _dynasty_index(self):
        # 缓存 work → 朝代 与 朝代顺序（来自 mulu/dynasty-works.json）
        if getattr(self, "_work_dyn", None) is not None:
            return self._work_dyn, self._dyn_order
        from cbeta_publish.catalog.dynasty_service import load_dynasty
        path=Path(self.config["mulu_dir"])/"dynasty-works.json"
        dmap={}; order=[]
        for title, works in load_dynasty(path):
            order.append(title)
            for wid, _t in works:
                dmap.setdefault(wid, title)
        self._work_dyn=dmap
        self._dyn_order=order
        return dmap, order

    @staticmethod
    def _stroke_label(title):
        # 笔画分组标题形如「1畫(stroke)」→ 显示为「1畫」
        return re.sub(r"\s*\(stroke\)\s*", "", title or "").strip()

    def _refresh_author_tree(self, filter_stroke=None, filter_letter=None):
        self.tree.clear()
        try:
            data=self.creator.strokes
            strokes=[]
            if data and len(data)==1 and len(data[0].get("children",[]))>=20:
                strokes=data[0].get("children",[])
            else:
                strokes=data
            mode=self._author_sort_mode()
            # 过滤下拉按排序模式填充：笔画排序=笔画列表；拼音排序=A-Z 字母
            self.author_filter.blockSignals(True)
            cur=self.author_filter.currentData()
            self.author_filter.clear()
            if mode=="拼音排序":
                self.author_filter.addItem("字母：全部", None)
                for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                    self.author_filter.addItem(ch, ch)
            elif mode=="朝代排序":
                self.author_filter.addItem("朝代：全部", None)
                for t in self._dynasty_index()[1]:
                    self.author_filter.addItem(t, t)
                self.author_filter.addItem("未詳", "未詳")
            else:
                self.author_filter.addItem("笔画：全部", None)
                for s in strokes:
                    self.author_filter.addItem(self._stroke_label(s.get("title","")), s)
            if cur:
                for i in range(self.author_filter.count()):
                    if self.author_filter.itemData(i)==cur:
                        self.author_filter.setCurrentIndex(i); break
            self.author_filter.blockSignals(False)
            # 可编辑 combo：恢复行编辑显示文本（否则选中项文本消失）
            if cur is not None:
                for i in range(self.author_filter.count()):
                    if self.author_filter.itemData(i)==cur:
                        self.author_filter.setEditText(self.author_filter.itemText(i))
                        break
                else:
                    # 旧选择在当前模式不存在（如跨模式切换）：回落显示首项
                    self.author_filter.setEditText(self.author_filter.itemText(0))
            if mode=="拼音排序":
                # 拼音排序：按首字母分组为可折叠节点（作者为子项），支持字母过滤
                try:
                    if self._authors_pinyin_sorted is not None:
                        authors=self._authors_pinyin_sorted
                    else:
                        authors=[]
                        for s in strokes:
                            for su in s.get("children",[]):
                                for a in su.get("children",[]):
                                    authors.append(a)
                        authors.sort(key=lambda x: self._pinyin_key(x.get("title","")))
                    if filter_letter:
                        authors=[a for a in authors if self._pinyin_letter(a.get("title",""))==filter_letter]
                    groups={}
                    for a in authors:
                        groups.setdefault(self._pinyin_letter(a.get("title","")), []).append(a)
                    for letter in sorted(groups):
                        g_item=QTreeWidgetItem([letter])
                        self.tree.addTopLevelItem(g_item)
                        for a in groups[letter]:
                            cnt=len(a.get("children",[]))
                            a_item=QTreeWidgetItem([f"{a.get('title','')} ({cnt}部)"])
                            a_item.setData(0, Qt.UserRole, a)
                            g_item.addChild(a_item)
                    self._expand_tree()
                    return
                except Exception:
                    pass
            if mode=="朝代排序":
                try:
                    from cbeta_publish.catalog.dynasty_service import group_authors_by_dynasty
                    authors=[]
                    for s in strokes:
                        for su in s.get("children",[]):
                            for a in su.get("children",[]):
                                authors.append(a)
                    dmap, order = self._dynasty_index()
                    pairs=group_authors_by_dynasty(authors, dmap, order)
                    if filter_letter:
                        pairs=[(t, g) for t, g in pairs if t==filter_letter]
                    for dyn, group in pairs:
                        d_item=QTreeWidgetItem([dyn])
                        self.tree.addTopLevelItem(d_item)
                        for a in sorted(group, key=lambda x: self._pinyin_key(x.get("title",""))):
                            cnt=len(a.get("children",[]) or [])
                            a_item=QTreeWidgetItem([f"{a.get('title','')} ({cnt}部)"])
                            a_item.setData(0, Qt.UserRole, a)
                            d_item.addChild(a_item)
                    self._expand_tree()
                    return
                except Exception as e:
                    print("author dynasty tree fail", e)
            if filter_stroke:
                strokes=[filter_stroke]
            for stroke in strokes:
                s_item=QTreeWidgetItem([self._stroke_label(stroke.get("title",""))])
                s_item.setData(0, Qt.UserRole, stroke)
                self.tree.addTopLevelItem(s_item)
                for surname in stroke.get("children",[]):
                    su_item=QTreeWidgetItem([surname.get("title","")])
                    su_item.setData(0, Qt.UserRole, surname)
                    s_item.addChild(su_item)
                    for author in surname.get("children",[]):
                        cnt=len(author.get("children",[]))
                        a_item=QTreeWidgetItem([f"{author.get('title','')} ({cnt}部)"])
                        a_item.setData(0, Qt.UserRole, author)
                        su_item.addChild(a_item)
            self._expand_tree()
        except Exception as e:
            print("author tree fail", e)

    # ---------- 丛书树 ----------
    def _tags(self):
        return TagsManager(Path(self.config["collections_dir"]) / "tags.json")

    def _on_coll_tag_filter(self, idx):
        tag=self.coll_tag_filter.currentData()
        QTimer.singleShot(0, lambda t=tag: self._refresh_coll_tree(
            filter_cat=self.coll_filter.currentData(), filter_tag=t))

    def _work_item(self, wid, wtitle=""):
        # 统一的作品叶节点（各树共用；_item_payload 认 {"key": wid}）
        it=QTreeWidgetItem([wtitle or wid])
        it.setData(0, Qt.UserRole, {"key": wid, "title": wtitle or wid})
        return it

    def _refresh_coll_tree(self, filter_cat=None, filter_tag=None):
        self.tree.clear()
        self.coll_filter.blockSignals(True)
        cur=self.coll_filter.currentData()
        self.coll_filter.clear()
        self.coll_filter.addItem("分类：全部", None)
        try:
            cm=CategoryManager(Path(self.config["collections_dir"])/"categories.json")
            for c in cm.all():
                self.coll_filter.addItem(c["name"], c["id"])
        except: pass
        if cur:
            for i in range(self.coll_filter.count()):
                if self.coll_filter.itemData(i)==cur:
                    self.coll_filter.setCurrentIndex(i); break
        self.coll_filter.blockSignals(False)
        # 标签筛选下拉（横切维度）
        self.coll_tag_filter.blockSignals(True)
        cur_tag=self.coll_tag_filter.currentData()
        self.coll_tag_filter.clear()
        self.coll_tag_filter.addItem("标签：全部", None)
        try:
            tm=self._tags()
            for t in tm.all():
                self.coll_tag_filter.addItem(t.get("name", t["id"]), t["id"])
        except Exception as e:
            print("tags load fail", e)
        if cur_tag:
            for i in range(self.coll_tag_filter.count()):
                if self.coll_tag_filter.itemData(i)==cur_tag:
                    self.coll_tag_filter.setCurrentIndex(i); break
        self.coll_tag_filter.blockSignals(False)
        for p,d in self._collections:
            if filter_cat and d.get("category")!=filter_cat:
                continue
            if filter_tag and filter_tag not in (d.get("tags",[]) or []):
                continue
            item=QTreeWidgetItem([f"{d.get('name')} [{self._cat_name(d.get('category',''))}] {len(d.get('work_ids',[]))}部"])
            item.setData(0, Qt.UserRole, d)
            self.tree.addTopLevelItem(item)
            # 列出经书名字（原来只有丛书名）
            for wid in (d.get("work_ids", []) or []):
                title=self.sutra.title_of(wid)
                if title==wid:
                    m=self.mapping.resolve(wid)
                    if m:
                        title=m.get("name") or wid
                item.addChild(self._work_item(wid, f"{title}"))
        self._expand_tree()

    def _load_collections(self):
        cdir=Path(self.config["collections_dir"])
        self._coll_changed=False
        self._changed_colls=set()
        self._coll_originals={}
        self._collections=[]
        for cat_dir in cdir.iterdir():
            if cat_dir.is_dir():
                for f in cat_dir.glob("*.json"):
                    try:
                        d=normalize_collection(json.loads(f.read_text(encoding="utf-8")))
                        self._collections.append((f,d))
                        # 基线也用规范化结果，读入即迁移（下次保存回写磁盘）
                        self._coll_originals[str(f)]=json.dumps(d, ensure_ascii=False, indent=2)
                    except: pass
        self._collections.sort(key=lambda x: 0 if x[1].get("name")=="空白丛书" else 1)
        self._write_index()
        self._sync_combo(select_path=self._last_coll_path)

    def _write_index(self):
        # 生成 collections/index.json（派生缓存，best-effort）
        try:
            write_index(self._collections, Path(self.config["collections_dir"]) / "index.json")
        except Exception as e:
            print("write index fail", e)

    def _read_coll(self, p):
        # 从磁盘读丛书 JSON（规范化 id）；用于内存未命中时的兜底
        return normalize_collection(json.loads(Path(p).read_text(encoding="utf-8")))

    def _coll_dict(self, path):
        for pp,dd in self._collections:
            if str(pp)==str(path):
                return dd
        return None

    def _pinyin_key(self, title):
        # 拼音排序键：剥离 释/沙門/比丘 等前缀后，返回音节元组（按音节正确比较，同字成组）
        t=title or ""
        for p in ("沙門釋","比丘釋","比丘尼釋","沙門","比丘尼","比丘","釋"):
            if t.startswith(p):
                t=t[len(p):]
                break
        try:
            from pypinyin import lazy_pinyin
            return tuple(lazy_pinyin(t))
        except Exception:
            return (t,)

    def _pinyin_letter(self, title):
        # 拼音首字母（用于字母分组/过滤）
        try:
            return self._pinyin_key(title)[0][:1].upper()
        except Exception:
            return ""

    def _cat_name(self, cid):
        # 分类 id -> 中文名
        try:
            cm=CategoryManager(Path(self.config["collections_dir"])/"categories.json")
            for c in cm.all():
                if c["id"]==cid:
                    return c["name"]
        except Exception:
            pass
        return cid

    def _refresh_after_cat_change(self):
        # 分类删改后：右栏过滤下拉与左栏 coll_filter 同步刷新
        self._sync_combo(select_path=getattr(self, "_last_coll_path", None))
        if self.nav_combo.currentText()=="丛书":
            self._refresh_coll_tree()

    def _category_manager_dialog(self):
        # 分类管理：列表（id/名称/描述/预设标记）+ 改名/删除；预设分类禁删
        cdir=Path(self.config["collections_dir"])
        from PySide6.QtWidgets import QDialog as _DM, QVBoxLayout as _VM, QHBoxLayout as _HM, QListWidget as _LM, QListWidgetItem as _LIM
        dlg=_DM(self)
        dlg.setWindowTitle("分类管理")
        dlg.resize(440, 400)
        v=_VM(dlg)
        lst=_LM()
        def reload():
            lst.clear()
            cm=CategoryManager(cdir/"categories.json")
            for c in cm.all():
                tag="（预设）" if c.get("preset") else ""
                desc=c.get("description","")
                text=f"{c['name']} ({c['id']}){tag}" + (f"\n   {desc}" if desc else "")
                item=_LIM(text)
                item.setData(Qt.UserRole, c["id"])
                lst.addItem(item)
        reload()
        v.addWidget(lst)
        btnrow=_DM()
        hb=_HM(btnrow)
        hb.setContentsMargins(0,0,0,0)
        btn_rename=QPushButton("改名")
        btn_add=QPushButton("新建")
        btn_del=QPushButton("删除")
        btn_close=QPushButton("关闭")
        hb.addWidget(btn_add); hb.addWidget(btn_rename); hb.addWidget(btn_del); hb.addStretch(); hb.addWidget(btn_close)
        v.addWidget(btnrow)
        def get_cid():
            item=lst.currentItem()
            return item.data(Qt.UserRole) if item else None
        def do_add():
            cid2=self._ask_cat_fields("新建分类")
            if cid2:
                reload()
        def do_rename():
            cid=get_cid()
            if not cid:
                return
            cm=CategoryManager(cdir/"categories.json")
            cat=next((x for x in cm.all() if x["id"]==cid), None)
            if not cat:
                return
            res=self._ask_cat_fields("改名分类", cat.get("name",""), cat.get("description",""))
            if not res:
                return
            cm.update(cid, new_name=res[0], new_desc=res[1])
            reload()
        def do_delete():
            cid=get_cid()
            if not cid:
                return
            cm=CategoryManager(cdir/"categories.json")
            cat=next((x for x in cm.all() if x["id"]==cid), None)
            if not cat:
                return
            if cat.get("preset"):
                self._wrap_box(QMessageBox.Warning, "禁止删除", f"「{cat['name']}」是预设分类，不允许删除。")
                return
            cat_dir=cdir/cid
            files=list(cat_dir.glob("*.json")) if cat_dir.exists() else []
            if files:
                self._wrap_box(QMessageBox.Warning, "禁止删除", f"「{cat['name']}」分类下还有 {len(files)} 部丛书，请先移走或删除后再操作。")
                return
            ret=QMessageBox.question(self,"删除分类", f"确定删除分类「{cat['name']}」？", QMessageBox.Yes | QMessageBox.No)
            if ret!=QMessageBox.Yes:
                return
            cm.delete(cid)
            try:
                if cat_dir.exists() and not any(cat_dir.iterdir()):
                    cat_dir.rmdir()
            except Exception:
                pass
            reload()
        btn_add.clicked.connect(do_add)
        btn_rename.clicked.connect(do_rename)
        btn_del.clicked.connect(do_delete)
        btn_close.clicked.connect(dlg.accept)
        if dlg.exec()==_DM.Accepted:
            self._refresh_after_cat_change()

    def _ask_name_desc(self, title, name="", desc=""):
        # 通用「名称+说明」对话框，返回 (name, desc) 或 None
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
        dlg=QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(400)
        form=QFormLayout(dlg)
        ne=QLineEdit(name)
        form.addRow("名称", ne)
        de=QLineEdit(desc)
        form.addRow("说明", de)
        btns=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec()!=QDialog.Accepted:
            return None
        n=ne.text().strip()
        if not n:
            return None
        return (n, de.text().strip())

    def _tag_manager_dialog(self):
        # 标签管理：新建/改名/删除；有丛书使用则禁删
        cdir=Path(self.config["collections_dir"])
        from PySide6.QtWidgets import QDialog as _DM, QVBoxLayout as _VM, QHBoxLayout as _HM, QListWidget as _LM, QListWidgetItem as _LIM
        dlg=_DM(self)
        dlg.setWindowTitle("标签管理")
        dlg.resize(440, 400)
        v=_VM(dlg)
        lst=_LM()
        def reload():
            lst.clear()
            for t in self._tags().all():
                desc=t.get("description","")
                text=f"{t.get('name',t['id'])} ({t['id']})" + (f"\n   {desc}" if desc else "")
                item=_LIM(text)
                item.setData(Qt.UserRole, t["id"])
                lst.addItem(item)
        def usage(tid):
            return [d.get("name","") for _p, d in self._collections
                    if tid in (d.get("tags",[]) or [])]
        reload()
        v.addWidget(lst)
        btnrow=_DM()
        hb=_HM(btnrow)
        hb.setContentsMargins(0,0,0,0)
        btn_add=QPushButton("新建"); btn_rename=QPushButton("改名")
        btn_del=QPushButton("删除"); btn_close=QPushButton("关闭")
        hb.addWidget(btn_add); hb.addWidget(btn_rename); hb.addWidget(btn_del)
        hb.addStretch(); hb.addWidget(btn_close)
        v.addWidget(btnrow)
        def get_tid():
            item=lst.currentItem()
            return item.data(Qt.UserRole) if item else None
        def do_add():
            res=self._ask_name_desc("新建标签")
            if not res:
                return
            self._tags().add(res[0], description=res[1])
            reload()
        def do_rename():
            tid=get_tid()
            if not tid:
                return
            t=self._tags().get(tid)
            if not t:
                return
            res=self._ask_name_desc("改名标签", t.get("name",""), t.get("description",""))
            if not res:
                return
            self._tags().update(tid, new_name=res[0], new_desc=res[1])
            reload()
        def do_delete():
            tid=get_tid()
            if not tid:
                return
            used=usage(tid)
            if used:
                self._wrap_box(QMessageBox.Warning, "禁止删除",
                               f"标签「{self._tags().name_of(tid)}」已被 {len(used)} 部丛书使用，请先移除后再删除。")
                return
            if QMessageBox.question(self, "删除标签", f"确定删除标签「{self._tags().name_of(tid)}」？") != QMessageBox.Yes:
                return
            self._tags().delete(tid)
            reload()
        btn_add.clicked.connect(do_add)
        btn_rename.clicked.connect(do_rename)
        btn_del.clicked.connect(do_delete)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec()
        if self.nav_combo.currentText()=="丛书":
            self._refresh_coll_tree(filter_cat=self.coll_filter.currentData(),
                                    filter_tag=self.coll_tag_filter.currentData())

    def _edit_coll_tags(self):
        # 为当前丛书设置标签（多选）
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择丛书")
            return
        d=self._coll_dict(data)
        if d is None:
            return
        from PySide6.QtWidgets import QDialog as _DM, QVBoxLayout as _VM, QHBoxLayout as _HM, QListWidget as _LM, QListWidgetItem as _LIM
        tags=self._tags().all()
        cur=set(d.get("tags",[]) or [])
        dlg=_DM(self)
        dlg.setWindowTitle(f"标签：{d.get('name','')}")
        dlg.resize(360, 420)
        v=_VM(dlg)
        lst=_LM()
        for t in tags:
            item=_LIM(t.get("name",t["id"]))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if t["id"] in cur else Qt.Unchecked)
            item.setData(Qt.UserRole, t["id"])
            lst.addItem(item)
        # 未登记的旧标签也列出，避免静默丢失
        known={t["id"] for t in tags}
        for tid in sorted(cur - known):
            item=_LIM(f"{tid}（未登记）")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, tid)
            lst.addItem(item)
        v.addWidget(lst)
        btnrow=_DM()
        hb=_HM(btnrow); hb.setContentsMargins(0,0,0,0)
        btn_ok=QPushButton("确定"); btn_mgr=QPushButton("标签管理…"); btn_cancel=QPushButton("取消")
        hb.addWidget(btn_ok); hb.addWidget(btn_mgr); hb.addStretch(); hb.addWidget(btn_cancel)
        v.addWidget(btnrow)
        def collect():
            out=[]
            for i in range(lst.count()):
                it=lst.item(i)
                if it.checkState()==Qt.Checked:
                    out.append(it.data(Qt.UserRole))
            return out
        def on_ok():
            d["tags"]=collect()
            d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
            self._mark_coll_changed(str(data))
            self._write_index()
            self._load_coll_works()
            if self.nav_combo.currentText()=="丛书":
                self._refresh_coll_tree(filter_cat=self.coll_filter.currentData(),
                                        filter_tag=self.coll_tag_filter.currentData())
            self.detail.setText(f"已更新标签（{len(d['tags'])} 个）")
            dlg.accept()
        btn_ok.clicked.connect(on_ok)
        btn_cancel.clicked.connect(dlg.reject)
        btn_mgr.clicked.connect(lambda: (dlg.accept(), self._tag_manager_dialog()))
        dlg.exec()

    def _name_taken(self, name, exclude_path=None):
        # 全局查重（跨分类），返回已占用丛书路径或 None
        for p,d in self._collections:
            if str(p)!=str(exclude_path) and d.get("name")==name:
                return str(p)
        return None

    def _is_coll_placeholder(self, data):
        return not data

    def _sync_combo(self, select_path=None):
        # 右栏：顶部分类过滤下拉（与左栏一致）+ 丛书 combo（仅 缓存/分隔线/丛书）
        cdir=Path(self.config["collections_dir"])
        try:
            cm=CategoryManager(cdir/"categories.json")
            cats=cm.all()
        except: cats=[]
        self.coll_cat_filter.blockSignals(True)
        cur_cat=self.coll_cat_filter.currentData()
        self.coll_cat_filter.clear()
        self.coll_cat_filter.addItem("分类：全部", None)
        for c in cats:
            self.coll_cat_filter.addItem(f"{c['name']} ({c['id']})", c["id"])
        if cur_cat:
            for i in range(self.coll_cat_filter.count()):
                if self.coll_cat_filter.itemData(i)==cur_cat:
                    self.coll_cat_filter.setCurrentIndex(i)
                    break
        self.coll_cat_filter.blockSignals(False)
        cat_filter=cur_cat
        self.coll_combo.blockSignals(True)
        self.coll_combo.clear()
        for p,d in self._collections:
            if cat_filter is None or d.get("category")==cat_filter:
                self.coll_combo.addItem(d.get("name",p.stem), str(p))
        self.coll_combo.blockSignals(False)
        idx=0
        if select_path:
            for i in range(self.coll_combo.count()):
                if self.coll_combo.itemData(i)==str(select_path):
                    idx=i
                    break
        self.coll_combo.setCurrentIndex(idx)
        self._update_coll_marks()
        # 空 combo 首个条目会自动选中（blockSignals 期间），setCurrentIndex 可能不发信号，
        # 显式刷新右栏书单确保始终与当前选中一致
        self._load_coll_works()

    def _on_cat_filter_changed(self, idx):
        self._sync_combo(select_path=getattr(self, "_last_coll_path", None))

    def _on_combo_changed(self):
        data=self.coll_combo.currentData()
        if isinstance(data,str):
            self._last_coll_path=str(data)
            self._persist_last_collection(str(data))
        self._load_coll_works()

    def _persist_ui_layout(self):
        # 布局（三栏/二栏）落盘，下次启动沿用
        try:
            p=Path(self._config_path)
            cfg=json.loads(p.read_text(encoding="utf-8")) if p.exists() else self.config
            cfg.setdefault("ui", {})["layout"]=self._layout_mode()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("persist layout fail", e)

    def _save_config(self):
        # 运行期改动（来源/预设）写回磁盘配置
        try:
            p=Path(self._config_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("save config fail", e)

    def _run_source(self):
        # 本次合并来源：右栏单选（全局 default_source），显示官方/自制
        return self.config.get("default_source", "official") or "official"

    def _run_preset(self):
        # 本次生成/合并预设：有「调整…」临时预设则优先用它（不落盘），否则用下拉选中项
        if getattr(self, "_tmp_preset", None) is not None:
            return self._tmp_preset
        from cbeta_publish.books import xml2pdf_bridge as _b
        return _b.resolve_preset(self.config)

    def _set_transient_preset(self, data):
        """保存「调整…」结果到临时预设（仅本次运行生效，不落盘为命名预设）。"""
        from cbeta_publish.books import xml2pdf_bridge as _b
        self._clear_transient_preset()
        p=_b.write_temp_preset(self.config, data)
        if p is None:
            self.detail.setText("临时预设写入失败")
            return None
        self._tmp_preset=p
        try:
            self.lbl_preset.setText("预设(本次):")
            self.lbl_preset.setToolTip("已应用「调整…」的本次改动（未保存为预设）；改选预设即放弃")
        except Exception:
            pass
        self.detail.setText("已应用本次临时调整（未保存为预设）")
        return p

    def _clear_transient_preset(self):
        if getattr(self, "_tmp_preset", None) is None:
            return
        from cbeta_publish.books import xml2pdf_bridge as _b
        _b.remove_temp_preset(self._tmp_preset)
        self._tmp_preset=None
        try:
            self.lbl_preset.setText("预设:")
            self.lbl_preset.setToolTip("")
        except Exception:
            pass

    def _checked_fmts(self):
        """右栏「格式」勾选 → ["pdf"]/["epub"]/["pdf","epub"]（pdf 在前）。"""
        fmts=[]
        if self.chk_pdf.isChecked(): fmts.append("pdf")
        if self.chk_epub.isChecked(): fmts.append("epub")
        return fmts

    def _run_regen(self):
        # 自制书生成策略（右栏「生成」单选）：missing=仅生成缺少（默认）；all=全部重新生成
        v=(self.config.get("xml2pdf", {}) or {}).get("regen", "missing")
        return "all" if v=="all" else "missing"

    def _sync_source_preset_ui(self):
        # 右栏来源单选 + 预设下拉 + 生成策略与配置同步（启动/设置页保存后调用）
        try:
            src=self._run_source()
            (self.rb_made if src=="xml" else self.rb_official).setChecked(True)
        except Exception:
            pass
        try:
            (self.rb_regen_all if self._run_regen()=="all" else self.rb_regen_missing).setChecked(True)
        except Exception:
            pass
        self._refresh_preset_combo()

    def _refresh_preset_combo(self):
        # 预设下拉：预设目录下合法 *.json + 首项"出厂默认"；保持当前选择
        from cbeta_publish.books import xml2pdf_bridge as _b
        try:
            cur=self.cb_preset.currentData()
        except Exception:
            cur=None
        if cur is None:
            cur=(self.config.get("xml2pdf", {}) or {}).get("preset", "")
        try:
            names=_b.list_presets(self.config)
        except Exception:
            names=[]
        self.cb_preset.blockSignals(True)
        self.cb_preset.clear()
        self.cb_preset.addItem("出厂默认", "")
        for n in names:
            self.cb_preset.addItem(n, n)
        i=self.cb_preset.findData(cur)
        self.cb_preset.setCurrentIndex(i if i>=0 else 0)
        self.cb_preset.blockSignals(False)
        self._update_preset_enabled()

    def _update_preset_enabled(self):
        # 仅来源=自制时启用预设/生成行，并把「下载/更新」换成「自制/重制」
        on=self._run_source()=="xml"
        self.cb_preset.setEnabled(on)
        self.btn_preset_edit.setEnabled(on)
        self.rb_regen_missing.setEnabled(on)
        self.rb_regen_all.setEnabled(on)
        self.regen_box.setVisible(on)
        self.btn_download.setVisible(not on)
        self.btn_make.setVisible(on)
        self.btn_remake.setVisible(on)

    def _on_source_changed(self, *_):
        # 右栏来源切换：sticky 写回全局，下次默认上次的选择
        btn=self.src_group.checkedButton()
        self.config["default_source"]="xml" if btn is self.rb_made else "official"
        self._save_config()
        self._update_preset_enabled()
        self._load_coll_works()   # 已有标志随来源（官方/自制目录）刷新

    def _on_regen_changed(self, *_):
        # 右栏生成策略切换：sticky 写回全局
        btn=self.regen_group.checkedButton()
        self.config.setdefault("xml2pdf", {})["regen"]="all" if btn is self.rb_regen_all else "missing"
        self._save_config()

    def _on_preset_changed(self, *_):
        # 右栏预设切换：sticky 写回全局默认预设
        try:
            name=self.cb_preset.currentData() or ""
        except Exception:
            name=""
        self.config.setdefault("xml2pdf", {})["preset"]=name
        self._save_config()
        # 改选预设 = 放弃「调整…」的临时预设
        self._clear_transient_preset()

    def _edit_preset(self):
        """打开上游 XmlOptionsDialog 调整选项。

        点「确定」= 调整结果**立即生效**（存成临时预设，仅本次运行、不落盘），
        随后再问是否保存为命名预设（覆盖/另存为/不保存）。取消则什么都不改。
        """
        from cbeta_publish.books import xml2pdf_bridge as _b
        from PySide6.QtWidgets import QDialog as _QD, QInputDialog
        try:
            _b._ensure_path(str(_b._x2p_root(self.config)))
            from pycbeta.gui.panel import XmlOptionsDialog
        except Exception as e:
            QMessageBox.warning(self, "失败", f"载入 xml2pdf 选项对话框失败：{e}")
            return
        cur_name = self.cb_preset.currentData() or ""
        cur_path = _b.resolve_preset(self.config, cur_name)
        base = _b.load_preset_dict(cur_path, self.config) if cur_path else {}
        dlg = XmlOptionsDialog(base or None, self)
        # 「输出格式」对 publish 无意义（格式由右栏勾选、以 -f 传入）：预置为当前勾选，避免误导
        _fmts=self._checked_fmts()
        if _fmts:
            try:
                _opts=dlg.panel.get_options()
                _opts.formats=list(_fmts)
                dlg.panel.set_options(_opts)
            except Exception as e:
                print('preset formats fail', e)
        if dlg.exec() != _QD.Accepted:
            return
        merged = dlg.get_preset(base if isinstance(base, dict) else None)
        if not isinstance(merged, dict):
            return
        # 确定即本次生效（临时预设，不落盘）
        if self._set_transient_preset(merged) is None:
            return
        # 再问是否保存为命名预设
        box = QMessageBox(self)
        box.setWindowTitle("保存为预设？")
        box.setText("本次调整已生效（仅本次运行）。要保存为预设吗？")
        b_save = box.addButton("覆盖当前预设" if cur_name else "保存为预设", QMessageBox.AcceptRole)
        b_as = box.addButton("另存为…", QMessageBox.ActionRole)
        box.addButton("不保存", QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        name = None
        if clicked is b_save:
            name = cur_name
            if not name:
                name, ok = QInputDialog.getText(self, "保存预设", "预设名：")
                name = (name or "").strip()
                if not ok or not name:
                    return
        elif clicked is b_as:
            name, ok = QInputDialog.getText(self, "另存为新预设", "预设名：")
            name = (name or "").strip()
            if not ok or not name:
                return
        else:
            return   # 不保存：保留临时预设（本次运行有效）
        path = _b.save_preset(self.config, name, merged)
        if path is None:
            QMessageBox.warning(self, "失败", "写入预设失败（预设名是否为空/非法？）")
            return
        # 已保存为命名预设 → 临时预设不再需要
        self._clear_transient_preset()
        self._refresh_preset_combo()
        i = self.cb_preset.findData(path.stem)
        if i >= 0:
            self.cb_preset.setCurrentIndex(i)
        self.detail.setText(f"预设已保存：{path.name}")

    def _persist_last_collection(self, path):
        # 记住上次工作的丛书，下次启动直接应用
        try:
            cfg=self.config
            ui=cfg.setdefault("ui", {})
            if ui.get("last_collection")==path:
                return
            ui["last_collection"]=path
            p=Path(self._config_path)
            if p.exists():
                disk=json.loads(p.read_text(encoding="utf-8"))
            else:
                disk=cfg
            disk.setdefault("ui", {})["last_collection"]=path
            p.write_text(json.dumps(disk, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("persist last collection fail", e)

    # ---------- 导航 ----------
    def _clear_search(self):
        # 清除搜索框 + 各二级过滤，恢复完整目录。
        # 目录树尽量保持使用状态（含展开/滚动/选中）：只搜过、没动过滤时恢复暂存的导航树；
        # 过滤条件真变了才重建（重建前快照展开状态并尽量还原）。
        had_kw=bool((self.search.text() or "").strip()) or bool(self._search_results)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        try:
            if self.btn_workspace.isChecked():
                self.btn_workspace.setChecked(False)
        except Exception:
            pass
        changed=False
        for cb in (self.bulei_filter, self.tripitaka_filter, self.vol_filter,
                   self.author_filter, self.coll_filter, self.coll_tag_filter):
            try:
                if cb.currentData() is not None:
                    changed=True
                cb.blockSignals(True)
                cb.setCurrentIndex(0)   # 可编辑 combo 也把编辑框文字带回默认项
                cb.blockSignals(False)
            except Exception:
                pass
        if not changed and not had_kw:
            return
        # 结果视图占用左栏时，展开状态取暂存导航树的快照
        expand=getattr(self, "_nav_expand", None) if self._left_search_active else None
        if expand is None:
            expand=self._tree_expand_state()
        self._search_results=[]
        if changed:
            self._left_search_active=False
            self._nav_stash=None
            self._refresh_current_tree()
            self._apply_tree_expand_state(expand)
        else:
            self._render_search_to_left()

    def _refresh_current_tree(self):
        # 按当前导航模式重刷目录树（内容变化时重建；是否保留展开状态由调用方决定）
        self.tree.clear()
        mode=self.nav_combo.currentText()
        if mode=="部类":
            self._refresh_bulei_tree()
        elif mode=="三藏":
            self._refresh_tripitaka_tree()
        elif mode=="朝代":
            self._refresh_dynasty_tree()
        elif mode=="刊本":
            self._refresh_vol_tree()
        elif mode=="作者":
            self._refresh_author_tree()
        elif mode=="丛书":
            self._refresh_coll_tree()

    def _on_nav_changed(self, mode):
        self.tree.clear()
        self._nav_stash=None
        self._left_search_active=False
        self._search_results=[]
        # 切导航模式 = 回到目录面板浏览（清掉搜索词与结果视图）
        try:
            if self.btn_workspace.isChecked():
                self.btn_workspace.setChecked(False)
        except Exception:
            pass
        if self.search.text():
            self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.bulei_filter.setVisible(mode=="部类")
        self.tripitaka_filter.setVisible(mode=="三藏")
        self.vol_filter.setVisible(mode=="刊本")
        self.author_filter.setVisible(mode=="作者")
        self.author_sort_row.setVisible(mode=="作者")
        self.coll_filter.setVisible(mode=="丛书")
        self.coll_tag_filter.setVisible(mode=="丛书")
        # 左栏状态栏：操作提示（按模式）
        if mode=="部类":
            self.lbl_hint.setText("提示：拖动或双击单本书加入工作区")
        elif mode=="三藏":
            self.lbl_hint.setText("提示：经/律/论/藏外；拖动或双击单本书加入工作区")
        elif mode=="朝代":
            self.lbl_hint.setText("提示：按朝代浏览；拖动或双击单本书加入工作区")
        elif mode=="刊本":
            self.lbl_hint.setText("提示：依刊本（藏经版本）→ 册 → 经；拖动或双击单本书加入工作区")
        elif mode=="作者":
            self.lbl_hint.setText("提示：拖动或双击作者（其全部作品）加入工作区")
        elif mode=="丛书":
            self.lbl_hint.setText("提示：双击丛书追加其书目到工作区；拖入右栏加入丛书")
        if self._layout_mode()=="two":
            self.lbl_hint.setText((self.lbl_hint.text() or "") + "　【二栏】拖动/双击=直接加入右栏")
        self._refresh_current_tree()

    def _book_info_text(self, w):
        # 统一书籍信息文本：左栏预览 / 中栏列表 / 右栏书单 三处一致
        if not w:
            return ""
        m=self.mapping.resolve(w) or {}
        title=self._display_title(w)
        lines=[f"{w} {title}".rstrip()]
        byline=m.get("byline","") or ""
        if byline:
            lines.append(f"译作者：{byline}")
        juan=m.get("juan")
        fname=m.get("file")
        if juan or fname:
            parts=[]
            if juan:
                parts.append(f"卷数：{juan}")
            if fname:
                parts.append(f"文件：{fname}")
            lines.append("　".join(parts))
        return "\n".join(lines)

    def _tree_item_work(self, item):
        # 左栏节点对应的书籍号：只有「叶=单个作品」才返回，分组/刊本册/丛书节点返回 None
        data=item.data(0, Qt.UserRole)
        if isinstance(data, dict):
            if data.get("children") or data.get("work_ids") is not None:
                return None
            k=data.get("key")
            return k if (k and self._is_work_id(k)) else None
        if hasattr(data, "title") and not getattr(data, "children", None):
            m=re.search(r"[A-Z]+[0-9A-Za-z]+", data.title)
            if m and self._is_work_id(m.group(0)):
                return m.group(0)
        return None

    def _on_tree_preview(self, item, col):
        # 点书（叶节点）才显示书籍信息；并激活「书籍信息」页签。其它节点不显示。
        key=self._tree_item_work(item) if item is not None else None
        if key:
            self.detail.setText(self._book_info_text(key))
            self.tab_bottom.setCurrentIndex(0)
        else:
            self.detail.setText("")

    def _on_tree_double_click(self, item, col):
        if not item:
            return
        item.setExpanded(not item.isExpanded())
        mode=self.nav_combo.currentText()
        data=item.data(0, Qt.UserRole)
        if not data:
            return
        # 单本书叶：三栏=加入工作区；二栏=直接加入右栏（移动）
        work=self._tree_item_work(item)
        if work:
            if self._layout_mode()=="two":
                added=self._add_to_collection([work], move_out=True)
                self.detail.setText(f"已加入 {work} 到右栏" if added else f"{work} 已在右栏")
            else:
                added=self._ws_add([work])
                self.detail.setText(f"已加入 {work} 到工作区" if added else f"{work} 已在工作区")
            return
        # 作者节点：其全部作品加入工作区
        if mode=="作者" and isinstance(data, dict) and data.get("children"):
            works=[c.get("key","").strip() for c in data.get("children",[])
                   if c.get("key") and self._is_work_id(c.get("key",""))]
            if works:
                added=self._ws_add(works)
                self.detail.setText(f"已加入作者 {data.get('title','')} 的 {len(works)} 部作品（新增 {added} 部）")
                return
        # 丛书节点：把其书目追加到工作区
        if isinstance(data, dict) and isinstance(data.get("work_ids"), list):
            works=[w for w in data.get("work_ids",[]) if self._is_work_id(w)]
            added=self._ws_add(works)
            self.detail.setText(f"已把丛书「{data.get('name','')}」{len(works)} 部追加到工作区（新增 {added} 部）")

    def _add_to_collection(self, works, *, move_out=False):
        """把作品加入当前丛书（按 work_ids 去重）；move_out=True 时同时从工作区移出。

        返回新增数量。右栏操作只动右栏与工作区，不触碰目录树/过滤器/搜索框。
        """
        works=[w for w in (works or []) if self._is_work_id(w)]
        if not works:
            return 0
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            data=str(self._ensure_blank_working())
            for i in range(self.coll_combo.count()):
                if self.coll_combo.itemData(i)==str(data):
                    self.coll_combo.setCurrentIndex(i)
                    break
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                self.detail.setText(f"失败 {e}")
                return 0
        added=0; wg_touched=False
        for w in works:
            if w not in d["work_ids"]:
                d["work_ids"].append(w)
                added+=1
            if w in self._work_groups:
                g=d.setdefault("work_groups",{})
                if g.get(w)!=self._work_groups[w]:
                    g[w]=self._work_groups[w]; wg_touched=True
        if added or wg_touched:
            d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
            self._mark_coll_changed(str(data))
            self._load_coll_works()
        if move_out:
            self._ws_remove(works)
        return added

    # ---------- 书籍列表 ----------
    def _normalize_work(self, w):
        return work_id.canonical_work(w)

    def _is_work_id(self, w):
        # 共享层作品编号 或 本仓文件名形态（T01n0001）；另兼容 catalog 命中
        if work_id.is_work_id(w):
            return True
        return bool(self.mapping.work_exists(work_id.canonical_work(w)))

    def _display_title(self, w):
        m=self.mapping.resolve(w)
        title=self.sutra.title_of(w)
        if title.startswith(w):
            title=title[len(w):].strip()
        if not title and m:
            title=m["name"]
        if not title:
            title=w
        if title.startswith(w):
            title=title[len(w):].strip()
        return title

    # ---------- 工作区（唯一内存目录；中栏与左栏面板两个视图） ----------
    def _work_row_text(self, w):
        # 两个视图共用的条目文字：经号 + 经名（+ 译作者）
        m=self.mapping.resolve(w)
        title=self._display_title(w)
        byline=m.get("byline","") if m else ""
        if byline:
            title=f"{title} [{byline}]"
        return f"{w} {title}"

    def _work_no_key(self, w):
        m=re.match(r"([A-Za-z]+)([0-9A-Za-z]+)", w or "")
        return (m.group(1), m.group(2)) if m else (w or "", "")

    def _ws_display_order(self):
        # 视图级排序（不改 _workspace 的原始加入顺序）
        works=list(self._workspace)
        if self._sort_mode=="经名排序":
            works.sort(key=lambda w: self._display_title(w))
        elif self._sort_mode=="经号排序":
            works.sort(key=self._work_no_key)
        return works

    def _refresh_ws_views(self):
        # 统一刷新：中栏列表 + 左栏工作区树 + 计数/按钮文案
        order=self._ws_display_order()
        self.list.blockSignals(True)
        self.list.clear()
        for w in order:
            item=QListWidgetItem(self._work_row_text(w))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked if w in self._selected else Qt.Unchecked)
            item.setData(Qt.UserRole, w)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self.ws_tree.blockSignals(True)
        self.ws_tree.clear()
        for w in order:
            it=self._work_item(w, self._work_row_text(w))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if w in self._selected else Qt.Unchecked)
            self.ws_tree.addTopLevelItem(it)
        self.ws_tree.blockSignals(False)
        if self.ws_tree.topLevelItemCount():
            self._color_tree_leaves(self.ws_tree)   # 书叶黑色（与目录树一致）
        self._refresh_sel_count()

    def _sync_checks(self):
        # 一处勾选变化 → 两个视图同步（不重建条目）
        for i in range(self.list.count()):
            it=self.list.item(i)
            w=it.data(Qt.UserRole)
            st=Qt.Checked if w in self._selected else Qt.Unchecked
            if it.checkState()!=st:
                self.list.blockSignals(True); it.setCheckState(st); self.list.blockSignals(False)
        for i in range(self.ws_tree.topLevelItemCount()):
            it=self.ws_tree.topLevelItem(i)
            w=(it.data(0, Qt.UserRole) or {}).get("key")
            st=Qt.Checked if w in self._selected else Qt.Unchecked
            if it.checkState(0)!=st:
                self.ws_tree.blockSignals(True); it.setCheckState(0, st); self.ws_tree.blockSignals(False)
        self._refresh_sel_count()

    def _refresh_sel_count(self):
        # 计数：中栏「已选 N 部」/ 左栏「工作区（N 部）」+ 工作区按钮文案
        self.lbl_sel_count.setText(f"已选 {len(self._selected)} 部")
        if hasattr(self, "ws_count"):
            self.ws_count.setText(f"工作区（{len(self._workspace)} 部）")
        self._update_ws_button()

    def _set_sort_mode(self, mode):
        self._sort_mode=mode or "原始顺序"
        for cb in (getattr(self, "sort_combo", None), getattr(self, "ws_sort_combo", None)):
            if cb is None:
                continue
            if cb.currentText()!=self._sort_mode:
                cb.blockSignals(True)
                cb.setCurrentText(self._sort_mode)
                cb.blockSignals(False)
        self._refresh_ws_views()

    def _ws_add(self, works):
        # 去重追加到工作区（唯一入口）
        have={self._normalize_work(w) for w in self._workspace}
        added=0
        for w in (works or []):
            if not w or not self._is_work_id(w):
                continue
            nw=self._normalize_work(w)
            if nw not in have:
                have.add(nw)
                self._workspace.append(w)
                added+=1
        self._refresh_ws_views()
        return added

    def _ws_remove(self, works):
        # 从工作区移出（含勾选清理）
        seen={self._normalize_work(w) for w in (works or []) if w}
        seen.discard("")
        if not seen:
            return 0
        before=len(self._workspace)
        self._workspace=[x for x in self._workspace if self._normalize_work(x) not in seen]
        for v in list(self._selected):
            if self._normalize_work(v) in seen:
                self._selected.discard(v)
        if len(self._workspace)!=before:
            self._refresh_ws_views()
        else:
            self._refresh_sel_count()
        return before-len(self._workspace)

    def _ws_clear(self):
        n=len(self._workspace)
        self._workspace=[]
        self._selected.clear()
        self._work_groups.clear()
        self._refresh_ws_views()
        self.detail.setText(f"已清空工作区（{n} 部）" if n else "工作区已空")

    def _ws_selected(self):
        # 勾选的书，按工作区显示顺序排列（_selected 是 set，直接遍历会乱序）
        out=[]; seen=set()
        for w in self._ws_display_order():
            if w in self._selected and w not in seen:
                seen.add(w); out.append(w)
        for w in sorted(self._selected):
            if w not in seen:
                seen.add(w); out.append(w)
        return out

    def _select_all(self):
        self._selected={w for w in self._workspace}
        self._sync_checks()

    def _clear_all(self):
        self._selected.clear()
        self._sync_checks()

    def _on_list_changed(self, item):
        w=item.data(Qt.UserRole)
        if item.checkState()==Qt.Checked:
            self._selected.add(w)
        else:
            self._selected.discard(w)
        self._sync_checks()

    def _on_ws_item_changed(self, item, col):
        if col!=0 or item is None:
            return
        w=(item.data(0, Qt.UserRole) or {}).get("key")
        if not w:
            return
        if item.checkState(0)==Qt.Checked:
            self._selected.add(w)
        else:
            self._selected.discard(w)
        self._sync_checks()

    def _on_list_detail(self, item):
        if not item:
            return
        self.detail.setText(self._book_info_text(item.data(Qt.UserRole)))
        # 点书 → 激活「书籍信息」页签
        self.tab_bottom.setCurrentIndex(0)

    def _on_list_double_add(self, item):
        # 中栏双击书 = 加入右栏（移动），与左栏工作区双击一致
        if not item:
            return
        self._ws_double_add(item.data(Qt.UserRole))

    def _ws_double_add(self, w):
        if not w:
            return
        added=self._add_to_collection([w], move_out=True)
        self.detail.setText(f"已加入 {w} 到右栏，已移出工作区" if added
                            else f"{w} 已在右栏，已移出工作区")

    def _list_key_press(self, e):
        from PySide6.QtCore import Qt as _Qt
        if e.key()==_Qt.Key_Space:
            for it in self.list.selectedItems():
                w=it.data(Qt.UserRole)
                if it.checkState()==_Qt.Checked:
                    self._selected.discard(w)
                else:
                    self._selected.add(w)
            self._sync_checks()
            e.accept()
            return
        if e.key() in (_Qt.Key_Delete, _Qt.Key_Backspace):
            sel=[it.data(Qt.UserRole) for it in self.list.selectedItems()]
            if sel:
                self._ws_remove(sel)
                self.detail.setText(f"已移出工作区 {len(sel)} 部")
                e.accept()
                return
        from PySide6.QtWidgets import QListWidget as _L
        _L.keyPressEvent(self.list, e)

    def _ws_key_press(self, e):
        from PySide6.QtCore import Qt as _Qt
        if e.key()==_Qt.Key_Space:
            for it in self.ws_tree.selectedItems():
                w=(it.data(0, Qt.UserRole) or {}).get("key")
                if not w:
                    continue
                if it.checkState(0)==_Qt.Checked:
                    self._selected.discard(w)
                else:
                    self._selected.add(w)
            self._sync_checks()
            e.accept()
            return
        if e.key() in (_Qt.Key_Delete, _Qt.Key_Backspace):
            sel=self._ws_tree_selected_works()
            if sel:
                self._ws_remove(sel)
                self.detail.setText(f"已移出工作区 {len(sel)} 部")
                e.accept()
                return
        from PySide6.QtWidgets import QTreeWidget as _T
        _T.keyPressEvent(self.ws_tree, e)

    def _ws_tree_selected_works(self):
        # 左栏工作区树选中项 → 作品 id（保序去重）
        out=[]; seen=set()
        for it in self.ws_tree.selectedItems():
            w=(it.data(0, Qt.UserRole) or {}).get("key")
            nw=self._normalize_work(w)
            if w and nw not in seen and self._is_work_id(w):
                seen.add(nw); out.append(w)
        return out

    def _data_work_ids(self, data):
        # dict 节点（作者/朝代/刊本叶等）递归取作品 id
        out=[]
        for c in (data.get("children") or []):
            if not isinstance(c, dict):
                continue
            if c.get("children"):
                out.extend(self._data_work_ids(c))
            elif c.get("key"):
                out.append(c["key"])
        return out

    def _item_group_label(self, data):
        # 册标签：优先「册标题」，其次「刊本名」
        if isinstance(data, dict):
            if data.get("vol_title"):
                return data["vol_title"]
            if data.get("vol"):
                return data["vol"]
        return ""

    def _item_payload(self, it, group=""):
        # 目录树节点 → [(work_id, 册标签)]；父节点展开其全部子孙
        data=it.data(0, Qt.UserRole)
        g=self._item_group_label(data) or group
        if it.childCount():
            out=[]
            for i in range(it.childCount()):
                out.extend(self._item_payload(it.child(i), g))
            return out
        if isinstance(data, dict):
            if data.get("work_ids"):
                return [(w, g) for w in data["work_ids"] if w]
            if data.get("children"):
                return [(w, g) for w in self._data_work_ids(data)]
            return [(data["key"], g)] if data.get("key") else []
        if hasattr(data, "title"):
            return [(w, g) for w in re.findall(r"[A-Z]+[0-9A-Za-z]+", data.title)]
        return []

    def _tree_mimeData(self, items):
        # 自定义树拖拽数据：text/plain = 作品 id（每行一个，兼容外部）；
        # application/x-cbeta-groups = JSON {work_id: 册标签}（按册分册用）
        from PySide6.QtCore import QMimeData
        ids=[]; seen=set(); groups={}
        for it in (items or []):
            for wid, g in self._item_payload(it):
                if wid and wid not in seen:
                    seen.add(wid); ids.append(wid)
                    if g:
                        groups[wid]=g
        md=QMimeData()
        md.setText("\n".join(ids))
        if groups:
            md.setData("application/x-cbeta-groups",
                       json.dumps(groups, ensure_ascii=False).encode("utf-8"))
        return md

    def _mime_works_groups(self, md):
        # 从拖拽数据解析 (works, groups)
        works=re.findall(r"[A-Z]+[0-9A-Za-z]+", (md.text() or ""))
        groups={}
        try:
            raw=bytes(md.data("application/x-cbeta-groups"))
            if raw:
                groups=json.loads(raw.decode("utf-8"))
        except Exception:
            groups={}
        return works, groups

    def _tree_selected_works(self):
        # 从目录树选中项提取作品 id（统一走 _item_payload：父节点展开全部子孙；
        # 兼容部类/作者节点、刊本叶、丛书节点与二栏的选书区节点）
        out=[]; seen=set()
        for it in self.tree.selectedItems():
            for w, _g in self._item_payload(it):
                nw=self._normalize_work(w)
                if w and nw not in seen and self._is_work_id(w):
                    seen.add(nw); out.append(w)
        return out

    def _drop_move(self, e, view):
        # 真实鼠标拖放：Qt 默认 dragMoveEvent 会拒收外部拖拽（dropEvent 永不到达，
        # 合成 FakeDrop 测试发现不了）；先走默认实现保留内部排序指示器，再强制放行。
        try:
            type(view).dragMoveEvent(view, e)
        except Exception:
            pass
        try:
            e.acceptProposedAction()
        except Exception:
            pass

    def _list_drag_enter(self, e):
        e.acceptProposedAction()

    def _coll_dragged_works(self, e):
        # 右栏拖出的作品：选中项 UserRole；兜底 mime 文本（真实拖拽只有内部 model mime）
        works=[]
        for it in self.coll_list.selectedItems():
            w=it.data(Qt.UserRole)
            if w:
                works.append(w)
        if not works:
            md=e.mimeData() if e is not None else None
            works=re.findall(r"[A-Z]+[0-9A-Za-z]+", (md.text() if md else "") or "")
        return works

    def _list_drop(self, e):
        # 右栏拖到中栏工作区 = 从丛书移除（书进工作区）；工作区自身拖拽 = 重新排序
        if e.source() is self.coll_list:
            self._remove_works_from_collection(self._coll_dragged_works(e))
            e.acceptProposedAction()
            return
        if e.source() is self.list:
            from PySide6.QtWidgets import QListWidget as _L
            old_order=self._workspace[:]
            _L.dropEvent(self.list, e)
            new_order=[]
            for i in range(self.list.count()):
                w=self.list.item(i).data(Qt.UserRole)
                if w:
                    new_order.append(w)
            if new_order and new_order!=old_order:
                self._workspace=new_order
                self._refresh_ws_views()
                self.detail.setText("已重新排序工作区")
            e.acceptProposedAction()
            return
        try:
            works, groups=self._mime_works_groups(e.mimeData())
            if not works:
                works=self._tree_selected_works()
            for w in works:
                if w not in self._work_groups and w in groups:
                    self._work_groups[w]=groups[w]
            if works:
                added=self._ws_add(works)
                self.detail.setText(f"拖入工作区 {added} 部，共 {len(self._workspace)} 部")
                e.acceptProposedAction()
                return
        except Exception as ex:
            print(ex)
        e.ignore()

    def _tree_drag_enter(self, e):
        e.acceptProposedAction()

    def _tree_drop(self, e):
        # 右栏拖入目录树 = 从丛书移除（书进工作区）；工作区/中栏拖入 = 从工作区移出；
        # 树自身内部拖拽忽略
        if e.source() is self.coll_list:
            works=self._coll_dragged_works(e)
            if works:
                self._remove_works_from_collection(works)
                e.acceptProposedAction()
                return
            e.ignore()
            return
        if e.source() is self.tree:
            e.ignore()
            return
        if e.source() is self.list or e.source() is getattr(self, "ws_tree", None):
            works=self._tree_drop_works(e)
            if works:
                n=self._ws_remove(works)
                self.detail.setText(f"已移出工作区 {n} 部" if n else "未找到可移除项")
                e.acceptProposedAction()
                return
            e.ignore()
            return
        e.ignore()

    def _tree_drop_works(self, e):
        # 从拖拽事件解析作品 id：优先选中项（真实拖拽只有内部 model mime），再兜底 mime 文本
        works=[]
        src=e.source()
        if src is self.list:
            for i in range(self.list.count()):
                it=self.list.item(i)
                if it and it.isSelected():
                    w=it.data(Qt.UserRole)
                    if w:
                        works.append(w)
        elif src is getattr(self, "ws_tree", None):
            works=self._ws_tree_selected_works()
        if not works:
            works=re.findall(r"[A-Z]+[0-9A-Za-z]+", (e.mimeData().text() if e.mimeData() else "") or "")
        seen=set(); uniq=[]
        for w in works:
            nw=self._normalize_work(w)
            if nw not in seen:
                seen.add(nw); uniq.append(w)
        return uniq

    def _remove_works_from_collection(self, works):
        """从当前丛书移除书籍：册标签搬回内存，并把书加入工作区。

        右栏书目操作只影响右栏与工作区，不触碰目录树/过滤器/搜索框。
        """
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择丛书")
            return
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                self.detail.setText(f"失败 {e}")
                return
        seen={self._normalize_work(w) for w in works if w}
        seen.discard("")
        if not seen:
            return
        wg=d.get("work_groups") or {}
        ws=d.get("work_sources") or {}
        rm=[]; kept=[]
        for w in d["work_ids"]:
            if self._normalize_work(w) in seen:
                rm.append(w)
                g=wg.get(w)                    # 册标签搬回内存，再次加入后可恢复
                if g:
                    self._work_groups[w]=g
            else:
                kept.append(w)
        if not rm:
            self.detail.setText("所选不在丛书中")
            return
        d["work_ids"]=kept
        for k in list(wg):                     # 清掉已移除书的册标签/来源，避免脏数据
            if self._normalize_work(k) in seen:
                wg.pop(k, None)
        d["work_groups"]=wg
        for k in list(ws):
            if self._normalize_work(k) in seen:
                ws.pop(k, None)
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        self._mark_coll_changed(str(data))
        self._load_coll_works()
        self._ws_add(rm)
        self.detail.setText(f"已移除 {len(rm)} 部（已进工作区，可再加入），剩余 {len(kept)} 部")

    # ---------- 搜索 ----------
    def _search_variants(self, kw):
        # 变体集：常见异体/通假字（花↔華 等）+ 原样，用于拓宽匹配
        out={kw}
        for a,b in [("花","華")]:
            if a in kw:
                out.add(kw.replace(a,b))
            if b in kw:
                out.add(kw.replace(b,a))
        return out

    def _author_search(self, kw):
        # 作者搜索：原词 + 繁简 + 异体变体逐一尝试
        for v in self._search_variants(kw):
            for q in {v, text_util.to_simplified(v), text_util.to_traditional(v)}:
                res=self.creator.search(q)
                if res:
                    return res
        return None

    def _search_author_works(self, res):
        # 合并最多 5 位命中作者的作品（去重）
        works=[]
        for r in res[:5]:
            for w in self.creator.works_of(r["id"]):
                k=(w.get("key") or "").strip()
                if k:
                    works.append(k)
        seen=set()
        out=[]
        for wk in works:
            if wk not in seen:
                seen.add(wk)
                out.append(wk)
        return out

    def _is_known_work(self, w):
        # 树标题里抓出的候选是否为真实作品（滤掉 T01 这类分组号）
        return len(w)>=4 and (self.sutra.title_of(w)!=w or self.mapping.work_exists(w))

    def _search_current_tree(self, kw):
        """在当前左栏树里按关键字找节点（大小写不敏感；繁简/异体变体），命中即取其全部子孙作品。

        覆盖所有视图（部类/三藏/刊本/朝代/作者/丛书），与原先只对部类生效的行为一致。
        """
        kw_l=kw.lower()
        vars_kw_s={text_util.to_simplified(v).lower() for v in self._search_variants(kw)}
        def _hit(text):
            tl=(text or "").lower()
            if kw_l in tl:
                return True
            ts=text_util.to_simplified(text).lower()
            return any(kv in ts for kv in vars_kw_s)
        out=[]; seen=set()
        def walk(it):
            if _hit(it.text(0)):
                for wid, _g in self._item_payload(it):
                    if wid and wid not in seen and self._is_known_work(wid):
                        seen.add(wid); out.append(wid)
                return
            for i in range(it.childCount()):
                walk(it.child(i))
        # 二栏选书区占用左栏时，导航树被暂存：搜索暂存的导航树而不是选书区
        if self._nav_stash:
            roots=list(self._nav_stash)
        else:
            roots=[self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        for it in roots:
            walk(it)
        return out

    def _on_search(self, kw):
        # 搜索目录（当前导航视图，繁简/异体/大小写不敏感），结果渲染到左栏；
        # 不再写入中栏（中栏=工作区，只由用户显式加入）。
        kw=(kw or "").strip()
        if not kw:
            self._search_results=[]
            self._render_search_to_left()
            return
        # 作者模式：优先作者搜索（避免被其它匹配抢占）
        if self.nav_combo.currentText()=="作者":
            res=self._author_search(kw)
            if res:
                filtered=self._search_author_works(res)
                if filtered:
                    self._search_results=filtered[:200]
                    self._render_search_to_left()
                    return
        self._search_results=self._search_current_tree(kw)[:200]
        self._render_search_to_left()

    # ---------- 丛书操作 ----------
    def _mark_coll_changed(self, path=None):
        self._coll_changed=True
        if path is None:
            data=self.coll_combo.currentData()
            if isinstance(data,str) and not self._is_coll_placeholder(data):
                path=data
        if path:
            self._changed_colls.add(str(path))
        self._update_coll_marks()

    def _update_coll_marks(self):
        # 未保存改动：丛书名后加星号
        for i in range(self.coll_combo.count()):
            data=self.coll_combo.itemData(i)
            if not isinstance(data,str) or self._is_coll_placeholder(data):
                continue
            text=self.coll_combo.itemText(i)
            if text.endswith(" *"):
                base=text[:-2]
            elif text.endswith("*"):
                base=text[:-1]
            else:
                base=text
            if str(data) in self._changed_colls:
                if not text.endswith(" *"):
                    self.coll_combo.setItemText(i, f"{base} *")
            else:
                if text.endswith(" *"):
                    self.coll_combo.setItemText(i, base)

    def _add_selected_to_coll(self):
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            # 无丛书选中：自动转到空白工作丛书并加入
            target=self._ensure_blank_working()
            data=str(target)
            for i in range(self.coll_combo.count()):
                if self.coll_combo.itemData(i)==str(target):
                    self.coll_combo.setCurrentIndex(i)
                    break
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                self.detail.setText(f"失败 {e}")
                return
        selected=self._ws_selected()
        added=[]
        wg_touched=False
        for w in selected:
            if w not in d["work_ids"]:
                d["work_ids"].append(w)
                added.append(w)
            if w in self._work_groups:
                g=d.setdefault("work_groups",{})
                if g.get(w)!=self._work_groups[w]:
                    g[w]=self._work_groups[w]; wg_touched=True
        if not added and not wg_touched:
            # 本批都已在右栏：也算“移动”完成，从工作区移出
            if selected:
                self._ws_remove(selected)
            self.detail.setText("所选均已在丛书中（已从工作区移出）")
            return
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        self._mark_coll_changed(str(data))
        self._load_coll_works()
        # 移动语义：加入成功即从工作区移出（目录里仍可搜到）
        self._ws_remove(selected)
        self.detail.setText(f"已加入 {len(added)} 部到 {d['name']}（已从工作区移出），共 {len(d['work_ids'])} 部")

    # ---------- 搜索结果渲染到左栏 ----------
    def _add_pool_node(self, label, works):
        if not works:
            return
        it=QTreeWidgetItem([f"{label}（{len(works)} 部）"])
        it.setData(0, Qt.UserRole, {"pool": label})
        self.tree.addTopLevelItem(it)
        for w in works:
            # 搜索结果带 work id，便于辨认/核对
            it.addChild(self._work_item(w, f"{w}　{self._display_title(w)}"))
        it.setExpanded(True)

    def _tree_expand_state(self, tree=None):
        # 展开状态快照：按「子索引路径」记录，用于暂存/重建后还原使用状态
        tree=tree if tree is not None else self.tree
        state=set()
        def walk(it, path):
            if it.isExpanded():
                state.add(path)
            for i in range(it.childCount()):
                walk(it.child(i), path+(i,))
        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i), (i,))
        return state

    def _apply_tree_expand_state(self, state, tree=None):
        tree=tree if tree is not None else self.tree
        if not state:
            return
        def walk(it, path):
            if path in state:
                it.setExpanded(True)
            for i in range(it.childCount()):
                walk(it.child(i), path+(i,))
        for i in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(i), (i,))

    def _stash_left_tree(self):
        """二栏：选书区要占用左栏时，把导航树顶层项暂存起来（仍可搜索）。

        注意：takeTopLevelItem 会把节点从视图移除，Qt 会丢失其展开状态，
        因此先快照展开路径，恢复时再套用。
        """
        if self._nav_stash is not None:
            return
        self._nav_expand=self._tree_expand_state()
        self._nav_stash=[]
        while self.tree.topLevelItemCount():
            self._nav_stash.append(self.tree.takeTopLevelItem(0))

    def _restore_left_tree(self):
        """二栏：把暂存的导航树放回左栏（含展开状态）。"""
        if self._nav_stash is None:
            return
        state=getattr(self, "_nav_expand", None)
        self.tree.clear()
        for it in self._nav_stash:
            self.tree.addTopLevelItem(it)
        self._nav_stash=None
        self._apply_tree_expand_state(state)

    def _render_search_to_left(self):
        """把当前搜索结果渲染到左栏树（两种布局一致）；无结果则恢复导航树。

        结果视图占用左栏时导航树被暂存（`_nav_stash`），搜索/清除会正确恢复。
        """
        if self._search_results:
            self._stash_left_tree()
            self._left_search_active=True
            self.tree.clear()
            self._add_pool_node("搜索结果", self._search_results)
            self._expand_tree()
        elif self._left_search_active:
            self._left_search_active=False
            self._restore_left_tree()

    # ---------- 工作区面板 ----------
    def _toggle_workspace(self, on):
        # 工作区面板显示时隐藏目录面板（树）；其它控件（导航/搜索）保持可见
        self.ws_page.setVisible(bool(on))
        self.tree.setVisible(not on)
        self._update_ws_button()
        if on:
            self._refresh_ws_views()

    def _update_ws_button(self):
        btn=getattr(self, "btn_workspace", None)
        if btn is None:
            return
        # 勾选=正在看工作区 → 按钮提示切回「目录区」；未勾选 → 「工作区（N）」
        n=len(getattr(self, "_workspace", []) or [])
        if btn.isChecked():
            btn.setText(f"目录区（{n}）" if n else "目录区")
        else:
            btn.setText(f"工作区（{n}）" if n else "工作区")

    def _ws_add_search(self):
        # 一键：把当前搜索结果加入工作区（也就是加入中栏，二者同一份数据）
        if not self._search_results:
            self.detail.setText("当前没有可加入的搜索结果")
            return
        added=self._ws_add(self._search_results)
        self.detail.setText(f"已加入 {added} 部到工作区，共 {len(self._workspace)} 部" if added
                            else "工作区已有这些书")

    def _ws_drop(self, e):
        # 工作区左栏树只接受右栏拖入 = 从丛书移除（书经 _remove_works_from_collection 流入工作区）；
        # 其它来源忽略。移除后不自动切到工作区面板，用户点「工作区」才进入。
        if e.source() is self.coll_list:
            works=self._coll_dragged_works(e)
            if works:
                self._remove_works_from_collection(works)
                e.acceptProposedAction()
                return
        e.ignore()

    def _on_ws_double_click(self, item, col):
        # 工作区双击书 = 加入右栏（移动），与中栏双击一致
        self._ws_double_add(self._tree_item_work(item) if item is not None else None)

    def _new_collection(self):
        # 工作区勾选优先；没有勾选则用目录树当前选中
        works=self._ws_selected() or self._tree_selected_works()
        self._create_collection_dialog(works)

    def _ensure_blank_working(self, select=True):
        # 确保存在唯一的空白工作丛书“空白丛书”（不存在则创建并落盘）
        # select=False 时仅确保存在，不改动当前选中（启动恢复上次丛书时用）
        cdir=Path(self.config["collections_dir"])
        target=None
        for p,d in self._collections:
            if d.get("name")=="空白丛书":
                target=p
                break
        if target is None:
            d=create_collection("空白丛书","custom",["custom"],[]).to_dict()
            cat_dir=cdir/"custom"
            target=cat_dir/"空白丛书.json"
            taken={str(x) for x in cat_dir.glob("*.json")} | {str(pp) for pp,_ in self._collections}
            if str(target) in taken:
                base=target.stem
                i=1
                while str(target) in taken:
                    target=cat_dir/f"{base}_{i}.json"
                    i+=1
            try:
                cat_dir.mkdir(parents=True, exist_ok=True)
                content=json.dumps(d, ensure_ascii=False, indent=2)
                target.write_text(content, encoding="utf-8")
                self._collections.append((target,d))
                self._coll_originals[str(target)]=content
            except Exception as e:
                print(e)
        # 重置分类过滤为全部，确保空白丛书出现在列表中
        self.coll_cat_filter.blockSignals(True)
        if self.coll_cat_filter.count():
            self.coll_cat_filter.setCurrentIndex(0)
        self.coll_cat_filter.blockSignals(False)
        if select:
            self._sync_combo(select_path=str(target))
        return target

    def _new_blank_collection(self):
        # “空白”按钮：选择唯一的空白工作丛书（不存在则创建），并显式刷新书单
        target=self._ensure_blank_working()
        self._load_coll_works()
        if self.nav_combo.currentText()=="丛书":
            self._refresh_coll_tree()
        self.detail.setText("已选择空白丛书（可直接拖入书籍）")

    def _append_collection(self, d):
        # 仅加入内存并标记未保存（不写盘）；点“保存”才落盘
        cdir=Path(self.config["collections_dir"])
        cat_dir=cdir/d.get("category","custom")
        target=cat_dir/f"{d.get('name','未命名')}.json"
        taken={str(p) for p,_ in self._collections} | {str(x) for x in cat_dir.glob("*.json")}
        if str(target) in taken:
            base=target.stem
            i=1
            while str(target) in taken:
                target=cat_dir/f"{base}_{i}.json"
                i+=1
        self._collections.append((target,d))
        self._mark_coll_changed(str(target))
        self._sync_combo(select_path=str(target))
        self._load_coll_works()
        return target

    def _ask_cat_fields(self, title, name="", desc=""):
        # 分类名称+描述 合并对话框；新建返回新 cid，改名返回 None（已保存）
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox
        cdir=Path(self.config["collections_dir"])
        dlg=QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(400)
        form=QFormLayout(dlg)
        ne=QLineEdit(name)
        ne.setPlaceholderText("如：天台宗")
        form.addRow("分类名称", ne)
        de=QLineEdit(desc)
        de.setPlaceholderText("可留空，如：天台宗典籍")
        form.addRow("分类描述", de)
        btns=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec()!=QDialog.Accepted:
            return None
        newname=ne.text().strip()
        if not newname:
            return None
        newdesc=de.text().strip()
        if title=="新建分类":
            try:
                from pypinyin import lazy_pinyin
                cid="".join(lazy_pinyin(newname))[:20]
            except Exception:
                cid=newname[:10]
            if not cid:
                cid="cat"
            try:
                cm=CategoryManager(cdir/"categories.json")
                cm.add(cid, newname, newdesc)
            except ValueError:
                import time as _t
                cm.add(f"{cid}_{int(_t.time())}", newname, newdesc)
            return cm.all()[-1]["id"]
        # 改名模式：返回 (name, desc) 由调用方保存
        return (newname, newdesc)

    def _ask_name_category(self, title, default_name="", current_id=None):
        # 合并弹窗：名称输入框 + 分类下拉（含“＋ 新建分类…”）；返回 (name, cat_id) 或 None
        from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QComboBox as _Cmb
        cdir=Path(self.config["collections_dir"])
        try:
            cm=CategoryManager(cdir/"categories.json")
            cats=cm.all()
        except:
            cats=[]
        dlg=QDialog(self)
        dlg.setWindowTitle(title)
        form=QFormLayout(dlg)
        name_edit=QLineEdit(default_name)
        form.addRow("丛书名称", name_edit)
        cat_combo=_Cmb()
        cat_combo.addItem("＋ 新建分类…", "__new__")
        for c in cats:
            cat_combo.addItem(c['name'] if not c.get('description') else f"{c['name']} ({c['description']})", c["id"])
        if current_id:
            for i in range(cat_combo.count()):
                if cat_combo.itemData(i)==current_id:
                    cat_combo.setCurrentIndex(i)
                    break
        form.addRow("分类", cat_combo)
        btns=QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec()!=QDialog.Accepted:
            return None
        name=name_edit.text().strip()
        if not name:
            return None
        cat=cat_combo.currentData()
        if cat=="__new__":
            # 合并弹窗：分类名称 + 描述 一个对话框（新建/改名共用）
            cid2=self._ask_cat_fields("新建分类")
            if cid2 is None:
                return None
            cat=cid2
            self._sync_combo(select_path=getattr(self, "_last_coll_path", None))
        return (name, cat)

    def _create_collection_dialog(self, works):
        res=self._ask_name_category("新建丛书")
        if res is None:
            return
        name,cat=res
        if self._name_taken(name):
            self._wrap_box(QMessageBox.Warning, "重名", f"已有同名丛书「{name}」，请换一个名称。")
            return
        c=create_collection(name, cat, [], works,
                            work_groups={w: self._work_groups[w] for w in works if w in self._work_groups})
        # 标签为用户管理（横切维度），新建时不自动打标
        target=self._append_collection(c.to_dict())
        # 与「加入已选」一致：新建即从工作区移出（移动语义）
        self._ws_remove(works)
        QMessageBox.information(self,"已创建",f"已加入（保存后落盘）：{target}")

    def _save_as_collection(self):
        # 另存为：当前丛书改名+分类，立即落盘（主要用于空白丛书转正式丛书）
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择要另存为的丛书")
            return
        old_p=str(data)
        p=Path(old_p)
        d=self._coll_dict(old_p)
        if d is None:
            try:
                d=self._read_coll(p)
            except Exception as e:
                self.detail.setText(f"读取失败 {e}")
                return
        res=self._ask_name_category("另存为丛书", d.get("name",""), d.get("category"))
        if not res:
            return
        name,cat=res
        if self._name_taken(name, exclude_path=data):
            self._wrap_box(QMessageBox.Warning, "重名", f"已有同名丛书「{name}」，请换一个名称。")
            return
        d["name"]=name
        d["slug"]=slugify(cat, name)
        d["category"]=cat
        d.setdefault("tags", [])   # 标签由用户维护，改名/另存不改动
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        cdir=Path(self.config["collections_dir"])
        cat_dir=cdir/cat
        target=cat_dir/f"{name}.json"
        taken={str(x) for x in cat_dir.glob("*.json")} | {str(pp) for pp,_ in self._collections}
        if str(target) in taken:
            base=target.stem
            i=1
            while str(target) in taken:
                target=cat_dir/f"{base}_{i}.json"
                i+=1
        try:
            cat_dir.mkdir(parents=True, exist_ok=True)
            content=json.dumps(d, ensure_ascii=False, indent=2)
            target.write_text(content, encoding="utf-8")
        except Exception as e:
            self.detail.setText(f"另存为失败 {e}")
            return
        if str(target)!=old_p:
            p.unlink(missing_ok=True)
        for i,(pp,dd) in enumerate(self._collections):
            if str(pp)==old_p:
                self._collections[i]=(target,d)
                break
        self._coll_originals.pop(old_p, None)
        self._coll_originals[str(target)]=content
        self._changed_colls.discard(old_p)
        self._changed_colls.discard(str(target))
        if not self._changed_colls:
            self._coll_changed=False
        self._sync_combo(select_path=str(target))
        self.detail.setText(f"已另存为「{name}」（分类 {self._cat_name(cat)}）")

    def _save_collections(self):
        if not self._changed_colls:
            self.detail.setText("没有未保存的丛书")
            return
        # 空白丛书（自动命名 空白/空白N）保存前：弹窗改名+归类
        for p in list(self._changed_colls):
            d=self._coll_dict(p)
            if d is None:
                continue
            if self._is_blank_name(d.get("name","")):
                self._finalize_blank_save(p, d)
        saved=0
        for p in list(self._changed_colls):
            d=self._coll_dict(p)
            if d is None:
                continue
            try:
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                self._coll_originals[str(p)]=json.dumps(d, ensure_ascii=False, indent=2)
                saved+=1
            except Exception as e:
                print(e)
        self._changed_colls=set()
        self._coll_changed=False
        self._update_coll_marks()
        self._write_index()
        self.detail.setText(f"已保存 {saved} 部丛书")

    def _finalize_blank_save(self, p, d):
        # 空白丛书保存前弹窗：改正式名称 + 归类（合并为一个对话框）
        cdir=Path(self.config["collections_dir"])
        res=self._ask_name_category("保存空白丛书", d.get("name",""))
        if res is None:
            return False
        name,cat=res
        d["name"]=name
        d["slug"]=slugify(cat, name)
        d["category"]=cat
        d.setdefault("tags", [])   # 标签由用户维护
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        cat_dir=cdir/cat
        target=cat_dir/f"{name}.json"
        taken={str(x) for x in cat_dir.glob("*.json")} | {str(pp) for pp,_ in self._collections}
        if str(target) in taken:
            base=target.stem
            i=1
            while str(target) in taken:
                target=cat_dir/f"{base}_{i}.json"
                i+=1
        if str(target)!=str(p):
            Path(p).unlink(missing_ok=True)
            for i,(pp,dd) in enumerate(self._collections):
                if str(pp)==str(p):
                    self._collections[i]=(target,d)
                    break
            orig=self._coll_originals.pop(str(p), None)
            if orig is not None:
                self._coll_originals[str(target)]=orig
            self._changed_colls.discard(str(p))
        for i in range(self.coll_combo.count()):
            if self.coll_combo.itemData(i)==str(p) or self.coll_combo.itemData(i)==str(target):
                self.coll_combo.setItemData(i, str(target))
                self.coll_combo.setItemText(i, name)
                self.coll_combo.setCurrentIndex(i)
                break
        self._changed_colls.add(str(target))
        return True

    def _restore_collection(self):
        # 恢复当前丛书到上次保存时的书单，并取消星号
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择要恢复的丛书")
            return
        if str(data) not in self._coll_originals:
            self.detail.setText("该丛书尚未保存过，无法恢复")
            return
        if str(data) not in self._changed_colls:
            self.detail.setText("该丛书没有未保存改动")
            return
        try:
            d=json.loads(self._coll_originals[str(data)])
        except Exception as e:
            self.detail.setText(f"恢复失败 {e}")
            return
        for i,(pp,dd) in enumerate(self._collections):
            if str(pp)==str(data):
                self._collections[i]=(pp,d)
                break
        self._changed_colls.discard(str(data))
        if not self._changed_colls:
            self._coll_changed=False
        for i in range(self.coll_combo.count()):
            if self.coll_combo.itemData(i)==str(data):
                self.coll_combo.setItemText(i, d.get("name", Path(data).stem))
                break
        self._update_coll_marks()
        self._load_coll_works()
        self.detail.setText(f"已恢复「{d.get('name','')}」到保存时的书单")

    def _rename_collection(self):
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择要改名的丛书")
            return
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                self.detail.setText(f"读取失败 {e}")
                return
        newname,ok=QInputDialog.getText(self,"丛书改名","新名称", text=d.get("name",""))
        if not ok or not newname.strip():
            return
        newname=newname.strip()
        if newname==d.get("name"):
            return
        # 仅改内存（文件名保持不变，保存时才落盘）
        d["name"]=newname
        d["slug"]=slugify(d.get("category","custom"), newname)
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        for i in range(self.coll_combo.count()):
            if self.coll_combo.itemData(i)==str(data):
                self.coll_combo.setItemText(i, newname)
                break
        self._mark_coll_changed(str(data))
        self.detail.setText(f"已改名：{newname}")

    def _delete_collection(self):
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择要删除的丛书")
            return
        p=Path(data)
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(p)
            except Exception as e:
                self.detail.setText(f"读取失败 {e}")
                return
        unsaved_new = str(p) not in self._coll_originals   # 本会话新建且未保存
        empty = not d.get("work_ids")
        if not (unsaved_new and empty):
            ret=QMessageBox.question(self,"删除丛书", f"确定删除丛书「{d.get('name','')}」？\n（{p}）", QMessageBox.Yes | QMessageBox.No)
            if ret!=QMessageBox.Yes:
                return
        try:
            p.unlink(missing_ok=True)
        except Exception as e:
            self.detail.setText(f"删除失败 {e}")
            return
        self._collections=[x for x in self._collections if str(x[0])!=str(data)]
        self._changed_colls.discard(str(data))
        self._coll_originals.pop(str(data), None)
        if not self._changed_colls:
            self._coll_changed=False
        self._sync_combo()          # 不选中任何丛书，留空
        self._load_coll_works()
        self._write_index()
        self.detail.setText("已删除丛书")

    def _remove_from_coll(self):
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择一个丛书")
            return
        from PySide6.QtWidgets import QCheckBox as _Chk3
        sel=[]
        for i in range(self.coll_list.count()):
            it=self.coll_list.item(i)
            row=self.coll_list.itemWidget(it)
            if row:
                for cb in row.findChildren(_Chk3):
                    if cb.isChecked():
                        w=it.data(Qt.UserRole)
                        if w:
                            sel.append(w)
        if not sel:
            self.detail.setText("请在右栏勾选要移除的书籍")
            return
        # 统一移除入口：册标签搬回内存 + 去重回填选书区末尾（右栏操作不影响左栏）
        self._remove_works_from_collection(sel)

    def _open_link(self, url):
        # 进度日志里的文件/目录链接：用系统默认程序打开（文件→阅读器，目录→资源管理器）
        try:
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(url)
        except Exception as e:
            print(e)

    def _open_publish_link(self, url):
        # 点击右栏信息区的发布链接：打开文件或目录
        try:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl(url))
        except Exception as e:
            print(e)

    def _load_coll_works(self):
        data=self.coll_combo.currentData()
        is_placeholder = self._is_coll_placeholder(data)
        self.coll_list.clear()
        self.lbl_coll_info.setVisible(True)
        if is_placeholder:
            # 分类过滤有效但该分类暂无丛书：显示空提示，不跳转、不重置过滤
            if self.coll_cat_filter.currentData() is not None:
                self.lbl_coll_info.setText("该分类下暂无丛书")
                return
            # 无丛书选中：自动转到唯一的空白工作丛书
            target=self._ensure_blank_working()
            for i in range(self.coll_combo.count()):
                if self.coll_combo.itemData(i)==str(target):
                    self.coll_combo.setCurrentIndex(i)
                    break
            return
        try:
            p=Path(data)
            d=self._coll_dict(data)
            if d is None:
                d=self._read_coll(p)
            import html as _html
            info=f"{_html.escape(d.get('name',''))} [{_html.escape(self._cat_name(d.get('category','')))}] {len(d.get('work_ids',[]))}部<br>最后发布: {_html.escape(str(d.get('last_publish_at','-')))}<br>{_html.escape(str(d.get('last_publish_dir','')))}"
            _tg=d.get("tags",[]) or []
            if _tg:
                _names="、".join(self._tags().name_of(t) for t in _tg)
                info+=f"<br>标签: {_html.escape(_names)}"
            # 发布成功产物：可点击链接（文件/目录）
            for _lname, _lpath in self._last_publish.get(str(data), []):
                from PySide6.QtCore import QUrl as _QU
                info+=f"<br><a href='{_QU.fromLocalFile(_lpath).toString()}'>{_html.escape(_lname)}</a>"
            self.lbl_coll_info.setText(info)
            self._render_coll_rows(d.get("work_ids",[]))
        except Exception as e:
            print(e)

    def _ebook_path(self, w, fmt):
        """按当前来源返回该书的电子书路径（不存在则 None）：
        两边同构 `{root}/{fmt}/…`，根分开（官方 cbeta_ebooks／自制 xml_to_ebooks_dir）。"""
        from cbeta_publish.books import xml2pdf_bridge
        if self._run_source()=="xml":
            return xml2pdf_bridge.find_built(w, fmt, xml2pdf_bridge.xml_books_dir(self.config))
        base=official_ebook_source.official_books_dir(self.config)
        dest=official_ebook_source.local_path(w, fmt, base)
        return dest if dest.exists() else None

    def _render_coll_rows(self, works):
        fmts=self._checked_fmts()
        if not fmts: fmts=["pdf"]
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QCheckBox as _Chk
        icon_dir=Path(__file__).parent / "theme" / "icons"
        for idx, w in enumerate(works, 1):
            title=self.sutra.title_of(w)   # 已含「编号 名称」
            if title==w:                   # 未收录：退回经录名
                m=self.mapping.resolve(w)
                if m: title=f"{w} {m['name']}"
            fmts_status=[]
            for fmt in fmts:
                # 已有标志随来源：官方查 cbeta_ebooks，自制查 xml_to_ebooks_dir
                exists=self._ebook_path(w, fmt) is not None
                fmts_status.append((fmt, exists))
            item=QListWidgetItem()
            item.setData(Qt.UserRole, w)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            missing=[f"{fmt.upper()}未下载" for fmt,ex in fmts_status if not ex]
            item.setToolTip(" ".join(missing) if missing else "")
            row=QWidget()
            # setItemWidget 的子控件会吞掉鼠标事件导致拖拽无法启动；
            # 让整行对鼠标透明，事件直达 viewport 从而可拖拽。
            row.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            hl=QHBoxLayout(row)
            hl.setContentsMargins(2,1,2,1)
            hl.setSpacing(4)
            # 行内复选框：右栏本地标记（供“移除”收集），与中栏勾选缓存(_selected)相互独立；
            # 勾选/取消只改本行视觉，不影响丛书内容与中栏。
            # 注意：行整体对鼠标透明（保证拖拽），子控件收不到事件，
            # 勾选/图标点击统一在 view 层按位置命中处理（eventFilter）。
            cb=_Chk()
            cb.setChecked(False)
            cb.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            cb.setEnabled(True)
            cb.setFocusPolicy(Qt.NoFocus)
            hl.addWidget(cb)
            for fmt, exists in fmts_status:
                lab=QLabel()
                pix=QPixmap(str(icon_dir/(f"{fmt}.png" if exists else f"{fmt}_gray.png")))
                lab.setPixmap(pix.scaled(16,16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                if not exists:
                    lab.setToolTip(f"{fmt.upper()}未下载")
                else:
                    lab.setToolTip("")
                lab.fmt=fmt
                lab.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                hl.addWidget(lab)
            text_lab=QLabel(f"{idx}. {title}")
            text_lab.missing=not any(ex for _,ex in fmts_status)
            if text_lab.missing:
                text_lab.setStyleSheet("color: gray;")
            hl.addWidget(text_lab)
            hl.addStretch()
            # 先激活布局再取 sizeHint，否则新行未布局，图标被裁剪不显示
            hl.activate()
            item.setSizeHint(row.sizeHint())
            self.coll_list.addItem(item)
            self.coll_list.setItemWidget(item, row)

    def _refresh_coll_text_colors(self):
        # 选中行文字转黑（未下载的灰字在绿底上对比不足）；取消选中则恢复
        for i in range(self.coll_list.count()):
            it=self.coll_list.item(i)
            row=self.coll_list.itemWidget(it) if it else None
            if not row:
                continue
            sel=it.isSelected()
            for lab in row.findChildren(QLabel):
                if hasattr(lab, "fmt"):
                    continue
                if sel:
                    lab.setStyleSheet("color: #000;")
                elif getattr(lab, "missing", False):
                    lab.setStyleSheet("color: gray;")
                else:
                    lab.setStyleSheet("")

    def _on_coll_item_detail(self, item):
        if not item:
            return
        self.detail.setText(self._book_info_text(item.data(Qt.UserRole)))
        # 点书 → 激活「书籍信息」页签
        self.tab_bottom.setCurrentIndex(0)

    def eventFilter(self, obj, event):
        # 命中：复选框切换 _selected；P/E 图标双击打开电子书
        try:
            if obj is self.coll_list.viewport():
                t=event.type()
                if t==QEvent.Type.MouseButtonPress and event.button()==Qt.LeftButton:
                    pos=event.position().toPoint()
                    if self._coll_hit_checkbox(pos):
                        return True
                elif t==QEvent.Type.MouseButtonDblClick and event.button()==Qt.LeftButton:
                    pos=event.position().toPoint()
                    if self._coll_hit_icon(pos):
                        return True
        except Exception as ex:
            print(ex)
        return super().eventFilter(obj, event)

    def _coll_hit_checkbox(self, pos):
        item=self.coll_list.itemAt(pos)
        if not item:
            return False
        row=self.coll_list.itemWidget(item)
        if not row:
            return False
        local=row.mapFrom(self.coll_list.viewport(), pos)
        from PySide6.QtWidgets import QCheckBox as _Chk2
        for cb in row.findChildren(_Chk2):
            if cb.geometry().contains(local):
                cb.setChecked(not cb.isChecked())
                return True
        return False

    def _coll_hit_icon(self, pos):
        item=self.coll_list.itemAt(pos)
        if not item:
            return False
        row=self.coll_list.itemWidget(item)
        if not row:
            return False
        local=row.mapFrom(self.coll_list.viewport(), pos)
        for lab in row.findChildren(QLabel):
            if lab.isVisible() and lab.geometry().contains(local) and hasattr(lab,"fmt"):
                self._open_ebook(item.data(Qt.UserRole), prefer=lab.fmt, only_prefer=True)
                return True
        return False

    def _coll_drag_enter(self, e):
        e.acceptProposedAction()

    def _coll_drop(self, e):
        # 内部拖拽（右栏自身）：移动排序
        if e.source() is self.coll_list:
            from PySide6.QtWidgets import QListWidget as _L
            _L.dropEvent(self.coll_list, e)
            self._on_coll_reordered()
            return
        try:
            # 外部拖拽（中栏/目录树/工作区）：提取书籍加入当前丛书
            works, groups=self._mime_works_groups(e.mimeData())
            if not works:
                src=e.source()
                if src is self.list:
                    for i in range(self.list.count()):
                        it=self.list.item(i)
                        if it and it.isSelected():
                            w=it.data(Qt.UserRole)
                            if w:
                                works.append(w)
                elif src is self.tree or src is getattr(self, "ws_tree", None):
                    # 真实鼠标拖拽带的是内部 model mime（无 text/plain）：从选中项提作品+册标签
                    seen=set()
                    for it in src.selectedItems():
                        for wid, g in self._item_payload(it):
                            if not wid or not self._is_work_id(wid):
                                continue
                            nw=self._normalize_work(wid)
                            if nw in seen:
                                continue
                            seen.add(nw)
                            works.append(wid)
                            if g:
                                groups[wid]=g
                else:
                    works=self._ws_selected()
            for w in works:
                if w not in self._work_groups and w in groups:
                    self._work_groups[w]=groups[w]
            if works:
                # 移动语义：来自工作区（中栏列表或左栏工作区树）的拖拽，加入后从工作区移出；
                # 来自目录树的是拷贝（不动工作区）
                added=self._add_to_collection(
                    works, move_out=(e.source() is self.list or e.source() is getattr(self, "ws_tree", None)))
                self.detail.setText(f"拖入 {added} 部")
                e.acceptProposedAction()
                return
        except Exception as ex:
            print(ex)
        from PySide6.QtWidgets import QListWidget as _L
        _L.dropEvent(self.coll_list, e)
        self._on_coll_reordered()

    def _on_coll_double_open(self, item):
        # 双击书名：打开存在的格式（先 PDF 再 epub）；都没有则无反应
        if not item:
            return
        w=item.data(Qt.UserRole)
        self._open_ebook(w, prefer="pdf", only_prefer=False)

    def _on_icon_clicked(self, work, fmt):
        # 双击格式图标：只打开该格式；该格式不存在则无反应
        self._open_ebook(work, prefer=fmt, only_prefer=True)

    def _open_ebook(self, work, prefer="pdf", only_prefer=False):
        """打开电子书（按当前来源取路径：官方 cbeta_ebooks／自制 xml_to_ebooks_dir）。

        only_prefer=True：只尝试 prefer 这一种格式（图标双击）；
        False：依次尝试 prefer → 其它格式（双击书名）。
        没有任何可用文件时不弹窗、不提示，仅返回 False。
        """
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        fmts=[prefer] if only_prefer else [prefer] + [f for f in ("pdf","epub") if f!=prefer]
        for fmt in fmts:
            dest=self._ebook_path(work, fmt)
            if dest is not None and Path(dest).exists():
                try:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(dest).resolve())))
                    self.detail.setText(f"已打开 {Path(dest).name}")
                except Exception as e:
                    self.detail.setText(f"打开失败 {e}")
                return True
        return False

    def _on_coll_reordered(self, *args):
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            return
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception:
                return
        new_order=[]
        for i in range(self.coll_list.count()):
            it=self.coll_list.item(i)
            w=it.data(Qt.UserRole)
            if w:
                new_order.append(w)
        new_order=[w for w in new_order if w]
        if new_order and new_order!=d.get("work_ids",[]):
            d["work_ids"]=new_order
            d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
            self._mark_coll_changed(str(data))
            self.detail.setText("已重新排序")

    def _coll_select_all(self):
        # 右栏全选：选中所有行 + 勾选所有复选框（复选框仅作本栏标记，供“移除”收集）
        from PySide6.QtWidgets import QCheckBox as _Chk4
        for i in range(self.coll_list.count()):
            it=self.coll_list.item(i)
            if not it:
                continue
            it.setSelected(True)
            row=self.coll_list.itemWidget(it)
            if not row:
                continue
            for cb in row.findChildren(_Chk4):
                cb.setChecked(True)

    def _coll_clear_checks(self):
        # 右栏不选：取消所有行选中 + 取消所有复选框勾选（不删除书籍）
        from PySide6.QtWidgets import QCheckBox as _Chk5
        self.coll_list.clearSelection()
        for i in range(self.coll_list.count()):
            it=self.coll_list.item(i)
            if not it:
                continue
            row=self.coll_list.itemWidget(it)
            if not row:
                continue
            for cb in row.findChildren(_Chk5):
                cb.setChecked(False)

    def _move_coll_selection(self, delta):
        # 右栏选中书上/下移一位（多选按块整体移动，保持相对顺序）
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择一个丛书再排序")
            return
        d=self._coll_dict(data)
        if d is None:
            return
        order=list(d.get("work_ids",[]))
        sel=[]
        for i in range(self.coll_list.count()):
            it=self.coll_list.item(i)
            if it and it.isSelected():
                w=it.data(Qt.UserRole)
                if w in order and w not in sel:
                    sel.append(w)
        if not sel:
            self.detail.setText("请先在右栏选中要移动的书籍")
            return
        idx={w:i for i,w in enumerate(order)}
        if delta<0:
            seq=sorted(sel, key=lambda w: idx[w])
            for w in seq:
                i=idx[w]
                if i>0 and order[i-1] not in sel:
                    order[i-1],order[i]=order[i],order[i-1]
                    idx[order[i]]=i
                    idx[order[i-1]]=i-1
        else:
            seq=sorted(sel, key=lambda w: idx[w], reverse=True)
            for w in seq:
                i=idx[w]
                if i<len(order)-1 and order[i+1] not in sel:
                    order[i+1],order[i]=order[i],order[i+1]
                    idx[order[i]]=i
                    idx[order[i+1]]=i+1
        if order!=d.get("work_ids",[]):
            d["work_ids"]=order
            d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
            self._mark_coll_changed(str(data))
            self._load_coll_works()
            first=None
            for i in range(self.coll_list.count()):
                it=self.coll_list.item(i)
                if it and it.data(Qt.UserRole) in sel:
                    it.setSelected(True)
                    if first is None:
                        first=it
            if first is not None:
                self.coll_list.scrollToItem(first, QListWidget.PositionAtCenter)
            self.detail.setText(f"已移动 {len(sel)} 部")

    # ---------- 下载 ----------
    def _download(self):
        # 下载/更新：走弹窗进度（_download_missing），不再占用右下「下载记录」页签
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self.detail.setText("请选择一个丛书")
            return
        p=Path(data)
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(p)
            except Exception as e:
                self.detail.setText(f"读取失败 {e}")
                return
        works=d.get("work_ids",[])
        if not works:
            QMessageBox.warning(self,"失败","丛书为空")
            return
        fmts=self._checked_fmts()
        if not fmts:
            self.detail.setText("请至少选择一种格式 pdf/epub")
            return
        dest_dir=official_ebook_source.official_books_dir(self.config)
        pairs=[(w, f) for w in works for f in fmts]
        ok=self._download_missing(pairs, dest_dir, title="下载/更新")
        st=getattr(self, "_dl_stats", {}) or {}
        if not ok:
            failed=st.get("failed") or []
            if failed:
                QMessageBox.warning(self, "下载失败", f"{len(failed)} 个文件下载失败：\n" + "\n".join(failed[:10]) + (f"\n...共 {len(failed)} 个" if len(failed)>10 else ""))
            self.detail.setText("下载未全部完成")
        else:
            self.detail.setText(f"下载完成 {st.get('ok',0)}/{st.get('total',len(pairs))}")
        self._prompt_save_collection("下载完成，", str(data))

    def _on_make_button(self, regen_all):
        # 右栏「自制」/「重制」：为当前丛书生成自制电子书（整批）
        #   自制 = 仅生成缺少（复用已有）；重制 = 全部重新生成
        fmts=self._checked_fmts()
        if not fmts:
            QMessageBox.warning(self, "失败", "请至少选择一种格式 pdf/epub")
            return
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            QMessageBox.warning(self, "失败", "请选择一个丛书")
            return
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                QMessageBox.warning(self, "失败", f"读取丛书失败 {e}")
                return
        works=d.get("work_ids", [])
        if not works:
            QMessageBox.warning(self, "失败", "丛书为空")
            return
        title="重新生成全部自制电子书" if regen_all else "生成自制电子书"
        from cbeta_publish.books import xml2pdf_bridge
        ok_map, failed, cancelled = self._ensure_xml_batch(
            works, fmts, title=title, regen_all=bool(regen_all), confirm=False)
        n=sum(len(v) for v in ok_map.values())
        if cancelled:
            self.detail.setText(f"已取消（已完成 {n} 部）")
        elif failed:
            self._wrap_box(QMessageBox.Warning, "部分失败",
                           f"完成 {n} 部，失败 {len(failed)}：\n" + "\n".join(failed[:10]))
            self.detail.setText(f"生成完成 {n} 部，失败 {len(failed)}")
        else:
            self.detail.setText(f"{'重制' if regen_all else '生成'}完成 {n} 部 → {xml2pdf_bridge.xml_books_dir(self.config)}")
        self._load_coll_works()

    def _on_download_button(self):
        self._download()

    def _download_missing(self, pairs, dest_dir, title="下载", autoclose_ok=False):
        """下载缺失书籍并弹进度窗（合并/ZIP/导出 前置调用）。

        pairs: [(work, fmt), ...]。下载在 DownloadWorker 线程里跑，用嵌套事件循环
        保持窗口可响应（否则下载期间界面会“无响应”）。返回 True 表示全部下载成功。
        autoclose_ok=True（合并/ZIP/导出 前置）时，若没有失败也没有取消，
        提示 3 秒后自动关闭窗口并继续后续步骤。
        """
        from cbeta_publish.books.download_worker import DownloadWorker, REPLACE_LAST
        from PySide6.QtCore import QEventLoop
        if not pairs:
            return True
        total=max(1, len(pairs))
        dlg, update, pstate = self._make_progress(title, total)
        result={"ok": 0, "failed": []}
        done={"n": 0}
        def on_progress(msg):
            # 「下载 X ...」不计数；「\r下载 X ...完成/更新/失败」计一件已完成
            if msg.startswith(REPLACE_LAST):
                done["n"]+=1
            update(done["n"], msg)
        def on_done(ok, tot, failed):
            result["ok"]=ok
            result["failed"]=list(failed)
        worker=DownloadWorker(dest_dir=dest_dir, pairs=list(pairs))
        worker.progress.connect(on_progress)
        worker.finished_all.connect(on_done)
        pstate["oncancel"]=worker.stop
        loop=QEventLoop()
        worker.finished_all.connect(lambda *a: loop.quit())
        worker.start()
        loop.exec()
        try:
            worker.wait()
        except Exception:
            pass
        failed=result["failed"]
        summary=[]
        if result["ok"]:
            summary.append(f"下载完成 {result['ok']}/{total}")
        if failed:
            summary.append(f"失败 {len(failed)}：{', '.join(failed[:10])}")
        if pstate["cancel"]:
            summary.append("已取消下载。")
        if autoclose_ok and not failed and not pstate["cancel"]:
            summary.append("没有出错，3 秒后自动关闭并继续…")
            pstate["autoclose_ms"]=3000
        pstate["finish"](summary or ["无可下载项。"])
        self._dl_stats={"ok": result["ok"], "total": total, "failed": list(failed),
                        "cancel": bool(pstate["cancel"])}
        self._load_coll_works()
        return (not failed) and (not pstate["cancel"])

    def _commit_publish_meta(self, data, d):
        # 发布元数据：丛书已有未保存改动则并入脏状态（保存时一起落盘）；
        # 否则直接落盘并更新基线，避免"刚保存又提示未保存"
        was_dirty=str(data) in self._changed_colls
        if was_dirty:
            self._mark_coll_changed(str(data))
        else:
            try:
                p=Path(data)
                p.parent.mkdir(parents=True, exist_ok=True)
                content=json.dumps(d, ensure_ascii=False, indent=2)
                p.write_text(content, encoding="utf-8")
                self._coll_originals[str(data)]=content
            except Exception as e:
                print(e)

    def _dirty_coll_names(self):
        # 脏丛书 [(path, name)]，按名称排序，用于弹窗列出
        out=[]
        for p in self._changed_colls:
            d=self._coll_dict(p)
            name=(d.get("name") if d else None) or Path(p).stem
            out.append((p, name))
        out.sort(key=lambda x: x[1])
        return out

    def _is_blank_name(self, name):
        # 空白临时名：“空白丛书”（工作丛书）或“空白/空白N”（历史自动命名）
        return bool(re.fullmatch(r"空白丛书|空白\d*", (name or "").strip()))

    def _save_one_collection(self, path):
        # 只保存指定丛书，不影响其它未保存丛书
        path=str(path)
        d=self._coll_dict(path)
        if d is None:
            return False
        if self._is_blank_name(d.get("name","")):
            if self._finalize_blank_save(path, d) is False:
                return False
            for pp,dd in self._collections:
                if dd is d:
                    path=str(pp)
                    break
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            self._coll_originals[path]=json.dumps(d, ensure_ascii=False, indent=2)
        except Exception as e:
            print(e)
            return False
        self._changed_colls.discard(path)
        if not self._changed_colls:
            self._coll_changed=False
        self._update_coll_marks()
        self._write_index()
        self.detail.setText(f"已保存「{d.get('name',Path(path).stem)}」")
        return True

    def _revert_one_collection(self, path):
        # 只还原指定丛书到快照，不影响其它未保存丛书，不跳走当前选中
        path=str(path)
        if path not in self._changed_colls:
            return
        cur=self.coll_combo.currentData()
        cur_str=str(cur) if isinstance(cur,str) else None
        if path in self._coll_originals:
            try:
                d2=json.loads(self._coll_originals[path])
            except Exception:
                d2=None
            if d2 is not None:
                d=self._coll_dict(path)
                if d is not None:
                    d.clear()
                    d.update(d2)
        else:
            # 本会话新建未保存：从内存丢弃并删除文件
            self._collections=[x for x in self._collections if str(x[0])!=path]
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
            self._sync_combo(select_path=cur_str if cur_str!=path else None)
        self._changed_colls.discard(path)
        if not self._changed_colls:
            self._coll_changed=False
        self._update_coll_marks()
        if cur_str==path:
            self._load_coll_works()
        self.detail.setText("已还原该丛书改动，其它丛书不受影响")

    def _prompt_save_collection(self, reason="", scope=None):
        # scope 指定当前操作的丛书路径：只处理该丛书的脏状态，不影响其它未保存丛书；
        # scope 为 None 时为全局（退出等），列出全部脏丛书
        if scope is not None:
            scope=str(scope)
            d=self._coll_dict(scope)
            name=(d.get("name") if d else None) or Path(scope).stem
            is_blank=self._is_blank_name(name)
            if not is_blank and scope not in self._changed_colls:
                return
            box=QMessageBox(self)
            box.setWindowTitle("保存丛书")
            box.setIcon(QMessageBox.Question)
            if is_blank:
                box.setText(f"{reason}「{name}」是临时名称（无意义），是否另存为正式名称？")
                box.setInformativeText("选「暂不保存」保留在内存，退出时可再处理；其它未保存丛书不动。")
            else:
                box.setText(f"{reason}「{name}」有未保存改动，是否立即保存？")
                box.setInformativeText("选「暂不保存」则改动保留在内存（不还原），退出时可再保存；其它未保存丛书不动。")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setButtonText(QMessageBox.Yes, "立即保存")
            box.setButtonText(QMessageBox.No, "暂不保存")
            ret=box.exec()
            if ret==QMessageBox.Yes:
                self._save_one_collection(scope)
            else:
                self.detail.setText(f"「{name}」改动未保存（保留在内存）")
            return
        if not self._coll_changed:
            return
        names="\n".join(f"・{n}" for _,n in self._dirty_coll_names())
        ret=QMessageBox.question(self, "保存丛书", f"{reason}以下丛书有未保存改动，是否保存？\n{names}", QMessageBox.Yes | QMessageBox.No)
        if ret==QMessageBox.Yes:
            self._save_collections()
        else:
            self._revert_collections()

    def _revert_collections(self):
        # 还原所有丛书到会话开始/上次保存的快照；未保存的新建丛书直接丢弃
        restored=[]
        for p,d in self._collections:
            if str(p) in self._coll_originals:
                try:
                    d2=json.loads(self._coll_originals[str(p)])
                except Exception:
                    d2=d
                restored.append((p,d2))
            else:
                # 本会话新建未保存：丢弃并删除可能已存在的文件
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
        self._collections=restored
        self._coll_changed=False
        self._changed_colls=set()
        self._sync_combo()
        self._load_coll_works()
        self.detail.setText("已还原丛书改动")

    def closeEvent(self, event):
        if self._coll_changed:
            names="\n".join(f"・{n}" for _,n in self._dirty_coll_names())
            ret=QMessageBox.question(self, "退出", f"以下丛书有未保存改动，是否保存？\n{names}", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ret==QMessageBox.Cancel:
                event.ignore()
                return
            elif ret==QMessageBox.Yes:
                self._save_collections()
            else:
                self._revert_collections()
        event.accept()

    # ---------- 合并 ----------
    def _out_dir(self):
        """丛书（合并/ZIP/导出）输出根：缺省 collections_books，相对按工程根解析。"""
        from cbeta_publish.books import xml2pdf_bridge
        p=Path(self.config.get("output_dir") or "collections_books")
        return p if p.is_absolute() else xml2pdf_bridge.PROJECT_ROOT / p

    def _build_menu(self):
        # 菜单栏：「设置…」直接放在菜单栏（不用 设置→设置 两级）
        from cbeta_publish.gui.settings_dialog import SettingsDialog
        bar=self.menuBar()
        act_settings=bar.addAction("设置…")
        act_settings.setToolTip("打开设置（Ctrl+,）")
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self._open_settings)
        m_tools=bar.addMenu("工具")
        act_xml2pdf=m_tools.addAction("xml2pdf 独立窗…")
        act_xml2pdf.setToolTip("打开 E:/dev/cbeta/xml2pdf 独立转换窗")
        act_xml2pdf.triggered.connect(self._open_xml2pdf_window)
        act_verify_send=m_tools.addAction("送当前丛书去校验…")
        act_verify_send.setToolTip("把当前丛书单发往独立窗批量生成+校验（产物与报告落校验目录）")
        act_verify_send.triggered.connect(self._send_coll_to_verify)
        act_verify_import=m_tools.addAction("导入校验通过项…")
        act_verify_import.setToolTip("把校验目录中验证通过的书拷入自制书目录（平展命名）")
        act_verify_import.triggered.connect(self._import_verified)
        # 视图 → 布局（三栏含选书区 / 二栏隐藏选书区）
        from PySide6.QtGui import QActionGroup
        m_view=bar.addMenu("视图")
        self.layout_action_group=QActionGroup(self)
        self.layout_action_group.setExclusive(True)
        self.act_three=m_view.addAction("三栏（含选书区）")
        self.act_two=m_view.addAction("二栏（隐藏选书区）")
        for _a, _lay in ((self.act_three, "three"), (self.act_two, "two")):
            _a.setCheckable(True)
            self.layout_action_group.addAction(_a)
            _a.triggered.connect(lambda _c=False, l=_lay: self._apply_layout(l))
        (self.act_two if self._layout_mode()=="two" else self.act_three).setChecked(True)

    def _open_xml2pdf_window(self):
        # 子进程启动 xml2pdf 独立窗（python -m pycbeta.gui）
        import subprocess, sys
        x2p=Path(self.config.get("xml2pdf",{}).get("path","E:/dev/cbeta/xml2pdf"))
        if not x2p.exists():
            QMessageBox.warning(self,"未找到",f"xml2pdf 路径不存在：{x2p}")
            return
        try:
            subprocess.Popen([sys.executable,"-m","pycbeta.gui"], cwd=str(x2p))
        except Exception as e:
            QMessageBox.warning(self,"启动失败",str(e))

    def _verify_coll(self):
        """当前丛书 (data, d, works)；占位/空/读失败返回 None（已弹窗）。"""
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            self._wrap_box(QMessageBox.Warning, "失败", "请选择一个丛书")
            return None
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                self._wrap_box(QMessageBox.Warning, "失败", f"读取丛书失败 {e}")
                return None
        works=d.get("work_ids",[]) or []
        if not works:
            self._wrap_box(QMessageBox.Warning, "失败", "丛书为空")
            return None
        return data, d, works

    def _send_coll_to_verify(self):
        """一键送校验：书单写校验目录 ids 文件，独立窗预填后自动开跑（detached）。"""
        import subprocess, sys
        from cbeta_publish.books import xml2pdf_bridge as _b
        got=self._verify_coll()
        if got is None:
            return
        _data, d, works=got
        if getattr(self, "_tmp_preset", None) is not None:
            self._wrap_box(QMessageBox.Warning, "临时预设未保存",
                           "「调整…」的临时预设尚未保存，请先保存（覆盖/另存为）再送校验。")
            return
        x2p=Path((self.config.get("xml2pdf",{}) or {}).get("path","") or "E:/dev/cbeta/xml2pdf")
        if not x2p.exists():
            self._wrap_box(QMessageBox.Warning,"未找到",f"xml2pdf 路径不存在：{x2p}")
            return
        slug=str(d.get("id") or d.get("name") or "")
        vdir=_b.verify_coll_dir(self.config, slug)
        try:
            vdir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._wrap_box(QMessageBox.Warning,"失败",f"校验目录不可写：{e}")
            return
        ids_file=vdir/f"{vdir.name}_ids.txt"
        try:
            ids_file.write_text("\n".join(works)+"\n", encoding="utf-8")
        except Exception as e:
            self._wrap_box(QMessageBox.Warning,"失败",f"书单写失败：{e}")
            return
        argv=[sys.executable,"-m","pycbeta.gui","--ids-file",str(ids_file),
              "--out",str(vdir),"--verify","--autostart"]
        preset_name=(self.config.get("xml2pdf",{}) or {}).get("preset","")
        if preset_name:
            argv+=["--preset",preset_name]
        try:
            subprocess.Popen(argv, cwd=str(x2p))
        except Exception as e:
            self._wrap_box(QMessageBox.Warning,"启动失败",str(e))
            return
        self.detail.setText(f"已送独立窗校验 {len(works)} 部 → {vdir}")
        self._wrap_box(QMessageBox.Information,"已发送",
                       f"已送独立窗校验 {len(works)} 部，产物与报告在：\n{vdir}\n"
                       f"校验完成后用「导入校验通过项…」入库。")

    def _import_verified(self):
        """一键导入通过项：校验目录报告判通过 → `{id 书名}.{fmt}` 拷入自制书目录改名平展。"""
        import shutil
        from cbeta_publish.books import xml2pdf_bridge as _b
        got=self._verify_coll()
        if got is None:
            return
        _data, d, works=got
        slug=str(d.get("id") or d.get("name") or "")
        vdir=_b.verify_coll_dir(self.config, slug)
        if not vdir.is_dir():
            self._wrap_box(QMessageBox.Information,"暂无校验","校验目录不存在，请先送校验。")
            return
        reports=sorted(vdir.glob("*_verify_report.txt"))
        if not reports:
            self._wrap_box(QMessageBox.Information,"暂无校验","暂无校验报告，请等独立窗跑完。")
            return
        base=_b.xml_books_dir(self.config)
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        SFX="_verify_report.txt"
        ok_list, fail_list, undet_list, skip_list=[], [], [], []
        dlg, update, pstate=self._make_progress("导入校验通过项", max(1,len(reports)))
        cancelled=False
        done=0
        for rp in reports:
            stem=rp.name[:-len(SFX)] if rp.name.endswith(SFX) else ""
            hit=next((w for w in works if stem==w or (stem and stem.startswith(w+" "))), None)
            done_label=f"{stem or rp.name}"
            if hit is None:
                skip_list.append(done_label)
            else:
                verdict=_b.verify_report_pass(rp)
                if verdict is True:
                    copied=[]
                    for fmt in ("pdf","epub"):
                        src=vdir/f"{stem}.{fmt}"
                        if src.is_file():
                            try:
                                (base/fmt).mkdir(parents=True, exist_ok=True)
                                shutil.copy2(src, base/fmt/f"{hit}.{fmt}")
                                copied.append(fmt)
                            except Exception as e:
                                fail_list.append(f"{hit} 拷贝失败: {e}")
                    if copied:
                        ok_list.append(f"{hit}（{'/'.join(copied)}）")
                    else:
                        fail_list.append(f"{hit} 缺产物")
                elif verdict is False:
                    fail_list.append(f"{hit} 校验未通过")
                else:
                    undet_list.append(f"{hit} 未判定")
            done+=1
            if not update(done, done_label):
                cancelled=True
                break
        try:
            dlg.close()
        except Exception:
            pass
        if cancelled:
            self.detail.setText("已取消导入")
            return
        self._load_coll_works()
        parts=[f"入库 {len(ok_list)} 部"]
        if fail_list:
            parts.append(f"未通过/失败 {len(fail_list)}")
        if undet_list:
            parts.append(f"未判定 {len(undet_list)}（需人工看报告）")
        if skip_list:
            parts.append(f"跳过 {len(skip_list)}（不在丛书中）")
        msg="，".join(parts)+f"\n校验目录：{vdir}"
        if fail_list:
            msg+="\n未通过:\n"+"\n".join(fail_list[:5])
        if undet_list:
            msg+="\n未判定:\n"+"\n".join(undet_list[:5])
        self._wrap_box(QMessageBox.Information,"导入完成",msg)

    def _open_settings(self):
        from cbeta_publish.gui.settings_dialog import SettingsDialog
        dlg=SettingsDialog(self.config, self)
        dlg.exec()
        new_cfg=dlg.result_config()
        if new_cfg is not None:
            saved=bool(getattr(dlg, "_did_save", False))
            self.config=new_cfg
            self._wvol_cache=None
            apply_ui_fonts(new_cfg.get("ui", {}))
            self._apply_layout()
            # 目录过滤等即时刷新当前视图
            self._on_nav_changed(self.nav_combo.currentText())
            # 设置可能改了来源/预设目录/默认预设：刷新右栏
            self._sync_source_preset_ui()
            self._refresh_dir_labels()
            if saved:
                self.detail.setText("设置已保存（界面字体即时生效；封面字体下次合并生效）")
            else:
                self.detail.setText("设置已应用（未写盘，仅本次运行生效）")

    def _refresh_dir_labels(self):
        """设置变更后刷新右栏「E书目录」三处短名/提示（路径经 getter 动态取）。"""
        for _lb in (getattr(self,"lbl_cache_dir",None), getattr(self,"lbl_xml_dir",None),
                    getattr(self,"lbl_out_dir",None)):
            r=getattr(_lb,"refresh",None)
            if callable(r):
                try:
                    r()
                except Exception:
                    pass

    def _cover_config(self):
        # 直接使用内存配置，避免 CWD 相对读取
        return self.config.get("cover", {})

    # ---------- 按册分册 ----------
    def _by_volume(self):
        return bool((self.config.get("merge", {}) or {}).get("by_volume", False))

    def _safe_name(self, label, fallback="未分册"):
        import re as _re
        s=_re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (label or "").strip())
        s=_re.sub(r"\s+", " ", s).strip(" ._")
        return s or fallback

    def _work_vol_map(self):
        # 作品 → {"edition","seq","label"}（由 mulu/vol.json 派生，缓存；拖拽记录优先作人工覆盖）
        if getattr(self, "_wvol_cache", None) is None:
            try:
                from cbeta_publish.catalog.vol_service import work_file_map
                path=Path(self.config.get("mulu_dir","mulu"))/"vol.json"
                self._wvol_cache=work_file_map(path)
            except Exception as e:
                print("work_file_map fail", e)
                self._wvol_cache={}
        return self._wvol_cache

    def _group_works(self, d, ok, ok_titles, ok_works):
        """按册分组，返回 [ {label, stem, ok, titles, works, sortkey}, ... ]。

        标签来源：丛书 work_groups（拖拽/编辑记录）优先，其次 mulu/vol.json 的册；
        刊本直属经取书名；未知则「未分册」。文件名 stem = `刊本名 序号 显示名`
        （序号按刊本内原书顺序；手动标签同样按其成员的册归属补刊本名+序号）。
        不开启「按册分册」时返回单组（label/stem 为 None）。
        """
        if not self._by_volume():
            return [{"label": None, "stem": None, "ok": ok, "titles": ok_titles,
                     "works": ok_works, "sortkey": (9, "")}]
        manual=d.get("work_groups") or {}
        auto=self._work_vol_map()
        buckets={}   # key -> dict
        for f, t, w in zip(ok, ok_titles, ok_works):
            nw=self._normalize_work(w)
            info=auto.get(w) or auto.get(nw)
            mlab=manual.get(w) or manual.get(nw)
            if info:
                ed=info.get("edition") or ""
                auto_lab=info.get("label") or "未分册"
                # 手动标签若与刊本名相同，视为拖拽回退值而非有效覆盖，用自动册名/书名
                lab=(mlab if (mlab and mlab != ed) else None) or auto_lab
                seq=int(info.get("seq") or 0)
                stem=(f"{ed} {seq:02d} {lab}".strip() if ed else lab)
                key=("a", ed, seq, lab)
                g=buckets.setdefault(key, {"label": lab, "stem": stem,
                                           "edition": ed, "seq": seq,
                                           "ok": [], "titles": [], "works": [],
                                           "sortkey": (1, ed, seq, lab)})
            elif mlab:
                key=("m", mlab)
                g=buckets.setdefault(key, {"label": mlab, "stem": mlab,
                                           "edition": "", "seq": 0,
                                           "ok": [], "titles": [], "works": [],
                                           "sortkey": (0, "", 0, mlab)})
            else:
                key=("z", "未分册")
                g=buckets.setdefault(key, {"label": "未分册", "stem": "未分册",
                                           "edition": "", "seq": 0,
                                           "ok": [], "titles": [], "works": [],
                                           "sortkey": (8, "未分册")})
            g["ok"].append(f); g["titles"].append(t); g["works"].append(w)
        return sorted(buckets.values(), key=lambda g: g["sortkey"])

    def _intro_for(self, ok_works, cover_cfg, made_by_xml=False):
        intro=None
        intro_cfg=(cover_cfg.get("intro",{}) or {})
        if ok_works and cover_cfg.get("enabled", True) and intro_cfg.get("enabled", True):
            try:
                from cbeta_publish.catalog import bulei_index
                intro=bulei_index.summarize(ok_works, self._bulei_roots, title_of=self.sutra.title_of)
                if intro_cfg.get("title"):
                    intro["title"]=intro_cfg["title"]
                if not intro_cfg.get("list", True):
                    intro["sections"]=[]
                if made_by_xml:
                    # 自制来源整页一句注明（官方不加）
                    intro.setdefault("summary", []).append("电子书由程序根据官方XML制作。")
            except Exception as e:
                print("intro build fail", e)
                intro=None
        return intro

    def _make_progress(self, title, total):
        # 合成/ZIP/导出共用：可滚动日志 + 进度条 + 取消；
        # update(done,label,is_html=False) 返回 False 表示用户已取消。
        # 日志逐条追加（保留全部，可上下滚动查看）；总结行可用 HTML，文件链接为蓝色可点击。
        total=max(1, int(total))
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QProgressBar, QPushButton
        from PySide6.QtGui import QTextCursor, QTextCharFormat
        import html as _htm
        dlg=QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumSize(460, 300)     # 窄一些（下载/合并进度窗）
        dlg.resize(520, 360)
        lay=QVBoxLayout(dlg)
        log=QTextBrowser(dlg)
        log.setReadOnly(True)
        log.setLineWrapMode(QTextBrowser.NoWrap)
        log.document().setMaximumBlockCount(5000)
        # file:// 链接必须自己处理：QTextBrowser 会把 file:// 当内部文档加载
        # （报 No document 且打不开），关掉自动跟随，走系统默认程序打开。
        log.setOpenLinks(False)
        log.anchorClicked.connect(self._open_link)
        lay.addWidget(log, 1)
        bar=QProgressBar(dlg)
        bar.setRange(0, total)
        bar.setValue(0)
        lay.addWidget(bar)
        btn=QPushButton("取消", dlg)
        lay.addWidget(btn)
        st={"cancel": False, "lines": [], "oncancel": None, "autoclose_ms": 0}
        def _cancel():
            st["cancel"]=True
            btn.setEnabled(False)
            btn.setText("取消中…")
            cb=st.get("oncancel")
            if cb is not None:
                try:
                    cb()
                except Exception as e:
                    print("cancel hook fail", e)
        btn.clicked.connect(_cancel)
        dlg.rejected.connect(_cancel)
        dlg.show()
        def _put(text, is_html):
            # 统一走 insertHtml：纯文本先转义；每次显式复位字符格式，
            # 否则链接的蓝/下划线/锚点格式会泄漏给后续行（源文件名变蓝即此因）。
            # 以 REPLACE_LAST 开头 => 替换上一行（合并「下载 X ...」与「完成 X」）。
            from cbeta_publish.books.download_worker import REPLACE_LAST
            text=str(text)
            replace=text.startswith(REPLACE_LAST)
            if replace:
                text=text[len(REPLACE_LAST):]
            sb=log.verticalScrollBar()
            at_bottom=sb.value() >= sb.maximum()-8
            pos=sb.value()
            content=text if is_html else _htm.escape(text)
            if replace and _log_replace_last(log, content):
                if at_bottom:
                    log.moveCursor(QTextCursor.End)
                else:
                    sb.setValue(min(pos, sb.maximum()))
                return
            log.moveCursor(QTextCursor.End)
            c=log.textCursor()
            c.setCharFormat(QTextCharFormat())
            c.insertBlock()
            log.setTextCursor(c)
            log.insertHtml(content)
            c2=log.textCursor()
            c2.setCharFormat(QTextCharFormat())
            log.setTextCursor(c2)
            if at_bottom:
                log.moveCursor(QTextCursor.End)
            else:
                # 用户正在往上翻：不抢滚动条
                sb.setValue(min(pos, sb.maximum()))
        def update(done, label="", is_html=False):
            bar.setValue(max(0, min(int(done), bar.maximum())))
            if label:
                st["lines"].append(str(label))
                _put(label, is_html)
            QApplication.processEvents()
            return not st["cancel"]
        def finish(lines=None):
            # 收尾：进度拉满，写入总结行（HTML，文件链接蓝色可点击），“取消”变“关闭”，
            # 窗口保留由用户手动关闭；st["autoclose_ms"]>0 时（下载无错）到点自动关闭。
            # （offscreen/自动化环境直接关闭，避免阻塞。）
            for ln in (lines or []):
                st["lines"].append(str(ln))
                _put(ln, True)
            bar.setValue(bar.maximum())
            try:
                btn.clicked.disconnect()
            except Exception:
                pass
            try:
                dlg.rejected.disconnect()
            except Exception:
                pass
            btn.setEnabled(True)
            btn.setText("关闭")
            btn.clicked.connect(dlg.accept)
            if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
                dlg.close()
                return
            ms=int(st.get("autoclose_ms") or 0)
            if ms > 0:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(ms, dlg.accept)   # 到点自动关闭 → exec 返回后继续后续步骤
            sb=log.verticalScrollBar()
            sb.setValue(sb.maximum())
            dlg.exec()
        st["finish"]=finish
        return dlg, update, st

    def _confirm_regen(self, works, fmts, xml_out):
        """「全部重新生成」确认：已有 N 部自制书会被重跑（较耗时）。返回是否继续。"""
        from cbeta_publish.books import xml2pdf_bridge
        n=0
        for fmt in fmts:
            for w in works:
                if xml2pdf_bridge.find_built(w, fmt, xml_out) is not None:
                    n+=1
        if n<=0:
            return True
        ret=QMessageBox.question(
            self, "全部重新生成",
            f"「生成」选了「全部」：已有 {n} 部自制电子书会被重新生成（需要重跑 xml2pdf，较耗时）。\n继续？",
            QMessageBox.Yes | QMessageBox.No)
        return ret==QMessageBox.Yes

    def _ensure_xml_batch(self, works, fmts, title="生成（自制）",
                          regen_all=None, confirm=True):
        """确保 works×fmts 的自制书存在。

        regen_all=None 时按右栏「生成」策略；True/False 为显式指定（「重制」/「自制」按钮）。
        confirm=True 且需要全部重生成时，先确认一次。
        返回 (ok_map, failed, cancelled)：ok_map = {fmt: {work: Path}}。
        """
        from cbeta_publish.books import xml2pdf_bridge
        xml_out=xml2pdf_bridge.xml_books_dir(self.config)
        try:
            xml_out.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        preset=self._run_preset()
        # 「调整…」临时预设（本次有效）：已有产物是旧预设生成的，必须重新生成才算生效
        if getattr(self, "_tmp_preset", None) is not None:
            regen_all=True
            confirm=False
        if regen_all is None:
            regen_all=(self._run_regen()=="all")
        ok_map={f: {} for f in fmts}
        failed=[]
        if regen_all and confirm and not self._confirm_regen(works, fmts, xml_out):
            return ok_map, failed, True
        total=max(1, len(works)*len(fmts))
        done=[0]
        dlg, update, pstate = self._make_progress(title, total)
        if fmts:
            _ptag="（本次临时）" if getattr(self, "_tmp_preset", None) is not None else ""
            update(0, f"来源：自制｜生成：{'全部重新生成' if regen_all else '仅生成缺少'}"
                      f"｜预设：{(Path(preset).name if preset else '出厂默认')}{_ptag}")
        cancelled=False
        for fmt in fmts:
            for w in works:
                out, reused = xml2pdf_bridge.ensure_one(
                    w, fmt, xml_out, self.config, preset=preset, regen_all=regen_all)
                done[0]+=1
                if out is not None and out.exists():
                    ok_map[fmt][w]=out
                else:
                    failed.append(f"{w}.{fmt} XML转换失败")
                if not update(done[0], f"[{fmt}] {'复用' if reused else '生成'} "
                                          f"{(out.name if out is not None else f'{w}.{fmt}')}"):
                    cancelled=True
                    break
            if cancelled:
                break
        pstate["finish"]([f"完成 {sum(len(v) for v in ok_map.values())}/{total}"
                          + (f"，失败 {len(failed)}" if failed else "")])
        return ok_map, failed, cancelled

    def _merge(self):
        fmts=self._checked_fmts()
        if not fmts:
            QMessageBox.warning(self,"失败","请至少选择一种格式 pdf/epub")
            return
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            QMessageBox.warning(self,"失败","请选择一个丛书再合成")
            return
        p=Path(data)
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(p)
            except Exception as e:
                QMessageBox.warning(self,"失败", f"读取丛书失败 {e}")
                return
        works=d.get("work_ids",[])
        if not works:
            QMessageBox.warning(self,"失败","丛书为空")
            return
        if self._is_blank_name(d.get("name","")):
            # 空白临时名：合并前先命名保存；取消则中止合并
            if not self._save_one_collection(str(data)):
                self.detail.setText("已取消合成（空白丛书需先命名保存）")
                return
            data=self.coll_combo.currentData()
            d=self._coll_dict(data)
            if d is None:
                self.detail.setText("已取消合成（丛书读取失败）")
                return
            works=d.get("work_ids",[])
            if not works:
                QMessageBox.warning(self,"失败","丛书为空")
                return
        from cbeta_publish.books.ebook_merger import merge_pdfs, merge_epubs, MergeCancelled
        from cbeta_publish.books import xml2pdf_bridge
        from cbeta_publish.books import official_ebook_source
        dest_dir=official_ebook_source.official_books_dir(self.config)
        # 本次来源：右栏单选（整批统一；丛书不绑定来源）
        run_source=self._run_source()
        run_preset=self._run_preset() if run_source=="xml" else None
        xml_out=xml2pdf_bridge.xml_books_dir(self.config)
        try:
            xml_out.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        def _src(w):
            return run_source
        def _official_dest(fmt, w):
            return official_ebook_source.dest_path(w, fmt, dest_dir)
        # 官方源缺书检查（xml 源不走此提示）
        missing=[]
        for fmt in fmts:
            for w in works:
                if _src(w)!="official":
                    continue
                if not _official_dest(fmt, w).exists():
                    missing.append(f"{w}.{fmt}")
        if missing:
            _pre=", ".join(missing[:3]) + ("..." if len(missing)>3 else "")
            ret=QMessageBox.question(self, "下载确认",
                f"有 {len(missing)} 部未下载（{_pre}）。\n是否先下载？（「否」= 跳过未下载继续合并）",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ret==QMessageBox.Cancel:
                return
            if ret==QMessageBox.Yes:
                pairs=[(w, fmt) for fmt in fmts for w in works
                       if _src(w)=="official" and not _official_dest(fmt, w).exists()]
                self._download_missing(pairs, dest_dir, title="下载（合并前）", autoclose_ok=True)
                missing=[f"{w}.{fmt}" for fmt in fmts for w in works
                         if _src(w)=="official" and not _official_dest(fmt, w).exists()]
        skip_missing = (ret == QMessageBox.No) if missing else False
        # 自制：全部重新生成前确认（会重跑 xml2pdf，较耗时）
        regen_all = (run_source=="xml" and self._run_regen()=="all")
        if getattr(self, "_tmp_preset", None) is not None:
            regen_all = True          # 临时预设：必须重生成才算生效
        if regen_all and getattr(self, "_tmp_preset", None) is None \
                and not self._confirm_regen(works, fmts, xml_out):
            self.detail.setText("已取消合成（未重新生成）")
            return
        self.btn_merge.setEnabled(False)
        success=[]
        skipped=[]
        failed=[]
        cover_cfg=self._cover_config()
        prep_total=max(1, len(works)*len(fmts))
        total_units=prep_total*2
        done_units=0
        cancelled=False
        dlg, update, pstate = self._make_progress("合成", 100)
        def bump(label=""):
            nonlocal done_units
            done_units+=1
            return update(100*done_units/total_units, label)
        for fmt in fmts:
            ok=[]
            ok_titles=[]
            ok_works=[]
            for w in works:
                if _src(w)=="xml":
                    # 只传 work id：XML 源解析归 xml2pdf（本地候选源→官方下载）。
                    # 注意 CBReader 书库是 P5a（按卷切分），不是 xml2pdf 要的
                    # P5（整部经），publish 侧不再自行定位 XML 文件。
                    out, reused = xml2pdf_bridge.ensure_one(
                        w, fmt, xml_out, self.config, preset=run_preset, regen_all=regen_all)
                    if out is not None and out.exists():
                        ok.append(out); ok_titles.append(self.sutra.title_of(w)); ok_works.append(w)
                    else:
                        failed.append(f"{w}.{fmt} XML转换失败")
                    if not bump(f"[{fmt}] {'复用' if reused else '生成'} "
                                f"{(out.name if out is not None else f'{w}.{fmt}')}"):
                        cancelled=True
                        break
                    continue
                dest=_official_dest(fmt, w)
                if dest.exists():
                    ok.append(dest); ok_titles.append(self.sutra.title_of(w)); ok_works.append(w)
                elif skip_missing:
                    skipped.append(f"{w}.{fmt}")
                else:
                    failed.append(f"{w}.{fmt} 未下载")
                if not bump():
                    cancelled=True
                    break
            if cancelled:
                break
            if not ok:
                failed.append(f"{fmt} 无文件")
                continue
            out_dir=self._out_dir()/d["name"]
            out_dir.mkdir(parents=True, exist_ok=True)
            _sp = self.config.get("pdf", {}).get("split_pages", 5000)
            split_pages = 5000 if _sp is None else max(0, int(_sp))
            _si = self.config.get("epub", {}).get("split_items", 500)
            split_items = 500 if _si is None else max(0, int(_si))
            organizer=cover_cfg.get("organizer","")
            groups=self._group_works(d, ok, ok_titles, ok_works)
            import html as _html
            from PySide6.QtCore import QUrl as _QU
            def _flink(path):
                # 产物文件蓝色链接（点击打开）
                return f'<a href="{_QU.fromLocalFile(str(Path(path).resolve())).toString()}">{_html.escape(Path(path).name)}</a>'
            def _dlink(path):
                return f'<a href="{_QU.fromLocalFile(str(Path(path).resolve())).toString()}">{_html.escape(str(path))}</a>'
            merge_base=done_units
            group_offset=0
            try:
                for g in groups:
                    glabel=g["label"]; gok=g["ok"]; gtitles=g["titles"]; gworks=g["works"]; stem=g["stem"]
                    gbase=merge_base+group_offset
                    def gprog(dd, nn, ll, _gbase=gbase, _n=len(gok)):
                        return update(100*(_gbase+_n*(dd/max(1,nn)))/total_units, ll)
                    if glabel is None:
                        cname=d["name"]
                        out=out_dir/f"{d['name']}.{fmt}"
                        update(100*gbase/total_units, f"[{fmt}] 不分册 → {out.name}（{len(gok)} 部）")
                    else:
                        cname=f"{d['name']}｜{glabel}"
                        out=out_dir/f"{self._safe_name(stem)}.{fmt}"
                        update(100*gbase/total_units, f"[{fmt}] 分册「{glabel}」 → {out.name}（{len(gok)} 部）")
                    intro=self._intro_for(gworks, cover_cfg, made_by_xml=(run_source=="xml"))
                    gfiles=[]
                    if fmt=="pdf":
                        parts=merge_pdfs(gok, out, titles=gtitles, collection_name=cname, organizer=organizer, cover_config=cover_cfg, intro=intro, progress=gprog, split_pages=split_pages)
                        gfiles=[str(pt.resolve()) for pt in parts] if parts else [str(out.resolve())]
                    else:
                        parts=merge_epubs(gok, out, collection_name=cname,
                                          organizer=organizer,
                                          titles=gtitles, cover_config=cover_cfg, intro=intro,
                                          progress=gprog,
                                          split_items=split_items)
                        gfiles=[str(pt.resolve()) for pt in parts]
                    for s in gfiles:
                        success.append(s)
                    _gdone=100*(gbase+len(gok))/total_units
                    for s in gfiles:
                        update(_gdone, f"  → 已生成 {_flink(s)}", True)
                    group_offset+=len(gok)
            except MergeCancelled:
                cancelled=True
                break
            except Exception as e:
                import traceback
                traceback.print_exc()
                failed.append(f"{fmt} 合成失败: {e}")
            done_units=merge_base+len(works)
        self.btn_merge.setEnabled(True)
        if cancelled:
            pstate["finish"](["已取消合成（本次不输出/未完成）。"])
            self._load_coll_works()
            self.detail.setText("已取消合成")
            return
        import datetime
        d["last_publish_at"]=datetime.datetime.utcnow().isoformat()+"Z"
        d["last_publish_dir"]=str(self._out_dir()/d["name"])
        self._commit_publish_meta(str(data), d)
        if success:
            # 各产物文件链接（丛书信息页可点开）；输出目录已在上面「最后发布」行显示
            self._last_publish[str(data)]=[(Path(s).name, s) for s in success]
        _sum=[]
        if success:
            _sum.append(f"合并成功 {len(success)} 个文件：")
            _sum += [f"  {_flink(s)}" for s in success]
            _sum.append(f"输出目录：{_dlink(self._out_dir()/d['name'])}")
        if skipped:
            _sum.append(_html.escape(f"跳过未下载 {len(skipped)}："))
            _sum += [_html.escape(f"  {x}") for x in skipped[:10]]
            if len(skipped)>10:
                _sum.append(_html.escape(f"  …共 {len(skipped)} 项"))
        if failed:
            _sum.append(_html.escape(f"失败 {len(failed)}："))
            _sum += [_html.escape(f"  {x}") for x in failed[:10]]
            if len(failed)>10:
                _sum.append(_html.escape(f"  …共 {len(failed)} 项"))
        if not _sum:
            _sum.append("无输出。")
        pstate["finish"](_sum)
        self._load_coll_works()
        self.tab_bottom.setCurrentIndex(1)   # 合并完成：切到「丛书信息」显示产物与链接
        if success:
            self.detail.setText(f"合并成功 {len(success)} 个文件 → {self._out_dir()/d['name']}"
                                + (f"（跳过 {len(skipped)}）" if skipped else "")
                                + (f"（失败 {len(failed)}）" if failed else ""))
            self._prompt_save_collection("合并完成，", str(data))
        else:
            QMessageBox.warning(self,"失败", "合并失败:\n" + "\n".join(failed))

    def _pack_avail_fmts(self):
        """打包（ZIP/导出）可选格式：官方源 7 种，自制源仅 pdf/epub。"""
        from cbeta_publish.books import official_ebook_source
        if self._run_source() == "xml":
            return ["pdf", "epub"]
        return list(official_ebook_source.PACK_FORMATS)

    def _choose_pack_fmts(self):
        """ZIP/导出格式多选（独立于合并格式勾选；预选=当前勾选交集）。
        返回 [fmt]（空即全不选）；取消返回 None。"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox
        avail = self._pack_avail_fmts()
        pre = set(self._checked_fmts())
        labels = {"txt": "txt（不含校注）", "txt_notes": "txt_notes（含校注）"}
        dlg = QDialog(self)
        dlg.setWindowTitle("选择打包格式")
        lay = QVBoxLayout(dlg)
        boxes = []
        for f in avail:
            b = QCheckBox(labels.get(f, f))
            b.setChecked(f in pre)
            lay.addWidget(b)
            boxes.append((f, b))
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return None
        return [f for f, b in boxes if b.isChecked()]

    def _zip(self):
        fmts = self._choose_pack_fmts()
        if fmts is None:
            return
        if not fmts:
            QMessageBox.warning(self, "失败", "请选择格式")
            return
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            QMessageBox.warning(self,"失败","请选择丛书")
            return
        p=Path(data)
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(p)
            except Exception as e:
                QMessageBox.warning(self,"失败", f"读取丛书失败 {e}")
                return
        works=d.get("work_ids",[])
        if not works:
            QMessageBox.warning(self,"失败","丛书为空")
            return
        import zipfile
        from cbeta_publish.books import official_ebook_source
        dest_dir=official_ebook_source.official_books_dir(self.config)
        # 按来源准备素材：官方=缺则下载；自制=缺则生成（改过预设可选全部重生成）
        if self._run_source()=="xml":
            ok_map, gen_failed, gen_cancelled = self._ensure_xml_batch(works, fmts, title="生成（ZIP 前）")
            if gen_cancelled:
                self._wrap_box(QMessageBox.Warning, "已取消", "已取消生成，未打包。")
                return
            if gen_failed:
                self._wrap_box(QMessageBox.Warning, "未全部生成",
                               "有 %d 部生成失败，已取消打包：\n%s" % (len(gen_failed), "\n".join(gen_failed[:5])))
                return
            src_map = {fmt: dict(ok_map.get(fmt) or {}) for fmt in fmts}
        else:
            missing=[]
            for fmt in fmts:
                for w in works:
                    dest=official_ebook_source.local_path(w, fmt, dest_dir)
                    if not dest.exists():
                        missing.append(f"{w}.{fmt}")
            if missing:
                _pre=", ".join(missing[:3]) + ("..." if len(missing)>3 else "")
                ret=QMessageBox.question(self, "下载确认",
                    f"有 {len(missing)} 部未下载（{_pre}）。\n是否先下载？",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if ret!=QMessageBox.Yes:
                    self._wrap_box(QMessageBox.Warning, "未全部下载", f"有 {len(missing)} 部未下载，请先下载后再打包。")
                    return
                pairs=[(w, fmt) for fmt in fmts for w in works
                       if not official_ebook_source.local_path(w, fmt, dest_dir).exists()]
                self._download_missing(pairs, dest_dir, title="下载（ZIP 前）", autoclose_ok=True)
                missing=[f"{w}.{fmt}" for fmt in fmts for w in works
                         if not official_ebook_source.local_path(w, fmt, dest_dir).exists()]
                if missing:
                    self._wrap_box(QMessageBox.Warning, "未全部下载", f"仍有 {len(missing)} 部未下载，已取消打包。")
                    return
            src_map = {fmt: {w: official_ebook_source.local_path(w, fmt, dest_dir) for w in works}
                       for fmt in fmts}
        from PySide6.QtWidgets import QFileDialog
        sel=QFileDialog.getExistingDirectory(self, "选择ZIP输出目录", str(self._out_dir()))
        if not sel:
            return
        out_dir=Path(sel)
        if not out_dir.exists():
            return
        success=[]
        failed=[]
        cancelled=False
        total=max(1, len(works)*len(fmts)*2)   # 收集文件 + 写入压缩 各占一半
        done=0
        dlg, update, pstate = self._make_progress("ZIP 打包", total)
        for fmt in fmts:
            files=[]
            for w in works:
                f=src_map.get(fmt, {}).get(w)
                if f is not None and Path(f).exists():
                    files.append(Path(f))
                else:
                    failed.append(f"{w}.{fmt} 缺失")
                done+=1
                if not update(done, f"[{fmt}] {w}"):
                    cancelled=True
                    break
            if cancelled:
                break
            if not files:
                failed.append(f"{fmt} 无文件")
                continue
            zpath=out_dir/f"{d['name']}_{fmt}.zip"
            try:
                with zipfile.ZipFile(zpath,"w", zipfile.ZIP_DEFLATED) as z:
                    for i,f in enumerate(files):
                        if f.is_dir():
                            # 目录型（html/docx/odt/txt/txt_notes 解压后）：walk 按 部/相对路径 写入
                            for sub in sorted(p for p in f.rglob("*") if p.is_file()):
                                z.write(sub, arcname=f"{f.name}/{sub.relative_to(f).as_posix()}")
                        else:
                            z.write(f, arcname=f.name)
                        done+=1
                        if not update(done, f"[{fmt}] 压缩 {f.name}"):
                            cancelled=True
                            break
                if cancelled:
                    try:
                        zpath.unlink(missing_ok=True)
                    except Exception:
                        pass
                    break
                success.append(str(zpath.resolve()))
            except Exception as e:
                failed.append(f"{fmt} ZIP 失败: {e}")
        try:
            dlg.close()
        except Exception:
            pass
        if cancelled:
            self.detail.setText("已取消 ZIP")
            QMessageBox.information(self, "已取消", "已取消 ZIP 打包。")
            return
        import datetime
        d["last_publish_at"]=datetime.datetime.utcnow().isoformat()+"Z"
        d["last_publish_dir"]=str(out_dir)
        self._commit_publish_meta(str(data), d)
        if success:
            self._last_publish[str(data)]=[(Path(s).name, s) for s in success]
        self._load_coll_works()
        if success:
            self.tab_bottom.setCurrentIndex(1)   # ZIP完成，切到丛书信息页显示发布结果
            succ_txt="\n".join(success[:3]) + (f"\n... 共 {len(success)} 个文件" if len(success)>3 else "")
            fail_txt=("\n失败:\n" + "\n".join(failed[:5]) + (f"\n... 共 {len(failed)} 项失败" if len(failed)>5 else "")) if failed else ""
            self._wrap_box(QMessageBox.Information, "成功", "ZIP 成功:\n" + succ_txt + fail_txt)
            self._prompt_save_collection("ZIP完成，", str(data))
        else:
            self._wrap_box(QMessageBox.Warning, "失败", "ZIP 失败:\n" + "\n".join(failed[:5]) + (f"\n... 共 {len(failed)} 项" if len(failed)>5 else ""))

    def _wrap_box(self, icon, title, text, buttons=QMessageBox.Ok):
        # 折行无效（QMessageBox 宽度由最长行主导），回退为普通弹窗；文本在调用处已截断
        return QMessageBox(icon, title, text, buttons, self).exec()

    def _export(self):
        fmts = self._choose_pack_fmts()
        if fmts is None:
            return
        if not fmts:
            QMessageBox.warning(self, "失败", "请选择格式")
            return
        data=self.coll_combo.currentData()
        if self._is_coll_placeholder(data):
            QMessageBox.warning(self,"失败","请选择丛书")
            return
        p=Path(data)
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(p)
            except Exception as e:
                QMessageBox.warning(self,"失败", f"读取丛书失败 {e}")
                return
        works=d.get("work_ids",[])
        if not works:
            QMessageBox.warning(self,"失败","丛书为空")
            return
        import shutil
        from cbeta_publish.books import official_ebook_source
        dest_dir=official_ebook_source.official_books_dir(self.config)
        # 按来源准备素材：官方=缺则下载；自制=缺则生成（改过预设可选全部重生成）
        if self._run_source()=="xml":
            ok_map, gen_failed, gen_cancelled = self._ensure_xml_batch(works, fmts, title="生成（导出前）")
            if gen_cancelled:
                self._wrap_box(QMessageBox.Warning, "已取消", "已取消生成，未导出。")
                return
            if gen_failed:
                self._wrap_box(QMessageBox.Warning, "未全部生成",
                               "有 %d 部生成失败，已取消导出：\n%s" % (len(gen_failed), "\n".join(gen_failed[:5])))
                return
            src_map = {fmt: dict(ok_map.get(fmt) or {}) for fmt in fmts}
        else:
            missing=[]
            for fmt in fmts:
                for w in works:
                    dest=official_ebook_source.local_path(w, fmt, dest_dir)
                    if not dest.exists():
                        missing.append(f"{w}.{fmt}")
            if missing:
                _pre=", ".join(missing[:3]) + ("..." if len(missing)>3 else "")
                ret=QMessageBox.question(self, "下载确认",
                    f"有 {len(missing)} 部未下载（{_pre}）。\n是否先下载？",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
                if ret!=QMessageBox.Yes:
                    self._wrap_box(QMessageBox.Warning, "未全部下载", f"有 {len(missing)} 部未下载，请先下载后再导出。")
                    return
                pairs=[(w, fmt) for fmt in fmts for w in works
                       if not official_ebook_source.local_path(w, fmt, dest_dir).exists()]
                self._download_missing(pairs, dest_dir, title="下载（导出前）", autoclose_ok=True)
                missing=[f"{w}.{fmt}" for fmt in fmts for w in works
                         if not official_ebook_source.local_path(w, fmt, dest_dir).exists()]
                if missing:
                    self._wrap_box(QMessageBox.Warning, "未全部下载", f"仍有 {len(missing)} 部未下载，已取消导出。")
                    return
            src_map = {fmt: {w: official_ebook_source.local_path(w, fmt, dest_dir) for w in works}
                       for fmt in fmts}
        from PySide6.QtWidgets import QFileDialog
        target=QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not target:
            return
        success=[]
        failed=[]
        cancelled=False
        total=max(1, len(works)*len(fmts))
        done=0
        dlg, update, pstate = self._make_progress("导出", total)
        for fmt in fmts:
            for w in works:
                src=src_map.get(fmt, {}).get(w)
                src=Path(src) if src is not None else None
                if src is not None and src.exists():
                    try:
                        if src.is_dir():
                            dest = Path(target)/src.name
                            shutil.copytree(src, dest, dirs_exist_ok=True)
                            success.append(str(dest))
                        else:
                            shutil.copy(src, Path(target)/src.name)
                            success.append(str(Path(target)/src.name))
                    except Exception as e:
                        failed.append(f"{w}.{fmt} 拷贝失败: {e}")
                else:
                    failed.append(f"{w}.{fmt} 缺失")
                done+=1
                if not update(done, f"[{fmt}] {w}"):
                    cancelled=True
                    break
            if cancelled:
                break
        try:
            dlg.close()
        except Exception:
            pass
        if cancelled:
            self.detail.setText("已取消导出")
            QMessageBox.information(self, "已取消", "已取消导出。")
            return
        import datetime
        d["last_publish_at"]=datetime.datetime.utcnow().isoformat()+"Z"
        d["last_publish_dir"]=target
        self._commit_publish_meta(str(data), d)
        if success:
            self._last_publish[str(data)]=[("导出目录", target)]
        self._load_coll_works()
        if success:
            self.tab_bottom.setCurrentIndex(1)   # 导出完成，切到丛书信息页显示发布结果
            self._wrap_box(QMessageBox.Information, "成功", f"导出成功 {len(success)} 文件到:\n{target}\n" + "\n".join(success[:3]) + ("\n..." if len(success)>3 else "") + ("\n失败:\n" + "\n".join(failed[:5]) + (f"\n... 共 {len(failed)} 项失败" if len(failed)>5 else "") if failed else ""))
            self._prompt_save_collection("导出完成，", str(data))
        else:
            self._wrap_box(QMessageBox.Warning, "失败", "导出失败:\n" + "\n".join(failed[:5]) + (f"\n... 共 {len(failed)} 项" if len(failed)>5 else ""))