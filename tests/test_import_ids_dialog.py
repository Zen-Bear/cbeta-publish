# -*- coding: utf-8 -*-
"""「导入 ID 建丛书」：解析预览、勾选、注释编辑、建单集成与模型剪枝。"""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.collection.collection_model import normalize_collection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


class ImportIdsDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def _dlg(self):
        from cbeta_publish.gui.import_ids_dialog import ImportIdsDialog
        return ImportIdsDialog(None, work_exists=lambda w: w == "T0001",
                               title_fn=lambda w: f"名-{w}")

    def test_parse_status_and_title(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T0001 甲\nT0999 乙\nbad 丙\nT0001 重复")
            dlg._parse()
            st = [dlg.table.item(r, 2).text() for r in range(dlg.table.rowCount())]
            self.assertEqual(st, ["有效", "未收录", "无效", "重复"])
            self.assertEqual(dlg.table.item(0, 6).text(), "名-T0001")
        finally:
            dlg.close()

    def test_selected_defaults_and_note(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T0001 甲\nT0999 乙\nbad 丙\nT0001 重复")
            dlg._parse()
            rows = dlg.selected_rows()
            # 默认只勾有效/未收录；无效/重复不勾
            self.assertEqual([r["work_id"] for r in rows], ["T0001", "T0999"])
            self.assertEqual(rows[0]["note"], "甲")
        finally:
            dlg.close()

    def test_note_edit_and_juan(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T0001:2-3 甲")
            dlg._parse()
            dlg.table.item(0, 5).setText("改后")
            rows = dlg.selected_rows()
            self.assertEqual(rows[0]["note"], "改后")
            self.assertEqual(rows[0]["juan"], "2-3")
            self.assertEqual(dlg.table.item(0, 4).text(), "T0001:2-3")
        finally:
            dlg.close()

    def test_check_all_and_delete(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T0001 甲\nT0999 乙")
            dlg._parse()
            dlg._check_all(False)
            self.assertEqual(dlg.selected_rows(), [])
            dlg._check_all(True)
            self.assertEqual(len(dlg.selected_rows()), 2)
            dlg._delete_checked()
            self.assertEqual(dlg.table.rowCount(), 0)
        finally:
            dlg.close()

    def test_invalid_rows_not_selectable_by_id(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("bad")
            dlg._parse()
            dlg._check_all(True)   # 即便勾上，无 work_id 也不入选
            self.assertEqual(dlg.selected_rows(), [])
        finally:
            dlg.close()

    def test_delete_invalid(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T0001 甲\nbad 丙\nT0001 重复\nT0999 乙")
            dlg._parse()
            dlg._delete_invalid()
            st = [dlg.table.item(r, 2).text() for r in range(dlg.table.rowCount())]
            self.assertNotIn("无效", st)
            self.assertEqual(len(st), 3)
            # 删除后序号重排
            self.assertEqual([dlg.table.item(r, 1).text()
                              for r in range(dlg.table.rowCount())], ["1", "2", "3"])
        finally:
            dlg.close()

    def test_count_label_and_same_work_diff_juan(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T0220:1 甲\nT0220:2 乙\nT0999 丙")
            dlg._parse()
            st = [dlg.table.item(r, 2).text() for r in range(dlg.table.rowCount())]
            self.assertEqual(st, ["未收录", "未收录", "未收录"])   # 同部不同卷不算重复
            self.assertEqual(dlg.lbl_count.text(), "已选 3 部")
            rows = dlg.selected_rows()
            self.assertEqual([(r["work_id"], r["juan"]) for r in rows],
                             [("T0220", "1"), ("T0220", "2"), ("T0999", "")])
        finally:
            dlg.close()

    def test_buttons_create_and_add(self):
        from PySide6.QtWidgets import QDialogButtonBox
        from cbeta_publish.gui.import_ids_dialog import ADD_RESULT
        dlg = self._dlg()
        try:
            self.assertEqual(dlg.buttons.button(QDialogButtonBox.Ok).text(), "创建丛书")
            self.assertTrue(dlg.btn_add.text().startswith("加入丛书"))
            # 未勾选点加入 → 警告且不关闭
            with mock.patch("cbeta_publish.gui.import_ids_dialog.QMessageBox.warning") as w:
                dlg._accept_add()
                w.assert_called_once()
                self.assertNotEqual(dlg.result(), ADD_RESULT)
            # 有勾选 → 返回加入码
            dlg.editor.setPlainText("T0001 甲")
            dlg._parse()
            dlg._accept_add()
            self.assertEqual(dlg.result(), ADD_RESULT)
        finally:
            dlg.close()

    def test_juan_from_basename_token(self):
        dlg = self._dlg()
        try:
            dlg.editor.setPlainText("T11n0310_050 卷五十")
            dlg._parse()
            rows = dlg.selected_rows()
            self.assertEqual(rows[0]["work_id"], "T0310")
            self.assertEqual(rows[0]["juan"], "50")
        finally:
            dlg.close()


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    col = tmp / "collections" / "custom"
    col.mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    from cbeta_publish.gui.main_window import MainWindow
    return MainWindow(cfg), tmp


class ImportIdsMainWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_creates_collection_with_notes(self):
        win = self.win

        class _Stub:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return 1   # QDialog.Accepted

            def selected_rows(self):
                return [{"work_id": "T0001", "note": "甲", "juan": ""},
                        {"work_id": "T0002", "note": "", "juan": "2-3"}]

        with mock.patch("cbeta_publish.gui.import_ids_dialog.ImportIdsDialog", _Stub), \
                mock.patch.object(win, "_ask_name_category",
                                  return_value=("导入测试丛书", "custom")):
            win._import_ids_dialog()
        found = next((d for _p, d in win._collections
                      if d.get("name") == "导入测试丛书"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["work_ids"], ["T0001", "T0002:2-3"])   # 卷并入条目键
        self.assertEqual(found["work_notes"], {"T0001": "甲"})

    def test_creates_collection_multi_volume_entries(self):
        # 同部多卷 → 各自成条
        win = self.win

        class _Stub:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return 1

            def selected_rows(self):
                return [{"work_id": "T0220", "note": "", "juan": "479"},
                        {"work_id": "T0220", "note": "", "juan": "523"}]

        with mock.patch("cbeta_publish.gui.import_ids_dialog.ImportIdsDialog", _Stub), \
                mock.patch.object(win, "_ask_name_category",
                                  return_value=("多卷丛书", "custom")):
            win._import_ids_dialog()
        found = next((d for _p, d in win._collections
                      if d.get("name") == "多卷丛书"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["work_ids"], ["T0220:479", "T0220:523"])

    def test_entry_book_title(self):
        # 合并用标题：同右栏行 `work-id 书名（卷…）`
        win = self.win
        t = win._entry_book_title("T0220:479")
        self.assertIn("T0220", t)
        self.assertIn("479", t)
        self.assertIn("卷", t)
        t2 = win._entry_book_title("T0001")
        self.assertNotIn("卷", t2)

    def test_add_ids_to_current_coll_dedupes_entries(self):
        # 按条目键去重：同部不同卷各自加入；已在条目跳过；注释补入
        win = self.win
        target = win._append_collection({"id": "t-add", "name": "加书测",
                                         "category": "custom", "tags": [],
                                         "work_ids": ["T0001"], "works": [{"id": "T0001"}]})
        rows = [{"work_id": "T0001", "note": "", "juan": ""},
                {"work_id": "T0220", "note": "", "juan": "1"},
                {"work_id": "T0220", "note": "", "juan": "2"},
                {"work_id": "T0002", "note": "乙", "juan": ""},
                {"work_id": "T0220", "note": "", "juan": "1"}]
        win._add_ids_to_coll(rows)
        d = win._coll_dict(str(target))
        self.assertEqual(d["work_ids"], ["T0001", "T0220:1", "T0220:2", "T0002"])
        self.assertEqual(d["work_notes"], {"T0002": "乙"})
        self.assertIn("已加入 3 部", win.detail.text())
        win._add_ids_to_coll([{"work_id": "T0001", "note": "", "juan": ""}])
        self.assertIn("已在当前丛书中", win.detail.text())


class WorkNotesModelTest(unittest.TestCase):
    def test_normalize_prunes_and_canonicalizes(self):
        d = {"work_ids": ["TXA001", "T0001", "T0001:1"],
             "work_notes": {"TXA001": "甲", "T0001": "  ", "ZZ9": "脏"}}
        out = normalize_collection(d)
        self.assertEqual(out["work_ids"], ["TXa001", "T0001", "T0001:1"])
        self.assertEqual(out["work_notes"], {"TXa001": "甲"})   # 空注/不在书单的剔除
        self.assertNotIn("work_juan", out)                     # 卷范围并入条目键


if __name__ == "__main__":
    unittest.main()
