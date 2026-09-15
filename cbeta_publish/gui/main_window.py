# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem, QSplitter, QSplitterHandle, QLabel, QPushButton, QToolButton, QLineEdit, QComboBox, QInputDialog, QMessageBox, QApplication, QTabWidget, QTextBrowser, QSizePolicy, QProgressDialog, QScrollArea
from PySide6.QtCore import Qt, QEvent, QTimer
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
    def __init__(self, orientation, parent, panel_index=0):
        super().__init__(orientation, parent)
        self._saved = None
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
        # 动态判定本分隔条左侧的那一栏
        sp = self.splitter()
        c = self.geometry().center()
        idx = 0
        for i in range(sp.count()):
            g = sp.widget(i).geometry()
            if (g.center().x() if sp.orientation() == Qt.Horizontal else g.center().y()) < \
               (c.x() if sp.orientation() == Qt.Horizontal else c.y()):
                idx = i
        return idx

    def _collapse(self):
        sp = self.splitter()
        k = self._left_index()
        sizes = sp.sizes()
        if sizes[k] > 0:
            # 存整组宽度，恢复时原样写回（保证各栏回到收起前的位置）
            self._saved = list(sizes)
        sizes[k] = 0
        sp.setSizes(sizes)

    def _restore(self):
        sp = self.splitter()
        k = self._left_index()
        sizes = sp.sizes()
        if sizes[k] > 0:
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
    if app is not None:
        app.setFont(QFont(str(ui.get("app_font") or "Microsoft YaHei"), font_size))


