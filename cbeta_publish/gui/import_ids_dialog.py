# -*- coding: utf-8 -*-
"""「导入 ID 建丛书」对话框：粘贴/文件/网页 → 解析预览 → 勾选创建。

单一内容区（`QPlainTextEdit`）三种来源灌入且可继续手改；`解析/预览` 生成表
`选｜序号｜状态｜原始｜规范ID｜注释(可编辑)｜目录书名`（状态全部保留并标注）。
底部「全选/全不选/删除选中行/删除无效」＋右侧「已选 N 部」计数；表格可选中拷贝（Ctrl+C）。
确定后由调用方取 `selected_rows()` 建丛书（本对话框不落盘、不问名）。

仅展示与建单：不参与合并/分册/校验（见 docs/UI设计.md）。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                               QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from cbeta_publish.collection import id_import

_STATUS_COLOR = {
    id_import.STATUS_INVALID: QColor("#c62828"),
    id_import.STATUS_DUP: QColor("#ef6c00"),
    id_import.STATUS_UNKNOWN: QColor("#757575"),
}

_COLS = ["选", "序号", "状态", "原始", "规范ID", "注释(可编辑)", "目录书名"]
_C_SEL, _C_NO, _C_ST, _C_RAW, _C_ID, _C_NOTE, _C_TITLE = range(7)

#: 「加入丛书」的对话框返回码（`创建丛书` 用 QDialog.Accepted）
ADD_RESULT = 2

#: 可选中拷贝的表格（Ctrl+C 复制所选单元格为制表符文本）
class _CopyTable(QTableWidget):
    def keyPressEvent(self, ev):
        if ev.matches(QKeySequence.Copy):
            self._copy_selection()
            return
        super().keyPressEvent(ev)

    def _copy_selection(self):
        ranges = self.selectedRanges()
        if not ranges:
            return
        r0 = ranges[0]
        lines = []
        for row in range(r0.topRow(), r0.bottomRow() + 1):
            cells = []
            for col in range(r0.leftColumn(), r0.rightColumn() + 1):
                it = self.item(row, col)
                cells.append(it.text() if it is not None else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))


def _sel_flags(editable=False):
    f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
    return (f | Qt.ItemIsEditable) if editable else f


class ImportIdsDialog(QDialog):
    """批量 ID 导入对话框。

    work_exists: 判定 catalog 命中的可调用（未收录标注）；None=不校验。
    title_fn: work_id → 目录书名（展示列）；None=空。
    """

    def __init__(self, parent=None, work_exists=None, title_fn=None):
        super().__init__(parent)
        self.setWindowTitle("导入 ID 建丛书")
        self.setMinimumWidth(760)
        self._work_exists = work_exists
        self._title_fn = title_fn

        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "粘贴多行（行首 ID，其后为注释）、或从文件/网页载入后点「解析/预览」。"
            "ID 支持 T0349、T01n0001、T25n1509、T0349:2-3、T11n0310_050 等。"))

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "T0349 彌勒菩薩所問本願經\nT0001 長阿含經\n# 以 # 或 // 开头的行忽略")
        self.editor.setMinimumHeight(120)
        root.addWidget(self.editor)

        src = QHBoxLayout()
        self.btn_file = QPushButton("从文件载入…")
        self.btn_web = QPushButton("从网页抓取…")
        self.btn_parse = QPushButton("解析/预览")
        src.addWidget(self.btn_file)
        src.addWidget(self.btn_web)
        src.addStretch()
        src.addWidget(self.btn_parse)
        root.addLayout(src)

        self.table = _CopyTable(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setColumnWidth(_C_SEL, 36)
        self.table.setColumnWidth(_C_NO, 44)
        self.table.setColumnWidth(_C_ST, 56)      # 状态窄列
        # 注释/目录书名两列伸展占满窗口余宽，其余按内容，避免出现横向滚动条
        hh = self.table.horizontalHeader()
        for _c in (_C_SEL, _C_NO, _C_ST):
            hh.setSectionResizeMode(_c, QHeaderView.Fixed)
        for _c in (_C_RAW, _C_ID):
            hh.setSectionResizeMode(_c, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(_C_NOTE, QHeaderView.Stretch)
        hh.setSectionResizeMode(_C_TITLE, QHeaderView.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.btn_all = QPushButton("全选")
        self.btn_none = QPushButton("全不选")
        self.btn_del = QPushButton("删除选中行")
        self.btn_del_invalid = QPushButton("删除无效")
        row.addWidget(self.btn_all)
        row.addWidget(self.btn_none)
        row.addWidget(self.btn_del)
        row.addWidget(self.btn_del_invalid)
        row.addStretch()
        self.lbl_count = QLabel("已选 0 部")
        row.addWidget(self.lbl_count)             # 靠窗口右边对齐
        root.addLayout(row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("创建丛书")
        self.btn_add = self.buttons.addButton("加入丛书", QDialogButtonBox.ActionRole)
        self.btn_add.setToolTip("把勾选行加入当前丛书（按条目去重，同部不同卷各自成条）")
        root.addWidget(self.buttons)

        self.btn_file.clicked.connect(self._load_file)
        self.btn_web.clicked.connect(self._fetch_web)
        self.btn_parse.clicked.connect(self._parse)
        self.btn_all.clicked.connect(lambda: self._check_all(True))
        self.btn_none.clicked.connect(lambda: self._check_all(False))
        self.btn_del.clicked.connect(self._delete_checked)
        self.btn_del_invalid.clicked.connect(self._delete_invalid)
        self.table.itemChanged.connect(lambda *_: self._update_count())
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.btn_add.clicked.connect(self._accept_add)

    def _accept_add(self):
        if not self.selected_rows():
            QMessageBox.warning(self, "未选择", "请先勾选要加入的书籍。")
            return
        self.done(ADD_RESULT)

    # ---------- 来源 ----------
    def _set_text(self, text):
        self.editor.setPlainText(text or "")

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "载入 ID 文件", "", "文本/CSV (*.txt *.csv);;所有文件 (*)")
        if not path:
            return
        try:
            data = open(path, "rb").read()
        except OSError as e:
            QMessageBox.warning(self, "读取失败", str(e))
            return
        text = ""
        for enc in ("utf-8-sig", "gbk"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if not text:
            text = data.decode("utf-8", errors="replace")
        self._set_text(text)
        self._parse()

    def _fetch_web(self):
        dlg = QInputDialog(self)
        dlg.setWindowTitle("从网页抓取")
        dlg.setLabelText("网页 URL（http/https）：")
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setMinimumWidth(500)
        dlg.resize(500, dlg.sizeHint().height())
        if dlg.exec() != QDialog.Accepted:
            return
        url = dlg.textValue().strip()
        if not url:
            return
        text = id_import.fetch_text(url)
        if not text:
            QMessageBox.warning(self, "抓取失败", "未能获取网页内容（仅支持 http/https）。")
            return
        self._set_text(id_import.html_to_text(text))
        self._parse()

    # ---------- 解析/预览 ----------
    def _parse(self):
        rows = id_import.parse_id_lines(self.editor.toPlainText())
        classified = id_import.classify(rows, work_exists=self._work_exists)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for i, r in enumerate(classified, 1):
            self._add_row(i, r)
        self.table.blockSignals(False)
        self._update_count()
        if not classified:
            self.editor.setFocus()

    def _add_row(self, idx, r):
        row = self.table.rowCount()
        self.table.insertRow(row)
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        chk.setCheckState(Qt.Checked if r.status in (
            id_import.STATUS_OK, id_import.STATUS_UNKNOWN) else Qt.Unchecked)
        self.table.setItem(row, _C_SEL, chk)
        for col, val in ((_C_NO, str(idx)), (_C_RAW, r.raw)):
            it = QTableWidgetItem(val)
            it.setFlags(_sel_flags())
            self.table.setItem(row, col, it)
        st = QTableWidgetItem(r.status)
        st.setFlags(_sel_flags())
        col = _STATUS_COLOR.get(r.status)
        if col is not None:
            st.setForeground(col)
        self.table.setItem(row, _C_ST, st)
        wid_txt = f"{r.work_id}:{r.juan}" if (r.work_id and r.juan) else r.work_id
        wid = QTableWidgetItem(wid_txt)
        wid.setFlags(_sel_flags())
        wid.setData(Qt.UserRole, r.work_id)       # 纯 work id（供建单）
        self.table.setItem(row, _C_ID, wid)
        self.table.setItem(row, _C_NOTE, QTableWidgetItem(r.note))
        title = ""
        if r.work_id and self._title_fn:
            try:
                title = self._title_fn(r.work_id) or ""
            except Exception:
                title = ""
        tit = QTableWidgetItem(title)
        tit.setFlags(_sel_flags())
        self.table.setItem(row, _C_TITLE, tit)

    # ---------- 行操作 ----------
    def _check_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            it = self.table.item(row, _C_SEL)
            if it is not None:
                it.setCheckState(state)
        self.table.blockSignals(False)
        self._update_count()

    def _delete_checked(self):
        self._delete_where(
            lambda row: (self.table.item(row, _C_SEL) is not None
                         and self.table.item(row, _C_SEL).checkState() == Qt.Checked))

    def _delete_invalid(self):
        """删除状态为「无效」的行。"""
        self._delete_where(
            lambda row: (self.table.item(row, _C_ST) is not None
                         and self.table.item(row, _C_ST).text() == id_import.STATUS_INVALID))

    def _delete_where(self, pred):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount() - 1, -1, -1):
            if pred(row):
                self.table.removeRow(row)
        self._renumber()
        self.table.blockSignals(False)
        self._update_count()

    def _renumber(self):
        """重排序号列为 1..N。"""
        for row in range(self.table.rowCount()):
            it = self.table.item(row, _C_NO)
            if it is not None:
                it.setText(str(row + 1))

    def _update_count(self):
        """右侧计数：勾选且规范 ID 非空的条目数（同部不同卷各计一条）。"""
        n = 0
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, _C_SEL)
            if chk is None or chk.checkState() != Qt.Checked:
                continue
            wid = self.table.item(row, _C_ID)
            if wid is not None and wid.data(Qt.UserRole):
                n += 1
        self.lbl_count.setText(f"已选 {n} 部")

    # ---------- 结果 ----------
    def selected_rows(self):
        """勾选且规范 ID 非空的行 → [{work_id, note, juan}]；身份=(work_id, 卷)，按行序去重。"""
        out = []
        seen = set()
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, _C_SEL)
            if chk is None or chk.checkState() != Qt.Checked:
                continue
            wid_item = self.table.item(row, _C_ID)
            wid = wid_item.data(Qt.UserRole) if wid_item is not None else ""
            if not wid:
                continue
            raw_item = self.table.item(row, _C_RAW)
            raw = raw_item.text() if raw_item is not None else ""
            juan = id_import.token_juan(raw)
            key = (wid, juan)
            if key in seen:
                continue
            seen.add(key)
            note_item = self.table.item(row, _C_NOTE)
            out.append({"work_id": wid,
                        "note": note_item.text().strip() if note_item else "",
                        "juan": juan})
        return out
