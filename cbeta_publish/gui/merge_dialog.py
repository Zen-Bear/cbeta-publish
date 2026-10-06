# -*- coding: utf-8 -*-
"""合并分册设置弹框：合并时选择 / 单书分册编辑共用。

- 模式：不分册 / 按刊本册 / 按目录（部类）/ 按手工分册 / 按作者 / 按朝代
  （`allow_ask=True` 时再加「合并时选择」，供单书分册配置用）。
- 深度 1–5（不分册时禁用）；文件名模板；预览（首组原文示例＋文件名清单）。
- `allow_follow=True` 时顶部有「跟随全局」：勾选则控件显示并禁用为当前全局值，
  `result_merge()` 返回 None。
"""
from PySide6.QtWidgets import (QCheckBox, QDialog, QVBoxLayout, QHBoxLayout,
                               QRadioButton, QButtonGroup, QLabel, QSpinBox,
                               QListWidget, QDialogButtonBox, QWidget, QLineEdit)

MODE_NONE, MODE_VOLUME, MODE_CATALOG, MODE_MANUAL = "none", "volume", "catalog", "manual"
MODE_AUTHOR, MODE_DYNASTY, MODE_ASK = "author", "dynasty", "ask"

_MODE_LABEL = {MODE_NONE: "不分册", MODE_VOLUME: "按刊本册",
               MODE_CATALOG: "按目录（部类）", MODE_MANUAL: "按手工分册",
               MODE_AUTHOR: "按作者", MODE_DYNASTY: "按朝代", MODE_ASK: "合并时选择"}