class MainWindow(QMainWindow):
    def __init__(self, config):
        super().__init__()
        self.config=config
        self._config_path=config.get("_config_path") or CONFIG_PATH
        self.setWindowTitle("CBETA 发布管理器")
        self.resize(1240,720)
        mulu=Path(config["mulu_dir"])
        try:
            self.sutra = SutraService(mulu/"SutraList.json")
            self.mapping = MappingService(mulu/"sutra_mapping.txt")
            self.creator = CreatorService(mulu/"all-creators-with-alias.json", mulu/"creators-by-strokes-with-works.json")
        except Exception as e:
            print("service load fail", e)
        self._bulei_roots=[]
        self._current_works=[]
        self._base_works=[]
        self._selected=set()
        self._collections=[]
        self._coll_changed=False
        self._coll_originals={}
        self._changed_colls=set()
        self._last_coll_path=(config.get("ui",{}) or {}).get("last_collection") or None
        self._last_publish={}
        self._work_groups={}   # {work_id: 册标签}（从刊本树拖入时记录，供「按册分册」）

        splitter=_Splitter(Qt.Horizontal)
        left=QWidget()
        lv=QVBoxLayout(left)
        self.nav_combo=QComboBox()
        self.nav_combo.addItems(["部类","三藏","刊本","朝代","作者","丛书"])
        lv.addWidget(self.nav_combo)
        self.bulei_filter=QComboBox()
        self.bulei_filter.setEditable(True)
        self.bulei_filter.setPlaceholderText("目录：全部部类（可输入筛选）")
        self.bulei_filter.addItem("目录：全部部类", None)
        lv.addWidget(self.bulei_filter)
        self.coll_filter=QComboBox()
        self.coll_filter.addItem("分类：全部", None)
        lv.addWidget(self.coll_filter)
        self.coll_tag_filter=QComboBox()
        self.coll_tag_filter.addItem("标签：全部", None)
        lv.addWidget(self.coll_tag_filter)
        self.author_sort=QComboBox()
        self.author_sort.addItems(["拼音排序","笔画排序","朝代排序"])
        lv.addWidget(self.author_sort)
        self.author_filter=QComboBox()
        self.author_filter.setEditable(True)
        self.author_filter.setPlaceholderText("笔画：全部")
        lv.addWidget(self.author_filter)
        self.search=QLineEdit()
        self.search.setPlaceholderText("搜索经名/作者/经号（全局）")
        lv.addWidget(self.search)
        self.tree=QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.mimeData = self._tree_mimeData   # 提供 text/plain（默认只有内部模型格式）
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setMinimumWidth(260)
        lv.addWidget(self.tree)
        self.lbl_hint=QLabel("")
        self.lbl_hint.setStyleSheet("color: gray;")
        self.lbl_hint.setWordWrap(True)
        lv.addWidget(self.lbl_hint)
        splitter.addWidget(left)

        mid=QWidget()
        mid.setMinimumWidth(280)
        mv=QVBoxLayout(mid)
        mid_top=QWidget()
        mth=QHBoxLayout(mid_top)
        mth.setContentsMargins(0,0,0,0)
        mth.addWidget(QLabel("书籍列表"))
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
        self.btn_clear_list.setToolTip("清除当前书籍列表")
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
        self.detail=QLabel("详情：选择书籍查看")
        self.detail.setWordWrap(True)
        mv.addWidget(self.detail)
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
        rv.addWidget(fmt_box)
        publish_box=QWidget()
        hb2=QHBoxLayout(publish_box)
        hb2.setContentsMargins(0,0,0,0)
        hb2.addWidget(QLabel("发布:"))
        self.btn_download=QPushButton("下载")
        self.btn_merge=QPushButton("合并")
        self.btn_merge.setToolTip("PDF/ePub合并成一个文件（单一格式，允许分册）")
        self.btn_zip=QPushButton("ZIP")
        self.btn_zip.setToolTip("ZIP 打包")
        self.btn_export=QPushButton("导出")
        self.btn_export.setToolTip("拷贝到指定目录")
        hb2.addWidget(self.btn_merge); hb2.addWidget(self.btn_zip); hb2.addWidget(self.btn_export); hb2.addWidget(self.btn_download)
        hb2.addStretch()
        rv.addWidget(publish_box)
        cache_box=QWidget()
        ch=QHBoxLayout(cache_box)
        ch.setContentsMargins(0,0,0,0)
        ch.addWidget(QLabel("缓存目录"))
        cache_base=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
        def _dir_label(p):
            # 目录短名显示，悬停看全路径，点击打开
            lb=QLabel(Path(p).name or str(p))
            lb.setStyleSheet("color:#0645AD; text-decoration:underline;")
            lb.setCursor(Qt.PointingHandCursor)
            lb.setToolTip(f"{p}\n点击在文件浏览器中打开")
            def _open(e, _p=str(Path(p).resolve())):
                try:
                    from PySide6.QtGui import QDesktopServices
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(_p))
                except Exception as ex:
                    print(ex)
            lb.mousePressEvent=_open
            return lb
        self.lbl_cache_dir=_dir_label(cache_base)
        ch.addWidget(self.lbl_cache_dir)
        ch.addWidget(QLabel("输出目录"))
        self.lbl_out_dir=_dir_label(self._out_dir())
        ch.addWidget(self.lbl_out_dir)
        ch.addStretch()
        rv.addWidget(cache_box)
        self.log_view=QTextBrowser()
        self.log_view.setMaximumHeight(100)
        self.log_view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.tab_bottom=QTabWidget()
        info_page=QWidget()
        info_layout=QVBoxLayout(info_page)
        info_layout.setContentsMargins(0,0,0,0)
        from PySide6.QtWidgets import QScrollArea
        self.info_scroll=QScrollArea()
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setFrameShape(QScrollArea.NoFrame)
        self.info_scroll.setWidget(self.lbl_coll_info)
        info_layout.addWidget(self.info_scroll)
        self.tab_bottom.addTab(info_page, "丛书信息")
        dl_page=QWidget()
        dl_layout=QVBoxLayout(dl_page)
        dl_layout.setContentsMargins(0,0,0,0)
        dl_layout.addWidget(self.log_view)
        self.tab_bottom.addTab(dl_page, "下载记录")
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
        self.author_filter.currentIndexChanged.connect(self._on_author_filter)
        self.coll_filter.currentIndexChanged.connect(self._on_coll_filter)
        self.author_sort.currentTextChanged.connect(self._on_author_sort)
        self.sort_combo.currentTextChanged.connect(self._on_sort_changed)
        self.tree.itemClicked.connect(self._on_tree_preview)
        self.tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self.list.itemChanged.connect(self._on_list_changed)
        self.list.itemClicked.connect(self._on_list_detail)
        self.list.itemDoubleClicked.connect(self._on_list_double_add)
        self.list.keyPressEvent = lambda e: self._list_key_press(e)
        self.list.dragEnterEvent = lambda e: self._list_drag_enter(e)
        self.list.dropEvent = lambda e: self._list_drop(e)
        self.btn_all.clicked.connect(self._select_all)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_clear_list.clicked.connect(self._clear_list)
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
        self.btn_merge.clicked.connect(self._merge)
        self.btn_zip.clicked.connect(self._zip)
        self.btn_export.clicked.connect(self._export)
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
        self.coll_list.dropEvent = lambda e: self._coll_drop(e)
        self.coll_list.viewport().installEventFilter(self)
        self.chk_pdf.stateChanged.connect(self._load_coll_works)
        self.chk_epub.stateChanged.connect(self._load_coll_works)
        self.lbl_coll_info.linkActivated.connect(self._open_publish_link)
        self.tree.dragEnterEvent = lambda e: self._tree_drag_enter(e)
        self.tree.dropEvent = lambda e: self._tree_drop(e)

        self._load_bulei()
        self._load_collections()
        # 有上次工作的丛书则保持选中；否则选中空白丛书
        self._ensure_blank_working(select=not bool(self._last_coll_path))
        # 繁简搜索：启动时生成简体标题缓存
        from cbeta_publish.utils import text_util
        text_util.init()
        self._title_s2={}
        self._bulei_title_s2={}
        try:
            def walk_b(nodes):
                for n in nodes:
                    self._bulei_title_s2[n.title]=text_util.to_simplified(n.title)
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
        # 作者别名索引：正式名 -> 别名列表（用于详情/悬停显示）
        self._author_aliases={}
        try:
            for _aid, _info in self.creator.alias.items():
                self._author_aliases[_info.get("regular_name","")]=_info.get("aliases_all",[])
        except Exception as e:
            print("alias index fail", e)
        self._on_nav_changed(self.nav_combo.currentText())
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
        # 首次显示后重新应用分栏宽度，避免 setSizes 在布局前失效
        try:
            self._splitter.setSizes([400,360,360])
        except Exception:
            pass
        if not getattr(self, "_focused_once", False):
            self._focused_once=True
            try:
                self.search.setFocus()
            except Exception:
                pass

    def _fix_tab_height(self):
        # Tab 高度固定为下载页高度，切页时上面元素不再伸缩
        try:
            bar=self.tab_bottom.tabBar().height() or self.tab_bottom.tabBar().sizeHint().height()
            page=self.tab_bottom.widget(1).sizeHint().height() or 104
            self._tab_full_h=bar+page+4
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
            if cat_json.exists():
                # 官方 scope-selector/category.json（权威，CBETA 部類）
                self._bulei_roots=parse_bulei_json(cat_json)
            else:
                self._bulei_roots=parse_bulei(mulu/"bulei.txt")
            self._refresh_bulei_tree()
        except Exception as e:
            print(e)

    def _refresh_bulei_tree(self, filter_node=None):
        self.tree.clear()
        hidden=set(self._catalog_filter_hidden("tripitaka"))   # 部类/三藏共用隐藏列表
        self.bulei_filter.blockSignals(True)
        cur = self.bulei_filter.currentData()
        self.bulei_filter.clear()
        self.bulei_filter.addItem("全部（全部部类）", None)
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
        self.bulei_filter.blockSignals(False)
        # 可编辑 combo：恢复行编辑显示文本
        if cur is not None:
            for i in range(self.bulei_filter.count()):
                if self.bulei_filter.itemData(i)==cur:
                    self.bulei_filter.setEditText(self.bulei_filter.itemText(i))
                    break
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

    def _refresh_tripitaka_tree(self):
        # 三藏视图：三藏→部類→…→经（复用 bulei 子树，内存重分组）
        from cbeta_publish.catalog.tripitaka_service import group_by_pitaka
        self.tree.clear()
        groups=group_by_pitaka(self._bulei_roots)
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
            hidden=set(self._catalog_filter_hidden("tripitaka"))
            nodes=[n for n in nodes if n.title not in hidden]
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
            # depth=展开层数：0/1 折叠；depth>=2 -> expandToDepth(depth-1)
            if depth<=1:
                self.tree.collapseAll()
            else:
                self.tree.expandToDepth(depth-1)

    def _refresh_vol_tree(self):
        # 刊本视图：刊本（藏经版本）→册→经（部分刊本第二层直接是经）；受 catalog.filters.vol.hidden 过滤
        from cbeta_publish.catalog.vol_service import load_vol, count_works
        self.tree.clear()
        path=Path(self.config["mulu_dir"])/"vol.json"
        hidden=set(self._catalog_filter_hidden("vol"))
        if not path.exists():
            it=QTreeWidgetItem(["（未下载 vol.json，请到 设置→更新源 检查更新）"])
            it.setForeground(0, Qt.gray)
            self.tree.addTopLevelItem(it)
            return
        def _work_item(wid, wtitle):
            l_item=QTreeWidgetItem([wtitle])
            l_item.setData(0, Qt.UserRole, {"key": wid, "title": wtitle})
            return l_item
        for entry in load_vol(path):
            edition=entry["edition"]
            if edition in hidden:
                continue
            vols=entry.get("vols", [])
            e_item=QTreeWidgetItem([f"{edition} ({len(vols)}册/{count_works(entry)}部)"])
            e_item.setData(0, Qt.UserRole, {"vol": edition})
            self.tree.addTopLevelItem(e_item)
            # 直属经（部分刊本无册分组）
            for wid, wtitle in entry.get("works", []):
                e_item.addChild(_work_item(wid, wtitle))
            for vol in vols:
                v_item=QTreeWidgetItem([f"{vol['title']} ({len(vol['works'])}部)"])
                v_item.setData(0, Qt.UserRole, {"vol_title": vol["title"], "edition": edition})
                e_item.addChild(v_item)
                for wid, wtitle in vol["works"]:
                    v_item.addChild(_work_item(wid, wtitle))
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

    def _on_author_filter(self, idx):
        d=self.author_filter.currentData()
        if self.author_sort.currentText() in ("拼音排序","朝代排序"):
            QTimer.singleShot(0, lambda l=d: self._refresh_author_tree(filter_letter=l))
        else:
            QTimer.singleShot(0, lambda s=d: self._refresh_author_tree(filter_stroke=s))

    def _on_coll_filter(self, idx):
        cat=self.coll_filter.currentData()
        QTimer.singleShot(0, lambda c=cat: self._refresh_coll_tree(filter_cat=c))

    def _on_author_sort(self, mode):
        self._refresh_author_tree()

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

    def _refresh_author_tree(self, filter_stroke=None, filter_letter=None):
        self.tree.clear()
        try:
            data=self.creator.strokes
            strokes=[]
            if data and len(data)==1 and len(data[0].get("children",[]))>=20:
                strokes=data[0].get("children",[])
            else:
                strokes=data
            mode=self.author_sort.currentText()
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
                    self.author_filter.addItem(s.get("title",""), s)
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
                s_item=QTreeWidgetItem([stroke.get("title","")])
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
    def _on_nav_changed(self, mode):
        self.tree.clear()
        self.list.clear()
        self.bulei_filter.setVisible(mode=="部类")
        self.author_filter.setVisible(mode=="作者")
        self.author_sort.setVisible(mode=="作者")
        self.coll_filter.setVisible(mode=="丛书")
        self.coll_tag_filter.setVisible(mode=="丛书")
        # 左栏状态栏：操作提示（按模式）
        if mode=="部类":
            self.lbl_hint.setText("提示：拖动或双击单本书加入中栏")
        elif mode=="三藏":
            self.lbl_hint.setText("提示：经/律/论/藏外；拖动或双击单本书加入中栏")
        elif mode=="朝代":
            self.lbl_hint.setText("提示：按朝代浏览；拖动或双击单本书加入中栏")
        elif mode=="刊本":
            self.lbl_hint.setText("提示：依刊本（藏经版本）→ 册 → 经；拖动或双击单本书加入中栏")
        elif mode=="作者":
            self.lbl_hint.setText("提示：拖动或双击作者（其全部作品）加入中栏")
        elif mode=="丛书":
            self.lbl_hint.setText("提示：双击丛书载入中栏；拖入右栏加入丛书")
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

    def _on_tree_preview(self, item, col):
        mode=self.nav_combo.currentText()
        data=item.data(0, Qt.UserRole)
        if not data:
            return
        if mode in ("部类","三藏"):
            if hasattr(data, "title") and not data.children:
                m=re.search(r"[A-Z]+[0-9A-Za-z]+", data.title)
                if m and self._is_work_id(m.group(0)):
                    self.detail.setText(self._book_info_text(m.group(0)))
                    return
            if hasattr(data, "title"):
                self.detail.setText(f"预览: {data.title}")
            elif isinstance(data, dict) and data.get("pitaka"):
                self.detail.setText(f"{data['pitaka']}（拖动或双击单本书加入中栏）")
        elif mode=="作者":
            if isinstance(data, dict) and data.get("title"):
                name=data.get("title","")
                alias=self._author_aliases.get(name, [])
                works=data.get("children",[])
                cnt=len(works)
                info=f"{name} ({cnt}部)"
                if alias:
                    info+=f"\n别名：{', '.join(alias)}"
                if works:
                    info+="\n作品："
                    for wk in works[:10]:
                        t=(wk.get("title","") or "").strip()
                        if len(t)>42:
                            t=t[:42]+"…"
                        info+=f"\n  {t}"
                    if cnt>10:
                        info+=f"\n  …共 {cnt} 部"
                self.detail.setText(info)
            else:
                self.detail.setText(f"预览: {data.get('title','')}")
        elif mode=="丛书":
            self.detail.setText(f"预览: {data.get('name','')} [{self._cat_name(data.get('category',''))}] {len(data.get('work_ids',[]))}部")
        elif mode=="朝代":
            if isinstance(data, dict) and data.get("key"):
                self.detail.setText(self._book_info_text(data["key"]))
            elif isinstance(data, dict) and data.get("dynasty"):
                self.detail.setText(f"{data['dynasty']}（拖动或双击单本书加入中栏）")
        elif mode=="刊本":
            if isinstance(data, dict) and data.get("key"):
                self.detail.setText(self._book_info_text(data["key"]))
            elif isinstance(data, dict) and data.get("vol_title"):
                self.detail.setText(f"{data.get('edition','')}／{data['vol_title']}（拖动或双击单本书加入中栏）")
            elif isinstance(data, dict) and data.get("vol"):
                self.detail.setText(f"刊本：{data['vol']}（拖动或双击单本书加入中栏）")

    def _on_tree_double_click(self, item, col):
        if not item:
            return
        item.setExpanded(not item.isExpanded())
        mode=self.nav_combo.currentText()
        data=item.data(0, Qt.UserRole)
        if not data:
            return
        if mode=="丛书" and isinstance(data, dict) and isinstance(data.get("work_ids"), list):
            # 目录窗口双击丛书：载入其书籍到中栏
            works=[w for w in data.get("work_ids",[]) if self._is_work_id(w)]
            self._show_works(works)
            self.detail.setText(f"已载入丛书「{data.get('name','')}」{len(works)} 部到中栏（可勾选后加入右栏）")
            return
        is_single=False
        work=None
        if mode in ("部类","三藏") and hasattr(data, 'title'):
            if not data.children:
                m=re.search(r"[A-Z]+[0-9A-Za-z]+", data.title)
                if m and self._is_work_id(m.group(0)):
                    is_single=True
                    work=m.group(0)
        elif mode=="朝代" and isinstance(data, dict) and data.get("key"):
            is_single=True
            work=data["key"]
        elif mode=="刊本" and isinstance(data, dict) and data.get("key"):
            is_single=True
            work=data["key"]
        elif mode=="作者" and isinstance(data, dict):
            if data.get("key") and "卷" in data.get("title",""):
                is_single=True
                work=data.get("key").strip()
            elif data.get("children"):
                # 双击作者：把其全部作品加入中栏
                works=[c.get("key","").strip() for c in data.get("children",[]) if c.get("key") and self._is_work_id(c.get("key",""))]
                if works:
                    added=0
                    for wk in works:
                        if wk not in self._current_works:
                            self._current_works.append(wk)
                            added+=1
                        if wk not in self._base_works:
                            self._base_works.append(wk)
                    self._show_works_sorted()
                    self.detail.setText(f"已加入作者 {data.get('title','')} 的 {len(works)} 部作品，新增 {added} 部")
                    return
        if is_single and work:
            newly = work not in self._current_works
            if newly:
                self._current_works.append(work)
                self._show_works_sorted()
            if work not in self._base_works:
                self._base_works.append(work)
            self.detail.setText(f"已加入 {work}，共 {len(self._current_works)} 部" if newly
                                else f"{work} 已在列表中")

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

    def _show_works_sorted(self):
        works=self._current_works[:]
        seen=set()
        uniq=[]
        for w in works:
            nw=self._normalize_work(w)
            if nw not in seen:
                seen.add(nw)
                uniq.append(w)
        mode=self.sort_combo.currentText() if hasattr(self, 'sort_combo') else "原始顺序"
        if mode=="经名排序":
            uniq.sort(key=lambda w: self._display_title(w))
        elif mode=="经号排序":
            def canon_key(w):
                m=re.match(r"([A-Za-z]+)([0-9A-Za-z]+)", w)
                if m:
                    return (m.group(1), m.group(2))
                return (w, "")
            uniq.sort(key=canon_key)
        # "原始顺序"：保持加入/拖动顺序，不再排序
        self._current_works=uniq
        self.list.clear()
        self.list.blockSignals(True)
        for w in uniq:
            m=self.mapping.resolve(w)
            title=self._display_title(w)
            byline=m.get("byline","") if m else ""
            if byline:
                title=f"{title} [{byline}]"
            item=QListWidgetItem(f"{w} {title}")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            item.setFlags(item.flags() | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked if w in self._selected else Qt.Unchecked)
            item.setData(Qt.UserRole, w)
            self.list.addItem(item)
        self.list.blockSignals(False)

    def _on_sort_changed(self, mode):
        self._show_works_sorted()

    def _show_works(self, works):
        # 确立新的列表范围：同时刷新搜索基准，之后搜索都从该基准过滤
        self._base_works=list(works)
        self._current_works=list(works)
        self._show_works_sorted()

    def _refresh_sel_count(self):
        # 中栏标题计数：只跟中栏复选框（_selected），不写 detail
        self.lbl_sel_count.setText(f"已选 {len(self._selected)} 部")

    def _select_all(self):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            it=self.list.item(i)
            it.setCheckState(Qt.Checked)
            self._selected.add(it.data(Qt.UserRole))
        self.list.blockSignals(False)
        self._refresh_sel_count()

    def _clear_all(self):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            it=self.list.item(i)
            it.setCheckState(Qt.Unchecked)
        self.list.blockSignals(False)
        self._selected.clear()
        self._refresh_sel_count()

    def _clear_list(self):
        self._current_works.clear()
        self._base_works.clear()
        self._selected.clear()
        self._work_groups.clear()
        self.list.clear()
        self._refresh_sel_count()
        self.detail.setText("已清空书籍列表")

    def _on_list_changed(self, item):
        w=item.data(Qt.UserRole)
        if item.checkState()==Qt.Checked:
            self._selected.add(w)
        else:
            self._selected.discard(w)
        self._refresh_sel_count()

    def _on_list_detail(self, item):
        if not item:
            return
        self.detail.setText(self._book_info_text(item.data(Qt.UserRole)))

    def _on_list_double_add(self, item):
        if not item:
            return
        w=item.data(Qt.UserRole)
        new_state=Qt.Unchecked if item.checkState()==Qt.Checked else Qt.Checked
        self.list.blockSignals(True)
        item.setCheckState(new_state)
        self.list.blockSignals(False)
        if new_state==Qt.Checked:
            self._selected.add(w)
        else:
            self._selected.discard(w)
        self._refresh_sel_count()

    def _list_key_press(self, e):
        from PySide6.QtCore import Qt as _Qt
        if e.key()==_Qt.Key_Space:
            for it in self.list.selectedItems():
                w=it.data(Qt.UserRole)
                new_state=_Qt.Unchecked if it.checkState()==_Qt.Checked else _Qt.Checked
                self.list.blockSignals(True)
                it.setCheckState(new_state)
                self.list.blockSignals(False)
                if new_state==_Qt.Checked:
                    self._selected.add(w)
                else:
                    self._selected.discard(w)
            self._refresh_sel_count()
            e.accept()
            return
        if e.key() in (_Qt.Key_Delete, _Qt.Key_Backspace):
            sel=[it.data(Qt.UserRole) for it in self.list.selectedItems()]
            if sel:
                for w in sel:
                    self._selected.discard(w)
                    self._current_works=[x for x in self._current_works if x.strip().upper()!=w.strip().upper()]
                    self._base_works=[x for x in self._base_works if x.strip().upper()!=w.strip().upper()]
                self._show_works_sorted()
                self._refresh_sel_count()
                self.detail.setText(f"已移除 {len(sel)} 部")
                e.accept()
                return
        from PySide6.QtWidgets import QListWidget as _L
        _L.keyPressEvent(self.list, e)

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
        # 从目录树选中项提取工作ID（部类/作者节点递归收集）
        works=[]
        for it in self.tree.selectedItems():
            data=it.data(0, Qt.UserRole)
            if data:
                if hasattr(data, 'title'):
                    def collect(n):
                        out=re.findall(r"[A-Z]+[0-9A-Za-z]+", n.title)
                        for ch in n.children:
                            out.extend(collect(ch))
                        return out
                    works.extend(collect(data))
                elif isinstance(data, dict) and data.get("key"):
                    if "卷" in data.get("title",""):
                        works.append(data["key"])
                    else:
                        def ca(node):
                            out=[]
                            for ch in node.get("children",[]):
                                if ch.get("key") and "卷" in ch.get("title",""):
                                    out.append(ch["key"])
                                elif ch.get("children"):
                                    out.extend(ca(ch))
                            return out
                        if data.get("key","").startswith("A"):
                            works.extend([c.get("key") for c in data.get("children",[]) if c.get("key")])
                        else:
                            works.extend(ca(data))
        return works

    def _list_drag_enter(self, e):
        e.acceptProposedAction()

    def _list_drop(self, e):
        # 丛书窗口拖到书籍列表：从当前丛书移除书籍
        if e.source() is self.coll_list:
            works=[]
            for it in self.coll_list.selectedItems():
                w=it.data(Qt.UserRole)
                if w:
                    works.append(w)
            if not works:
                works=re.findall(r"[A-Z]+[0-9A-Za-z]+", e.mimeData().text() or "")
            self._remove_works_from_collection(works)
            self._purge_buffer(works)
            e.acceptProposedAction()
            return
        if e.source() is self.list:
            from PySide6.QtWidgets import QListWidget as _L
            old_order=self._current_works[:]
            _L.dropEvent(self.list, e)
            new_order=[]
            for i in range(self.list.count()):
                w=self.list.item(i).data(Qt.UserRole)
                if w:
                    new_order.append(w)
            if new_order and new_order!=old_order:
                self._current_works=new_order
                self._base_works=list(new_order)
                self.detail.setText("已重新排序")
            e.acceptProposedAction()
            return
        try:
            works, groups=self._mime_works_groups(e.mimeData())
            if not works:
                works=self._tree_selected_works()
            seen=set()
            uniq=[]
            for w in works:
                nw=self._normalize_work(w)
                if nw not in seen and self._is_work_id(w):
                    seen.add(nw); uniq.append(w)
            if uniq:
                added=0
                for w in uniq:
                    if w not in self._work_groups and w in groups:
                        self._work_groups[w]=groups[w]
                    nw=self._normalize_work(w)
                    if nw not in [self._normalize_work(x) for x in self._current_works]:
                        self._current_works.append(w)
                        added+=1
                    if nw not in [self._normalize_work(x) for x in self._base_works]:
                        self._base_works.append(w)
                self._show_works_sorted()
                self.detail.setText(f"拖入 {added} 部，去重后 {len(self._current_works)} 部")
                e.acceptProposedAction()
                return
        except Exception as ex:
            print(ex)
        e.ignore()

    def _tree_drag_enter(self, e):
        e.acceptProposedAction()

    def _tree_drop(self, e):
        # 仅支持：中栏书籍列表拖回移除 _current_works；
        # 丛书窗口 coll_list 不得拖到目录窗口（目标是中栏书籍列表，见 _list_drop）
        if e.source() is self.coll_list:
            e.ignore()
            return
        try:
            txt=e.mimeData().text()
            works=re.findall(r"[A-Z]+[0-9A-Za-z]+", txt)
            if not works:
                for i in range(self.list.count()):
                    it=self.list.item(i)
                    if it.isSelected():
                        w=it.data(Qt.UserRole)
                        if w:
                            works.append(w)
            if not works:
                works=list(self._selected)
            seen=set()
            uniq=[]
            for w in works:
                nw=w.strip().upper()
                if nw not in seen:
                    seen.add(nw); uniq.append(w)
            if uniq:
                removed=0
                for w in uniq:
                    nw=w.strip().upper()
                    before=len(self._current_works)
                    self._current_works=[x for x in self._current_works if x.strip().upper()!=nw]
                    self._base_works=[x for x in self._base_works if x.strip().upper()!=nw]
                    if len(self._current_works)!=before:
                        removed+=1
                    for v in list(self._selected):
                        if v.strip().upper()==nw:
                            self._selected.discard(v)
                self._refresh_sel_count()
                if removed:
                    self._show_works_sorted()
                    self.detail.setText(f"已移除 {removed} 部，剩余 {len(self._current_works)} 部")
                else:
                    self.detail.setText("未找到可移除项")
                e.acceptProposedAction()
                return
        except Exception as ex:
            print(ex)
        e.ignore()

    def _remove_works_from_collection(self, works):
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
        seen=set()
        for w in works:
            nw=w.strip().upper()
            if nw:
                seen.add(nw)
        before=len(d["work_ids"])
        d["work_ids"]=[w for w in d["work_ids"] if self._normalize_work(w) not in seen]
        wg=d.get("work_groups") or {}
        if wg:
            for k in list(wg):
                if self._normalize_work(k) in seen:
                    wg.pop(k, None)
            d["work_groups"]=wg
        if len(d["work_ids"])!=before:
            d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
            self._mark_coll_changed(str(data))
            self._load_coll_works()
            self.detail.setText(f"已移除 {before-len(d['work_ids'])} 部，剩余 {len(d['work_ids'])} 部")

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

    def _on_search(self, kw):
        # 始终从搜索基准过滤；结果只更新显示，不改基准，回车可重复搜
        if not kw:
            self._current_works=list(self._base_works)
            self._show_works_sorted()
            return
        vars_kw_s={text_util.to_simplified(v) for v in self._search_variants(kw)}
        # 作者模式：优先作者搜索（避免被当前列表的其它匹配抢占）
        if self.nav_combo.currentText()=="作者":
            res=self._author_search(kw)
            if res:
                filtered=self._search_author_works(res)
                if filtered:
                    self._current_works=filtered[:200]
                    self._show_works_sorted()
                    return
        def _match(w):
            if kw in w:
                return True
            t_s,m_s=self._title_s2.get(w,("",""))
            for kv in vars_kw_s:
                if kv in t_s or kv in m_s:
                    return True
            t=self.sutra.title_of(w)
            if kw in t:
                return True
            m=(self.mapping.resolve(w) or {}).get("name","")
            return kw in m
        filtered=[w for w in self._base_works if _match(w)]
        if not filtered and self.nav_combo.currentText()=="部类":
            all_works=[]
            def collect_all(nodes):
                for n in nodes:
                    if any(kv in self._bulei_title_s2.get(n.title, n.title) for kv in vars_kw_s):
                        for w in WORK_RE.findall(n.title):
                            if len(w)>=4 and (self.sutra.title_of(w)!=w or self.mapping.work_exists(w)):
                                all_works.append(w)
                    collect_all(n.children)
            collect_all(self._bulei_roots)
            seen=set()
            filtered=[w for w in all_works if not (w in seen or seen.add(w))]
        if not filtered and self.nav_combo.currentText()=="作者":
            res=self._author_search(kw)
            if res:
                filtered=self._search_author_works(res)
        self._current_works=filtered[:200]
        self._show_works_sorted()

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

    def _ordered_selected(self):
        # 勾选的工作ID按中栏显示顺序排列（_selected 是 set，直接遍历会乱序）；
        # 勾选但不在当前列表中的按排序追加，保证确定性
        out=[]
        seen=set()
        in_list=set()
        for i in range(self.list.count()):
            w=self.list.item(i).data(Qt.UserRole)
            in_list.add(w)
            if w in self._selected and w not in seen:
                seen.add(w)
                out.append(w)
        for w in sorted(self._selected - in_list):
            seen.add(w)
            out.append(w)
        return out

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
        added=[]
        wg_touched=False
        for w in self._ordered_selected():
            if w not in d["work_ids"]:
                d["work_ids"].append(w)
                added.append(w)
            if w in self._work_groups:
                g=d.setdefault("work_groups",{})
                if g.get(w)!=self._work_groups[w]:
                    g[w]=self._work_groups[w]; wg_touched=True
        if not added and not wg_touched:
            self.detail.setText("所选均已在丛书中")
            return
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        self._mark_coll_changed(str(data))
        self._load_coll_works()
        self.detail.setText(f"已加入 {len(added)} 部到 {d['name']}，共 {len(d['work_ids'])} 部")

    def _new_collection(self):
        self._create_collection_dialog(self._ordered_selected())

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
        d=self._coll_dict(data)
        if d is None:
            try:
                d=self._read_coll(Path(data))
            except Exception as e:
                self.detail.setText(f"失败 {e}")
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
        before=len(d["work_ids"])
        d["work_ids"]=[w for w in d["work_ids"] if w not in sel]
        if len(d["work_ids"])==before:
            self.detail.setText("所选不在丛书中")
            return
        d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
        self._mark_coll_changed(str(data))
        self._purge_buffer(sel)
        self._load_coll_works()
        self.detail.setText(f"已移除 {before-len(d['work_ids'])} 部，剩余 {len(d['work_ids'])} 部")

    def _purge_buffer(self, works):
        # 从内存缓冲（中栏缓存/勾选缓冲/搜索基准）中清除已删除书籍，避免残留并被重新加入
        seen={w.strip().upper() for w in works if w}
        before=len(self._current_works)
        self._current_works=[x for x in self._current_works if x.strip().upper() not in seen]
        self._base_works=[x for x in self._base_works if x.strip().upper() not in seen]
        for k in list(self._work_groups):
            if k.strip().upper() in seen:
                self._work_groups.pop(k, None)
        if len(self._current_works)!=before:
            self._show_works_sorted()
        for v in list(self._selected):
            if v.strip().upper() in seen:
                self._selected.discard(v)
        self._refresh_sel_count()

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

    def _render_coll_rows(self, works):
        fmts=[]
        if self.chk_pdf.isChecked(): fmts.append("pdf")
        if self.chk_epub.isChecked(): fmts.append("epub")
        if not fmts: fmts=["pdf"]
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QCheckBox as _Chk
        icon_dir=Path(__file__).parent / "theme" / "icons"
        for idx, w in enumerate(works, 1):
            title=self.sutra.title_of(w)
            if title==w:
                m=self.mapping.resolve(w)
                if m: title=m["name"]
            base=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
            fmts_status=[]
            for fmt in fmts:
                dest=official_ebook_source.local_path(w, fmt, base)
                exists=dest.exists()
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
            text_lab=QLabel(f"{idx}. {w} {title}")
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
                self._open_ebook(item.data(Qt.UserRole), prefer=lab.fmt)
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
            # 外部拖拽（中栏/目录树）：提取书籍加入当前丛书
            works, groups=self._mime_works_groups(e.mimeData())
            if not works:
                if e.source() is self.list:
                    for i in range(self.list.count()):
                        it=self.list.item(i)
                        if it and it.isSelected():
                            w=it.data(Qt.UserRole)
                            if w:
                                works.append(w)
                elif e.source() is self.tree:
                    works=self._tree_selected_works()
                else:
                    works=self._ordered_selected()
            for w in works:
                if w not in self._work_groups and w in groups:
                    self._work_groups[w]=groups[w]
            if works:
                data=self.coll_combo.currentData()
                if self._is_coll_placeholder(data):
                    # 无丛书选中：自动转到空白工作丛书并拖入
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
                    except Exception as ex:
                        self.detail.setText(f"失败 {ex}")
                        return
                added=0
                wg_touched=False
                for w in works:
                    if self._is_work_id(w) and w not in d["work_ids"]:
                        d["work_ids"].append(w)
                        added+=1
                    if self._is_work_id(w) and w in self._work_groups:
                        g=d.setdefault("work_groups",{})
                        if g.get(w)!=self._work_groups[w]:
                            g[w]=self._work_groups[w]; wg_touched=True
                if added or wg_touched:
                    d["updated_at"]=__import__("datetime").datetime.utcnow().isoformat()+"Z"
                    self._mark_coll_changed(str(data))
                    self._load_coll_works()
                    self.detail.setText(f"拖入 {added} 部")
                e.acceptProposedAction()
                return
        except Exception as ex:
            print(ex)
        from PySide6.QtWidgets import QListWidget as _L
        _L.dropEvent(self.coll_list, e)
        self._on_coll_reordered()

    def _on_coll_double_open(self, item):
        if not item:
            return
        w=item.data(Qt.UserRole)
        self._open_ebook(w, prefer="pdf")

    def _on_icon_clicked(self, work, fmt):
        self._open_ebook(work, prefer=fmt)

    def _open_ebook(self, work, prefer="pdf"):
        base=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
        for fmt in [prefer] + [f for f in ["pdf","epub"] if f!=prefer]:
            dest=official_ebook_source.local_path(work, fmt, base)
            if dest.exists():
                try:
                    from PySide6.QtGui import QDesktopServices
                    from PySide6.QtCore import QUrl
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(dest.resolve())))
                    self.detail.setText(f"已打开 {dest}")
                except Exception as e:
                    self.detail.setText(f"打开失败 {e}")
                return
        self.detail.setText(f"未找到 {work} 的 {prefer}，请先下载")

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

    def _add_record(self, text):
        # 下载记录：文本形式（可选中拷贝）；成功 ✓ / 更新 ↻ 蓝字 / 跳过 – 灰字 / 失败 ✗ 红字
        import html as _html
        t=_html.escape(text)
        if text.startswith("失败"):
            line=f'<font color="red">✗ {t}</font>'
        elif text.startswith("更新"):
            line=f'<font color="blue">↻ {t}</font>'
        elif text.startswith("跳过"):
            line=f'<font color="gray">– {t}</font>'
        elif text.startswith("完成"):
            line=f'✓ {t}'
        else:
            line=t
        self.log_view.append(line)

    # ---------- 下载 ----------
    def _download(self):
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
        fmts=[]
        if self.chk_pdf.isChecked(): fmts.append("pdf")
        if self.chk_epub.isChecked(): fmts.append("epub")
        if not fmts:
            self.detail.setText("请至少选择一种格式 pdf/epub")
            return
        dest_dir=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
        self.btn_download.setText("取消下载")
        self.log_view.clear()
        self.tab_bottom.setCurrentIndex(1)
        from cbeta_publish.books.download_worker import DownloadWorker
        self._dl_worker=DownloadWorker(works, fmts, dest_dir)
        self._dl_worker.progress.connect(self._add_record)
        def on_done(ok, total, failed):
            self._add_record(f"完成 {ok}/{total}")
            if failed:
                self._add_record("失败: " + ", ".join(failed[:3]) + (f" 等共 {len(failed)} 个" if len(failed)>3 else ""))
                QMessageBox.warning(self, "下载失败", f"{len(failed)} 个文件下载失败：\n" + "\n".join(failed[:10]) + (f"\n...共 {len(failed)} 个" if len(failed)>10 else ""))
            self.btn_download.setText("下载")
            if ok+len(failed)<total:
                self._add_record(f"取消 剩余 {total-ok-len(failed)} 个未下载")
            self._load_coll_works()
            self.detail.setText(f"下载完成 {ok}/{total}")
            self._prompt_save_collection("下载完成，", str(data))
            self._dl_worker=None
        self._dl_worker.finished_all.connect(on_done)
        self._dl_worker.start()

    def _on_download_button(self):
        # 双态按钮：空闲点开始下载，下载中点取消
        if getattr(self, "_dl_worker", None) is not None:
            self._cancel_download()
        else:
            self._download()

    def _cancel_download(self):
        w=getattr(self, "_dl_worker", None)
        if w is None:
            return
        try:
            w.stop()
        except Exception:
            pass
        self.detail.setText("正在取消下载…")

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
        return Path(self.config.get("output_dir","my_books"))

    def _build_menu(self):
        # 菜单栏：设置（含未来 xml2pdf 等工具的扩展位）
        from cbeta_publish.gui.settings_dialog import SettingsDialog
        bar=self.menuBar()
        m_settings=bar.addMenu("设置")
        act_settings=m_settings.addAction("设置…")
        act_settings.triggered.connect(self._open_settings)
        m_tools=bar.addMenu("工具")
        act_xml2pdf=m_tools.addAction("xml2pdf 独立窗…")
        act_xml2pdf.setToolTip("打开 E:/dev/cbeta/xml2pdf 独立转换窗")
        act_xml2pdf.triggered.connect(self._open_xml2pdf_window)

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
            # 目录过滤等即时刷新当前视图
            self._on_nav_changed(self.nav_combo.currentText())
            if saved:
                self.detail.setText("设置已保存（界面字体即时生效；封面字体下次合并生效）")
            else:
                self.detail.setText("设置已应用（未写盘，仅本次运行生效）")

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

    def _intro_for(self, ok_works, cover_cfg):
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
        dlg.setMinimumSize(640, 440)
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
        st={"cancel": False, "lines": []}
        def _cancel():
            st["cancel"]=True
            btn.setEnabled(False)
            btn.setText("取消中…")
        btn.clicked.connect(_cancel)
        dlg.rejected.connect(_cancel)
        dlg.show()
        def _put(text, is_html):
            # 统一走 insertHtml：纯文本先转义；每次显式复位字符格式，
            # 否则链接的蓝/下划线/锚点格式会泄漏给后续行（源文件名变蓝即此因）。
            sb=log.verticalScrollBar()
            at_bottom=sb.value() >= sb.maximum()-8
            pos=sb.value()
            log.moveCursor(QTextCursor.End)
            c=log.textCursor()
            c.setCharFormat(QTextCharFormat())
            c.insertBlock()
            log.setTextCursor(c)
            log.insertHtml(text if is_html else _htm.escape(str(text)))
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
            # 窗口保留由用户手动关闭。（offscreen/自动化环境直接关闭，避免阻塞。）
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
            sb=log.verticalScrollBar()
            sb.setValue(sb.maximum())
            dlg.exec()
        st["finish"]=finish
        return dlg, update, st

    def _merge(self):
        fmts=[]
        if self.chk_pdf.isChecked(): fmts.append("pdf")
        if self.chk_epub.isChecked(): fmts.append("epub")
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
        from cbeta_publish.books.official_ebook_source import download_ebook
        from cbeta_publish.books.ebook_merger import merge_pdfs, merge_epubs, MergeCancelled
        from cbeta_publish.books import xml2pdf_bridge
        from cbeta_publish.books import official_ebook_source
        dest_dir=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
        src_default=d.get("source") or self.config.get("default_source","official")
        work_sources=d.get("work_sources",{}) or {}
        def _src(w):
            return work_sources.get(w, src_default)
        xml_cache=self._out_dir()/"_xml_convert"/(d.get("name") or "book")
        xml_opts=(d.get("xml_options") or self.config.get("xml2pdf",{}) or {})
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
            ret=QMessageBox.question(self, "下载确认", f"有 {len(missing)} 部未下载（{', '.join(missing[:3])}{'...' if len(missing)>3 else ''}），是否先下载后合并？", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ret==QMessageBox.Cancel:
                return
            elif ret==QMessageBox.Yes:
                for fmt in fmts:
                    for w in works:
                        if _src(w)=="official" and not _official_dest(fmt, w).exists():
                            download_ebook(w, fmt, dest_dir)
        skip_missing = (ret == QMessageBox.No) if missing else False
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
                    out=xml_cache/f"{w}.{fmt}"
                    if not out.exists():
                        xml=xml2pdf_bridge.find_xml(w, self.config, mapping=self.mapping)
                        if xml:
                            xml2pdf_bridge.convert(w, xml, xml_cache, self.config, fmt=fmt, opts=xml_opts)
                    if out.exists():
                        ok.append(out); ok_titles.append(self.sutra.title_of(w)); ok_works.append(w)
                    else:
                        failed.append(f"{w}.{fmt} XML转换失败")
                    if not bump(f"[{fmt}] 转换 {out.name}"):
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
                    intro=self._intro_for(gworks, cover_cfg)
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
            # 首条为输出目录链接，其余为各产物文件链接（丛书信息页可点开，不再弹窗询问）
            _pub_dir=str((self._out_dir()/d["name"]).resolve())
            self._last_publish[str(data)]=[("→ 打开输出目录", _pub_dir)]+[(Path(s).name, s) for s in success]
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
        self.tab_bottom.setCurrentIndex(0)   # 合并完成：切到「丛书信息」显示产物与链接
        if success:
            self.detail.setText(f"合并成功 {len(success)} 个文件 → {self._out_dir()/d['name']}"
                                + (f"（跳过 {len(skipped)}）" if skipped else "")
                                + (f"（失败 {len(failed)}）" if failed else ""))
            self._prompt_save_collection("合并完成，", str(data))
        else:
            QMessageBox.warning(self,"失败", "合并失败:\n" + "\n".join(failed))

    def _zip(self):
        fmts=[]
        if self.chk_pdf.isChecked(): fmts.append("pdf")
        if self.chk_epub.isChecked(): fmts.append("epub")
        if not fmts:
            QMessageBox.warning(self,"失败","请选择格式 pdf/epub")
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
        dest_dir=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
        missing=[]
        for fmt in fmts:
            for w in works:
                dest=official_ebook_source.local_path(w, fmt, dest_dir)
                if not dest.exists():
                    missing.append(f"{w}.{fmt}")
        if missing:
            self._wrap_box(QMessageBox.Warning, "未全部下载", f"有 {len(missing)} 部未下载（{', '.join(missing[:3])}{'...' if len(missing)>3 else ''}），请先点击「下载」后再打包。")
            return
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
                f=official_ebook_source.local_path(w, fmt, dest_dir)
                if f.exists():
                    files.append(f)
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
        fmts=[]
        if self.chk_pdf.isChecked(): fmts.append("pdf")
        if self.chk_epub.isChecked(): fmts.append("epub")
        if not fmts:
            QMessageBox.warning(self,"失败","请选择格式")
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
        dest_dir=Path(self.config.get("cbeta_ebooks_dir", self.config.get("official_ebooks_dir","./cbeta_ebooks")))
        missing=[]
        for fmt in fmts:
            for w in works:
                dest=official_ebook_source.local_path(w, fmt, dest_dir)
                if not dest.exists():
                    missing.append(f"{w}.{fmt}")
        if missing:
            self._wrap_box(QMessageBox.Warning, "未全部下载", f"有 {len(missing)} 部未下载（{', '.join(missing[:3])}{'...' if len(missing)>3 else ''}），请先点击「下载」后再导出。")
            return
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
                src=official_ebook_source.local_path(w, fmt, dest_dir)
                if src.exists():
                    try:
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
            self._wrap_box(QMessageBox.Information, "成功", f"导出成功 {len(success)} 文件到:\n{target}\n" + "\n".join(success[:3]) + ("\n..." if len(success)>3 else "") + ("\n失败:\n" + "\n".join(failed[:5]) + (f"\n... 共 {len(failed)} 项失败" if len(failed)>5 else "") if failed else ""))
            self._prompt_save_collection("导出完成，", str(data))
        else:
            self._wrap_box(QMessageBox.Warning, "失败", "导出失败:\n" + "\n".join(failed[:5]) + (f"\n... 共 {len(failed)} 项" if len(failed)>5 else ""))