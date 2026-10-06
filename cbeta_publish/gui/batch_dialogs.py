# -*- coding: utf-8 -*-
"""批量操作对话框：批量更新素材 / 批量合并（含 ZIP）。

两个入口共用同一 `BatchDialog`（`mode="update"|"merge"`）：
- 共用丛书复选清单（默认全选非空；全选/全不选）。
- 「更新素材」只设计素材刷新选项；「合并丛书」另有 合并/ZIP/自动备齐/报告
  与每部丛书独立分册配置。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

#: 官方刷新策略（值传给 _prepare_official 的 policy）
OFFICIAL_POLICIES = [("XML较新则重下（推荐）", "stale"),
                     ("仅缺（不自动更新）", "missing"),
                     ("全部重新下载", "all")]
#: 自制刷新策略
SELF_POLICIES = [("仅缺（源新自动重制）", "missing"),
                 ("全部重制", "all")]
#: 分册模式（None=跟随全局）
MERGE_MODES = [("跟随全局", None), ("不分册", "none"), ("按刊本册", "volume"),
               ("按目录(部类)", "catalog"), ("按手工分册", "manual"),
               ("按作者", "author"), ("按朝代", "dynasty"), ("合并时选择", "ask")]
_MODE_LABEL = {v: k for k, v in MERGE_MODES}

#: 对话框最小宽度（比默认宽一倍，约 2×）
_DLG_MIN_W = 640


def effective_merge_text(d, cfg_fn):
    """有效分册配置显示文本（含来源）；cfg_fn(d)->(mode,depth,tpl)。"""
    try:
        mode, depth, tpl = cfg_fn(d)
    except Exception:
        return "（未知）"
    src = "丛书" if isinstance((d or {}).get("merge"), dict) else "跟随全局"
    if mode in ("volume", "catalog"):
        return f"{src}：{_MODE_LABEL.get(mode, mode)}（深度{depth}）"
    return f"{src}：{_MODE_LABEL.get(mode, mode)}"


class CollectionChecklist(QTreeWidget):
    """丛书复选清单：列 [丛书, 部数, 分册]；默认全选非空。

    「分册」列可用 `set_merge_column_visible(False)` 隐藏（更新素材模式无关）。
    """

    def __init__(self, items, cfg_fn, parent=None, show_merge=True):
        super().__init__(parent)
        self._cfg_fn = cfg_fn
        self._show_merge = show_merge
        self.setColumnCount(3)
        self.setHeaderLabels(["丛书", "部数", "分册"])
        self.setRootIsDecorated(False)
        self._items = list(items)
        for path, d in self._items:
            n = len(d.get("work_ids") or [])
            cols = [d.get("name", ""), str(n),
                    effective_merge_text(d, cfg_fn)]
            it = QTreeWidgetItem(cols)
            it.setData(0, Qt.UserRole, str(path))
            if show_merge:
                it.setToolTip(2, "本丛书合并时的切分方式；缺省跟随全局（可在下方「设置当前丛书分册…」修改）")
            flags = it.flags() | Qt.ItemIsUserCheckable
            if n:
                it.setCheckState(0, Qt.Checked)
            else:
                it.setCheckState(0, Qt.Unchecked)
                flags &= ~Qt.ItemIsEnabled
            it.setFlags(flags)
            self.addTopLevelItem(it)
        self.setColumnWidth(0, 260)
        self.setColumnWidth(1, 60)
        self.set_merge_column_visible(show_merge)

    def set_merge_column_visible(self, vis):
        self._show_merge = bool(vis)
        self.setColumnHidden(2, not vis)

    def _all_checkable(self):
        return [self.topLevelItem(i) for i in range(self.topLevelItemCount())
                if self.topLevelItem(i).flags() & Qt.ItemIsEnabled]

    def check_all(self, checked):
        for it in self._all_checkable():
            it.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

    def selected_items(self):
        out = []
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            if it.checkState(0) == Qt.Checked:
                p = it.data(0, Qt.UserRole)
                for path, d in self._items:
                    if str(path) == p:
                        out.append((path, d))
                        break
        return out

    def current_item(self):
        it = self.currentItem()
        if it is None:
            return None
        p = it.data(0, Qt.UserRole)
        for path, d in self._items:
            if str(path) == p:
                return path, d
        return None

    def item_pair(self, item):
        """QTreeWidgetItem → (path, d)；找不到回 None。"""
        if item is None:
            return None
        key = item.data(0, Qt.UserRole)
        for path, d in self._items:
            if str(path) == key:
                return path, d
        return None

    def set_merge_text(self, path_key, text):
        if not self._show_merge:
            return
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            if it.data(0, Qt.UserRole) == path_key:
                it.setText(2, text)
                break


class BatchDialog(QDialog):
    """批量操作对话框：mode="update"|"merge"|"combined"（combined=窗口内切换）。"""

    def __init__(self, items, cfg_fn, parent=None, *, mode="merge",
                 merge_fmts=None, zip_fmts=None, can_merge=True,
                 save_merge_fn=None, preview_fn=None, global_cfg=None):
        super().__init__(parent)
        self._fixed_mode = mode if mode in ("update", "merge") else None
        self._mode = "merge" if self._fixed_mode is None else self._fixed_mode
        self._cfg_fn = cfg_fn
        self._save_merge_fn = save_merge_fn
        self._preview_fn = preview_fn
        self._global_cfg = tuple(global_cfg) if global_cfg else ("none", 2, "")
        self._merge_fmts = list(merge_fmts or [])
        self._zip_fmts = list(zip_fmts or [])
        self._can_merge = bool(can_merge)
        self.setMinimumWidth(_DLG_MIN_W)
        self.resize(_DLG_MIN_W, 520)
        self._overrides = {}   # {path_str: merge|None}（仅 merge）
        self._merge_widgets = []

        v = QVBoxLayout(self)
        if self._fixed_mode is None:
            from PySide6.QtWidgets import QButtonGroup, QRadioButton
            self.setWindowTitle("批量处理")
            rowm = QHBoxLayout()
            rowm.addWidget(QLabel("操作："))
            self.rb_update = QRadioButton("更新素材")
            self.rb_merge = QRadioButton("合并丛书")
            self.rb_merge.setChecked(True)
            self._mode_group = QButtonGroup(self)
            self._mode_group.addButton(self.rb_update)
            self._mode_group.addButton(self.rb_merge)
            rowm.addWidget(self.rb_update)
            rowm.addWidget(self.rb_merge)
            rowm.addStretch(1)
            v.addLayout(rowm)
            self.rb_update.toggled.connect(self._apply_mode)
        else:
            self.setWindowTitle("批量更新素材" if mode == "update" else "批量合并丛书")

        hdr = QHBoxLayout()
        self.lbl_choose = QLabel()
        hdr.addWidget(self.lbl_choose)
        hdr.addStretch(1)
        b_all = QPushButton("全选")
        b_none = QPushButton("全不选")
        b_all.clicked.connect(lambda: self.list.check_all(True))
        b_none.clicked.connect(lambda: self.list.check_all(False))
        hdr.addWidget(b_all)
        hdr.addWidget(b_none)
        v.addLayout(hdr)
        self.list = CollectionChecklist(items, cfg_fn, show_merge=True)
        self.list.set_merge_column_visible(self._mode == "merge")
        v.addWidget(self.list, 1)

        self._opt = QVBoxLayout()
        v.addLayout(self._opt)

        self.chk_merge = QCheckBox("合并（" + ", ".join(self._merge_fmts) + "）")
        self.chk_merge.setChecked(self._can_merge and bool(self._merge_fmts))
        self.chk_merge.setEnabled(self._can_merge and bool(self._merge_fmts))
        self._opt.addWidget(self.chk_merge)
        self._merge_widgets.append(self.chk_merge)

        self.chk_zip = QCheckBox("ZIP 打包（" + ", ".join(self._zip_fmts) + "）")
        self.chk_zip.setChecked(bool(self._zip_fmts))
        self.chk_zip.setEnabled(bool(self._zip_fmts))
        self._opt.addWidget(self.chk_zip)
        self._merge_widgets.append(self.chk_zip)

        self.chk_prepare = QCheckBox("合并前自动备齐：官方书有更新、自制书源较新时先刷新，已是最新则跳过（通常很快）")
        self.chk_prepare.setToolTip(
            "开：阶段一按下面策略刷新素材（官方书按过期判据重下、自制书源新重制），"
            "已刷新过的会跳过；\n关：只用现有素材，缺的记失败（适合先「批量更新素材」再合并）。")
        self.chk_prepare.setChecked(True)
        self._opt.addWidget(self.chk_prepare)
        self._merge_widgets.append(self.chk_prepare)

        self.cb_official = self._policy_combo("官方书", OFFICIAL_POLICIES, 0)
        self.cb_self = self._policy_combo("自制书", SELF_POLICIES, 0)

        # 分册编辑：点击列表「分册」列任意一行进入
        self.list.itemClicked.connect(self._on_list_clicked)

        self.chk_report = QCheckBox("报告落盘")
        self.chk_report.setChecked(True)
        v.addWidget(self.chk_report)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)
        self._apply_mode()

    def _policy_combo(self, label, choices, default_idx=0):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        cb = QComboBox()
        for text, val in choices:
            cb.addItem(text, val)
        cb.setCurrentIndex(default_idx)
        row.addWidget(cb, 1)
        self._opt.addLayout(row)
        return cb

    def _apply_mode(self, *_):
        if self._fixed_mode is None:
            self._mode = "merge" if self.rb_merge.isChecked() else "update"
        on = self._mode == "merge"
        for w in self._merge_widgets:
            w.setVisible(on)
        self.list.set_merge_column_visible(on)
        self.lbl_choose.setText(
            "选择丛书（默认全选非空；点击『分册』列可设置该丛书分册）："
            if on else "选择丛书（默认全选非空）：")

    def effective_mode(self):
        """combined=当前选择；固定模式=构造时指定。"""
        return self._mode

    # ---------- 通用 ----------
    def selected_items(self):
        return self.list.selected_items()

    def save_report(self):
        return self.chk_report.isChecked()

    def official_policy(self):
        return self.cb_official.currentData()

    def self_policy(self):
        return self.cb_self.currentData()

    # ---------- 仅 merge ----------
    def _on_list_clicked(self, item, col):
        if self._mode == "merge" and col == 2:
            self._edit_merge(item)

    def _edit_merge(self, item=None):
        if self._mode != "merge":
            return
        if item is None:
            item = self.list.currentItem()
        pair = self.list.item_pair(item)
        if pair is None:
            return
        path, d = pair
        key = str(path)
        from cbeta_publish.gui.merge_dialog import MergeDialog
        m = d.get("merge") if isinstance(d.get("merge"), dict) else None
        gm, gd, gt = self._global_cfg
        dlg = MergeDialog(self,
                          default_mode=(m or {}).get("mode", "none"),
                          default_depth=int((m or {}).get("depth", gd) or gd),
                          default_template=(m or {}).get("name_template", gt) or "",
                          preview=None, allow_follow=True, allow_ask=True,
                          follow=(m is None), global_cfg=(gm, gd, gt))
        if self._preview_fn is not None:
            dlg._preview = lambda mm, dep: self._preview_fn(d, mm, dep, dlg.template())
        dlg._refresh()
        if dlg.exec() != QDialog.Accepted:
            return
        res = dlg.result_merge()
        if self._save_merge_fn is not None:
            self._save_merge_fn(key, res)
        if res is None:
            d.pop("merge", None)
        else:
            d["merge"] = dict(res)
        self.list.set_merge_text(key, effective_merge_text(d, self._cfg_fn))

    def merge_overrides(self):
        return dict(self._overrides)

    def merge_enabled(self):
        return self._mode == "merge" and self.chk_merge.isChecked()

    def zip_enabled(self):
        return self._mode == "merge" and self.chk_zip.isChecked()

    def auto_prepare(self):
        return self._mode == "merge" and self.chk_prepare.isChecked()


class BatchUpdateDialog(BatchDialog):
    def __init__(self, items, cfg_fn, parent=None):
        super().__init__(items, cfg_fn, parent, mode="update")


class BatchMergeDialog(BatchDialog):
    def __init__(self, items, cfg_fn, parent=None, *, merge_fmts=None,
                 zip_fmts=None, can_merge=True, **kw):
        super().__init__(items, cfg_fn, parent, mode="merge",
                         merge_fmts=merge_fmts, zip_fmts=zip_fmts, can_merge=can_merge,
                         **kw)