class MergeDialog(QDialog):
    def __init__(self, parent=None, default_mode=MODE_NONE, default_depth=2,
                 default_template="", preview=None, allow_follow=False,
                 allow_ask=False, follow=False, global_cfg=None):
        """
        preview(mode, depth) -> [(label, count, filename), ...]，用于实时预览。
        global_cfg=(mode, depth, template)：跟随全局时显示的值。
        """
        super().__init__(parent)
        self.setWindowTitle("合并设置（分册）")
        self.resize(520, 460)
        self._preview = preview
        self._allow_ask = bool(allow_ask)
        self._global = tuple(global_cfg) if global_cfg else (MODE_NONE, 2, "")
        v = QVBoxLayout(self)

        # 跟随全局
        self._chk_follow = None
        self.lbl_global = None
        if allow_follow:
            self._chk_follow = QCheckBox("跟随全局")
            self._chk_follow.setToolTip("勾选=用设置页的全局分册配置；取消勾选可改为本丛书专属")
            v.addWidget(self._chk_follow)
            self.lbl_global = QLabel()
            self.lbl_global.setStyleSheet("color: gray;")
            v.addWidget(self.lbl_global)
            self._update_global_label()

        # 模式
        v.addWidget(QLabel("分册模式："))
        self.group = QButtonGroup(self)
        self.rb_none = QRadioButton("不分册")
        self.rb_volume = QRadioButton("按刊本册")
        self.rb_catalog = QRadioButton("按目录（部类）")
        self.rb_manual = QRadioButton("按手工分册")
        self.rb_author = QRadioButton("按作者")
        self.rb_dynasty = QRadioButton("按朝代")
        self.rb_ask = QRadioButton("合并时选择") if allow_ask else None
        self.rb_volume.setToolTip("按 mulu/vol.json 的刊本/册分组")
        self.rb_catalog.setToolTip("按部类树路径分组（如 01 阿含部類 / 長阿含經）")
        self.rb_manual.setToolTip("按右栏「手工分册」的卷分组（未分组自成一组）")
        self.rb_author.setToolTip("按作者（译/撰者）分组；未署名置末")
        self.rb_dynasty.setToolTip("按朝代分组（朝代序；未詳置末）")
        if self.rb_ask is not None:
            self.rb_ask.setToolTip("合并时每次弹框选择（用上次选择）")
        self._rbs = [self.rb_none, self.rb_volume, self.rb_catalog, self.rb_manual,
                     self.rb_author, self.rb_dynasty]
        if self.rb_ask is not None:
            self._rbs.append(self.rb_ask)
        second = (self.rb_author, self.rb_dynasty) + ((self.rb_ask,) if self.rb_ask else ())
        self._rows = ((self.rb_none, self.rb_volume, self.rb_catalog, self.rb_manual),
                      second)
        _i = 0
        for _row in self._rows:
            rw = QWidget()
            rh = QHBoxLayout(rw)
            rh.setContentsMargins(0, 0, 0, 0)
            for b in _row:
                rh.addWidget(b)
                self.group.addButton(b, _i)
                _i += 1
            rh.addStretch()
            v.addWidget(rw)

        # 深度 + 文件名模板
        drow = QWidget()
        dh = QHBoxLayout(drow)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.addWidget(QLabel("深度："))
        self.sp_depth = QSpinBox()
        self.sp_depth.setRange(1, 5)
        self.sp_depth.setValue(max(1, min(5, int(default_depth or 2))))
        self.sp_depth.setToolTip("路径取前 N 段：1=按刊本名/顶层部类；2=刊本名_册、部类_子组（默认）")
        dh.addWidget(self.sp_depth)
        dh.addWidget(QLabel("文件名模板："))
        self.ed_template = QLineEdit(str(default_template or ""))
        self.ed_template.setToolTip("分册文件名模板；确定后同步设置页（变量见设置页示例）")
        dh.addWidget(self.ed_template, 1)
        v.addWidget(drow)

        self.lbl_example = QLabel()
        self.lbl_example.setWordWrap(True)
        self.lbl_example.setStyleSheet("color: gray;")
        v.addWidget(self.lbl_example)
        v.addWidget(QLabel("文件名："))
        self.lst = QListWidget()
        v.addWidget(self.lst, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

        self._select(default_mode)
        if self._chk_follow is not None:
            self._chk_follow.setChecked(bool(follow))
            self._chk_follow.toggled.connect(self._on_follow)
        for _rb in self._rbs:
            _rb.toggled.connect(self._refresh)
        self.sp_depth.valueChanged.connect(self._refresh)
        self.ed_template.textChanged.connect(self._refresh)
        if self.follow_global():
            self._on_follow(True)
        else:
            self._refresh()

    # ---------- 模式 ----------
    def _select(self, mode):
        mp = {MODE_VOLUME: self.rb_volume, MODE_CATALOG: self.rb_catalog,
              MODE_MANUAL: self.rb_manual, MODE_AUTHOR: self.rb_author,
              MODE_DYNASTY: self.rb_dynasty}
        if self.rb_ask is not None:
            mp[MODE_ASK] = self.rb_ask
        (mp.get(mode) or self.rb_none).setChecked(True)

    def chosen(self):
        """返回 (mode, depth)。"""
        if self.rb_volume.isChecked():
            mode = MODE_VOLUME
        elif self.rb_catalog.isChecked():
            mode = MODE_CATALOG
        elif self.rb_manual.isChecked():
            mode = MODE_MANUAL
        elif self.rb_author.isChecked():
            mode = MODE_AUTHOR
        elif self.rb_dynasty.isChecked():
            mode = MODE_DYNASTY
        elif self.rb_ask is not None and self.rb_ask.isChecked():
            mode = MODE_ASK
        else:
            mode = MODE_NONE
        return mode, int(self.sp_depth.value())

    def template(self):
        """文件名模板输入（strip；空由调用方回退缺省）"""
        return self.ed_template.text().strip()

    # ---------- 跟随全局 ----------
    def follow_global(self):
        return bool(self._chk_follow.isChecked()) if self._chk_follow is not None else False

    def result_merge(self):
        """单书分册配置：跟随全局→None；否则 {mode,depth,name_template}。"""
        if self.follow_global():
            return None
        mode, depth = self.chosen()
        return {"mode": mode, "depth": depth, "name_template": self.template()}

    def _update_global_label(self):
        if self.lbl_global is None:
            return
        gm, gd, gt = self._global
        self.lbl_global.setText(
            f"当前全局：{_MODE_LABEL.get(gm, gm)}，深度 {gd}，命名模板 {gt or '（默认）'}")

    def _on_follow(self, checked):
        if checked:
            gm, gd, gt = self._global
            self._select(gm)
            self.sp_depth.setValue(max(1, min(5, int(gd or 2))))
            self.ed_template.setText(str(gt or ""))
        self._refresh()

    # ---------- 刷新 ----------
    def _refresh(self, *_):
        mode, depth = self.chosen()
        follow = self.follow_global()
        for rb in self._rbs:
            rb.setEnabled(not follow)
        self.sp_depth.setEnabled(not follow and mode in (MODE_VOLUME, MODE_CATALOG))
        self.ed_template.setEnabled(not follow)
        self.lbl_example.clear()
        self.lst.clear()
        if follow:
            return
        if mode == MODE_ASK:
            self.lbl_example.setText("合并时每次弹框选择（用上次选择）")
            return
        if self._preview is None:
            return
        try:
            groups = self._preview(mode, depth)
        except Exception as e:
            self.lst.addItem(f"预览失败：{e}")
            return
        if mode == MODE_NONE:
            # 不分册：无例子行，清单只显示文件名（随模板实时展开）
            for _label, _n, stem in groups:
                self.lst.addItem(stem)
            return
        shown = False
        for label, n, stem in groups:
            if not shown and label:
                self.lbl_example.setText(f"例：{label}（{n} 部）")
                shown = True
            if label is None:
                continue
            self.lst.addItem(stem)
