# -*- coding: utf-8 -*-
"""合并分册设置弹框：「合并时选择」模式下每次合并弹出。

模式三选一：不分册 / 按刊本册 / 按目录（部类）；深度 1–5（默认 2，
不分册时禁用）；文件名模板输入在深度右侧，改动随确定同步设置。
预览：首组原文全文示例（随深度动态变化，不分册清空）＋文件名清单。
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QRadioButton,
                               QButtonGroup, QLabel, QSpinBox, QListWidget,
                               QDialogButtonBox, QWidget, QLineEdit)

MODE_NONE, MODE_VOLUME, MODE_CATALOG, MODE_MANUAL = "none", "volume", "catalog", "manual"


class MergeDialog(QDialog):
    def __init__(self, parent=None, default_mode=MODE_NONE, default_depth=2,
                 default_template="", preview=None):
        """
        preview(mode, depth) -> [(label, count, filename), ...]，用于实时预览。
        """
        super().__init__(parent)
        self.setWindowTitle("合并设置（分册）")
        self.resize(520, 460)
        self._preview = preview
        v = QVBoxLayout(self)

        # 模式
        v.addWidget(QLabel("分册模式："))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(row)
        self.rb_none = QRadioButton("不分册")
        self.rb_volume = QRadioButton("按刊本册")
        self.rb_catalog = QRadioButton("按目录（部类）")
        self.rb_manual = QRadioButton("按手工分册")
        self.rb_volume.setToolTip("按 mulu/vol.json 的刊本/册分组")
        self.rb_catalog.setToolTip("按部类树路径分组（如 01 阿含部類 / 長阿含經）")
        self.rb_manual.setToolTip("按右栏「手工分册」的卷分组（未分组自成一组）")
        for i, b in enumerate((self.rb_none, self.rb_volume, self.rb_catalog, self.rb_manual)):
            h.addWidget(b)
            self.group.addButton(b, i)
        h.addStretch()
        v.addWidget(row)

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
        self.rb_none.toggled.connect(self._refresh)
        self.rb_volume.toggled.connect(self._refresh)
        self.rb_catalog.toggled.connect(self._refresh)
        self.rb_manual.toggled.connect(self._refresh)
        self.sp_depth.valueChanged.connect(self._refresh)
        self.ed_template.textChanged.connect(self._refresh)
        self._refresh()

    def _select(self, mode):
        rb = {MODE_VOLUME: self.rb_volume, MODE_CATALOG: self.rb_catalog,
              MODE_MANUAL: self.rb_manual}.get(mode)
        (rb or self.rb_none).setChecked(True)

    def chosen(self):
        """返回 (mode, depth)：none/volume/catalog/manual。"""
        if self.rb_volume.isChecked():
            mode = MODE_VOLUME
        elif self.rb_catalog.isChecked():
            mode = MODE_CATALOG
        elif self.rb_manual.isChecked():
            mode = MODE_MANUAL
        else:
            mode = MODE_NONE
        return mode, int(self.sp_depth.value())

    def template(self):
        """文件名模板输入（strip；空由调用方回退缺省）"""
        return self.ed_template.text().strip()

    def _refresh(self, *_):
        mode, depth = self.chosen()
        self.sp_depth.setEnabled(mode in (MODE_VOLUME, MODE_CATALOG))
        self.lbl_example.clear()
        self.lst.clear()
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
