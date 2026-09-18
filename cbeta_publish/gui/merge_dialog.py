# -*- coding: utf-8 -*-
"""合并分册设置弹框：「合并时选择」模式下每次合并弹出。

模式三选一：不分册 / 按刊本册 / 按目录（部类）；深度 1–5（默认 2，
不分册时禁用）。预览列出该模式+深度下的分组 → 部数 + 拟输出文件名。
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QRadioButton,
                               QButtonGroup, QLabel, QSpinBox, QListWidget,
                               QDialogButtonBox, QWidget)

MODE_NONE, MODE_VOLUME, MODE_CATALOG = "none", "volume", "catalog"


class MergeDialog(QDialog):
    def __init__(self, parent=None, default_mode=MODE_NONE, default_depth=2,
                 preview=None):
        """
        preview(mode, depth) -> [(label, count, stem), ...]，用于实时预览。
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
        self.rb_volume.setToolTip("按 mulu/vol.json 的刊本/册分组")
        self.rb_catalog.setToolTip("按部类树路径分组（如 01 阿含部類 / 長阿含經）")
        for i, b in enumerate((self.rb_none, self.rb_volume, self.rb_catalog)):
            h.addWidget(b)
            self.group.addButton(b, i)
        h.addStretch()
        v.addWidget(row)

        # 深度
        drow = QWidget()
        dh = QHBoxLayout(drow)
        dh.setContentsMargins(0, 0, 0, 0)
        dh.addWidget(QLabel("深度："))
        self.sp_depth = QSpinBox()
        self.sp_depth.setRange(1, 5)
        self.sp_depth.setValue(max(1, min(5, int(default_depth or 2))))
        self.sp_depth.setToolTip("路径取前 N 段：1=按刊本名/顶层部类；2=刊本名_册、部类_子组（默认）")
        dh.addWidget(self.sp_depth)
        dh.addStretch()
        v.addWidget(drow)

        v.addWidget(QLabel("预览（分组 → 部数 → 文件名）："))
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
        self.sp_depth.valueChanged.connect(self._refresh)
        self._refresh()

    def _select(self, mode):
        rb = {MODE_VOLUME: self.rb_volume, MODE_CATALOG: self.rb_catalog}.get(mode)
        (rb or self.rb_none).setChecked(True)

    def chosen(self):
        """返回 (mode, depth)：none/volume/catalog。"""
        if self.rb_volume.isChecked():
            mode = MODE_VOLUME
        elif self.rb_catalog.isChecked():
            mode = MODE_CATALOG
        else:
            mode = MODE_NONE
        return mode, int(self.sp_depth.value())

    def _refresh(self, *_):
        mode, depth = self.chosen()
        self.sp_depth.setEnabled(mode != MODE_NONE)
        self.lst.clear()
        if self._preview is None:
            return
        try:
            groups = self._preview(mode, depth)
        except Exception as e:
            self.lst.addItem(f"预览失败：{e}")
            return
        for label, n, stem in groups:
            self.lst.addItem(f"{label}（{n} 部） → {stem}")
