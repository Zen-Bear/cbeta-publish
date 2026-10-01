# -*- coding: utf-8 -*-
"""按目录（部类）分册：catalog_path 路径/命名/序 + _group_works catalog 模式 + 合并弹框。"""
import json
import copy
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cbeta_publish.catalog import catalog_path as cp  # noqa: E402
from cbeta_publish.catalog.bulei_parser import parse_bulei  # noqa: E402
from cbeta_publish.gui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
_app = None


def _ensure_app():
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication([])
    return _app


def _make_window():
    _ensure_app()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "collections" / "custom").mkdir(parents=True)
    (tmp / "collections" / "categories.json").write_text("[]", encoding="utf-8")
    (tmp / "collections" / "tags.json").write_text('{"tags": []}', encoding="utf-8")
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["mulu_dir"] = str(ROOT / "mulu")           # 用真实目录树
    cfg["collections_dir"] = str(tmp / "collections")
    cfg["update_interval"] = "manual"
    cfg["_config_path"] = str(tmp / "app.json")
    return MainWindow(cfg), tmp


class CatalogPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roots = parse_bulei(ROOT / "mulu" / "bulei.txt")
        cls.bm = cp.build_bulei_map(cls.roots)

    def test_depth_and_naming(self):
        r1 = cp.resolve("T0002", "bulei", 1, bulei_map=self.bm)
        r2 = cp.resolve("T0002", "bulei", 2, bulei_map=self.bm)
        self.assertEqual(r1["label"], "01 阿含部類")
        self.assertEqual(r2["label"], "01 阿含部類 / 長阿含經")
        self.assertEqual(r2["stem"], "01 阿含部類_長阿含經")   # 下划线连接
        self.assertFalse(r2["unclassified"])
        # 全路径不受截断影响（封面显示用）：截断段是其前缀，末段是叶标题
        self.assertEqual(r1["full_segments"][:len(r1["segments"])],
                         r1["segments"])
        self.assertGreaterEqual(len(r1["full_segments"]), len(r1["segments"]))
        self.assertIn("七佛經", r1["full_segments"][-1])
        self.assertEqual(r2["full_segments"], r1["full_segments"])

    def test_order_is_tree_order(self):
        # T0001（長阿含經）在 T0026（中阿含經）之前
        a = cp.resolve("T0001", "bulei", 2, bulei_map=self.bm)["order"]
        b = cp.resolve("T0026", "bulei", 2, bulei_map=self.bm)["order"]
        self.assertLess(a, b)

    def test_unclassified(self):
        r = cp.resolve("ZZ9999", "bulei", 2, bulei_map=self.bm)
        self.assertEqual(r["label"], "未歸類")
        self.assertTrue(r["unclassified"])
        self.assertEqual(r["order"], (10 ** 6,))

    def test_clean_seg_strips_ids(self):
        self.assertEqual(cp._clean_bulei_seg("T0001-25 長阿含經 etc. T01"), "長阿含經")
        self.assertEqual(cp._clean_bulei_seg("01 阿含部類 T01-02,25,33 etc."), "01 阿含部類")
        # 全角 ／ 保留；T/K/X/G 经号与 etc. 去掉
        self.assertEqual(cp._clean_bulei_seg("T30a, K41 中觀部／疏 T42,85, X46, G151"),
                         "中觀部／疏")
        self.assertEqual(cp._clean_bulei_seg("T1564-67, K1482 中論 etc.／疏 T42"),
                         "中論／疏")
        # 经号后的裸卷号列表（X46,54 / T42,85）也要去掉
        self.assertEqual(cp._clean_bulei_seg("T45, X46,54 三論宗"), "三論宗")
        # 续号可带字母后缀（T11-12a,26a,37,40b）：否则残留孤立 a/b 进文件名
        self.assertEqual(cp._clean_bulei_seg("06 寶積部類 T11-12a,26a,37,40b,85, X10,19"),
                         "06 寶積部類")
        self.assertEqual(cp._clean_bulei_seg("T0360-73 淨土經 T11-12／論 T26a／疏 T37,40b,85"),
                         "淨土經／論／疏")
        # 作者等正文（含 】）保留，不被截断
        self.assertEqual(cp._clean_bulei_seg("T2034 二諦義 (3卷)【隋 吉藏撰】"),
                         "二諦義 (3卷)【隋 吉藏撰】")


class CatalogGroupingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_group_works_catalog(self):
        self.win.config.setdefault("merge", {})["mode"] = "catalog"
        groups = self.win._group_works(
            {}, ["a", "b"], ["t1", "t2"], ["T0002", "T0001"])
        self.assertEqual(len(groups), 1)                       # 同属長阿含經
        self.assertEqual(groups[0]["label"], "01 阿含部類 / 長阿含經")
        self.assertEqual(groups[0]["stem"], "01 阿含部類_長阿含經")

    def test_group_works_catalog_depth1(self):
        self.win.config.setdefault("merge", {})["mode"] = "catalog"
        groups = self.win._group_works({}, ["a", "b"], ["t1", "t2"],
                                        ["T0001", "T0026"], mode="catalog", depth=1)
        self.assertEqual(groups[0]["label"], "01 阿含部類")
        self.assertEqual(len(groups), 1)

    def test_merge_preview(self):
        rows = self.win._merge_preview(["T0001", "T0026"], "catalog", 2)
        self.assertTrue(any("01 阿含部類" in r[0] for r in rows))
        self.assertTrue(all(r[1] >= 1 for r in rows))


class MergeBasenameTest(unittest.TestCase):
    """分册文件名模板：默认 {coll}.{nn}.{seg}；旧名风/计数风展开正确。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _basename(self, template, d, g, idx):
        win = self.win
        old = (win.config.get("merge", {}) or {}).get("name_template")
        win.config.setdefault("merge", {})["name_template"] = template
        try:
            return win._merge_basename(d, g, idx)
        finally:
            if old is None:
                win.config["merge"].pop("name_template", None)
            else:
                win.config["merge"]["name_template"] = old

    def _g(self, **kw):
        g = {"label": "太虛大師全書 / 01 編纂說明",
             "stem": "太虛大師全書_01 編纂說明",
             "segments": ["太虛大師全書", "01 編纂說明"],
             "works": ["T0001", "T0002"]}
        g.update(kw)
        return g

    def test_default_is_coll_nn_seg(self):
        d = {"name": "太虛大師全書"}
        self.assertEqual(self._basename("{stem}", d, self._g(), 1),
                         "太虛大師全書_01 編纂說明")
        self.assertEqual(self._basename("", d, self._g(), 1),
                         "太虛大師全書.01.01 編纂說明")  # 空模板回退新缺省

    def test_old_style_coll_seg(self):
        d = {"name": "太虛大師全書"}
        self.assertEqual(self._basename("{coll} {seg}", d, self._g(), 1),
                         "太虛大師全書 01 編纂說明")

    def test_count_style(self):
        d = {"name": "太虛大師全書"}
        g = self._g(label="太虛大師全書 / 法藏", stem="太虛大師全書_法藏",
                    segments=["太虛大師全書", "法藏"],
                    works=["T%04d" % i for i in range(12)])
        self.assertEqual(self._basename("{coll} {nn} {seg}.{count}册", d, g, 2),
                         "太虛大師全書 02 法藏.12册")

    def test_seg_n_vars(self):
        # 分段变量：{seg1}…{segN} 取第 N 段，超出段数置空；
        # {seg1} 去掉首段前导数字（数字归 {seg0}）
        d = {"name": "太虛大師全書"}
        g = self._g(segments=["06 寶積部類", "01 編纂說明"])
        self.assertEqual(self._basename("{seg1}-{seg2}", d, g, 1),
                         "寶積部類-01 編纂說明")
        self.assertEqual(self._basename("{seg1}[{seg9}]", d, g, 1),
                         "寶積部類[]")
        self.assertEqual(self._basename("{seg}", d, self._g(), 1),
                         "01 編纂說明")

    def test_seg0_is_first_seg_number(self):
        # {seg0}＝首段前导数字；首段无数字/无段则空
        d = {"name": "太虛大師全書"}
        g = self._g(segments=["06 寶積部類", "淨土經／論／疏", "阿彌陀經"])
        self.assertEqual(self._basename("{seg0}", d, g, 1), "06")
        self.assertEqual(self._basename("{seg0}-{seg1}-{seg3}", d, g, 1),
                         "06-寶積部類-阿彌陀經")
        self.assertEqual(self._basename("{seg0}-{seg1}", d, self._g(
            label="淨土組", stem="淨土組", segments=["淨土組"], works=[]), 1),
            "-淨土組")  # 无数字置空；纯空模板回退 stem
        self.assertEqual(self._basename("{seg0}", d, self._g(
            label="淨土組", stem="淨土組", segments=["淨土組"], works=[]), 1),
            "淨土組")
        self.assertEqual(self._basename("{seg0}", d, self._g(
            label="X", stem="X", segments=[], works=[]), 1), "X")

    def test_label_sanitized(self):
        d = {"name": "X"}
        self.assertEqual(self._basename("{label}", d, self._g(), 1),
                         "太虛大師全書 _ 01 編纂說明")  # / → _

    def test_n_adaptive_and_n_plain(self):
        # {n} 永不补零；{nn} 自适应（宽度＝总文件数位数，拿不到总数回退两位）
        win = self.win
        d = {"name": "C"}
        g = self._g(segments=["S"], works=[])
        self.assertEqual(win._merge_basename(d, g, 3, template="{n}", total=8), "3")
        self.assertEqual(win._merge_basename(d, g, 3, template="{nn}", total=8), "3")
        self.assertEqual(win._merge_basename(d, g, 3, template="{nn}", total=12), "03")
        self.assertEqual(win._merge_basename(d, g, 7, template="{nn}", total=105), "007")
        self.assertEqual(win._merge_basename(d, g, 3, template="{n}-{nn}", total=12),
                         "3-03")
        self.assertEqual(win._merge_basename(d, g, 3, template="{nn}"), "03")

    def test_basename_template_override(self):
        # _merge_basename(template=...) 覆盖配置模板；空串回退配置
        win = self.win
        d = {"name": "太虛大師全書"}
        g = self._g(segments=["06 寶積部類", "01 編纂說明"])
        self.assertEqual(win._merge_basename(d, g, 1, template="{seg0}"), "06")
        self.assertEqual(win._merge_basename(d, g, 1, template=""),
                         win._merge_basename(d, g, 1))
        rows = win._merge_preview(["T0001", "T0026"], "catalog", 2,
                                  coll="测丛书", name_template="{seg}")
        self.assertTrue(rows)
        self.assertTrue(all(not r[2].endswith((".pdf", ".epub")) for r in rows), rows)
        self.assertTrue(any(r[2].startswith("長阿含經") for r in rows), rows)

    def test_none_mode_uses_template(self):
        # 不分册同样走模板（无序号；{coll}/{count} 可用；缺省即丛书名本身）
        win = self.win
        d = {"name": "C"}
        g = {"label": None, "stem": None, "segments": [],
             "works": ["T0001", "T0002"]}
        self.assertEqual(
            win._merge_basename(d, g, None, template="{coll}.{nn}.{seg}"), "C")
        self.assertEqual(
            win._merge_basename(d, g, None, template="{coll}.{count}"), "C.2")
        self.assertEqual(
            win._merge_basename(d, g, None, template="{coll}"), "C")
        rows = win._merge_preview(["T0001", "T0002"], "none", 2,
                                  coll="C", name_template="{coll}.{count}")
        self.assertEqual([(r[0], r[1], r[2]) for r in rows],
                         [("（不分册）", 2, "C.2")])

    def test_preview_follows_template(self):
        win = self.win
        old = (win.config.get("merge", {}) or {}).get("name_template")
        win.config.setdefault("merge", {})["name_template"] = "{coll} {nn} {seg}"
        try:
            rows = win._merge_preview(["T0001", "T0026"], "catalog", 2, coll="测丛书")
        finally:
            if old is None:
                win.config["merge"].pop("name_template", None)
            else:
                win.config["merge"]["name_template"] = old
        self.assertTrue(any(r[2].startswith("测丛书 1 ") for r in rows), rows)  # 2 组自适应不补零

    def test_merge_mode_helpers(self):
        self.win.config.setdefault("merge", {})["mode"] = "ask"
        self.assertEqual(self.win._merge_mode(), "ask")
        # 旧配置：无 mode、by_volume=true → volume
        self.win.config["merge"] = {"by_volume": True}
        self.assertEqual(self.win._merge_mode(), "volume")
        self.win.config["merge"] = {"mode": "catalog", "depth": 9}
        self.assertEqual(self.win._merge_depth(), 5)           # clamp 1..5

    def test_cover_group_label_display(self):
        # 封面副标题显示形态：默认去序号、每层一行；可配深度/一行/分隔符/序号
        win = self.win
        old_cover = copy.deepcopy(win.config.get("cover", {}))
        g = {"label": "06 寶積部類 / 淨土經／論／疏 / 阿彌陀經",
             "stem": "s", "segments": ["06 寶積部類", "淨土經／論／疏"],
             "full_segments": ["06 寶積部類", "淨土經／論／疏", "阿彌陀經"],
             "works": []}
        try:
            win.config.setdefault("cover", {})["bulei"] = {
                "depth": 0, "layout": "lines", "sep": "·", "show_num": False}
            # depth=0 跟随分册深度＝截断处（2 段），不探全路径
            self.assertEqual(win._cover_group_label(g),
                             "寶積部類 / 淨土經／論／疏")
            win.config["cover"]["bulei"] = {
                "depth": 2, "layout": "one", "sep": "·", "show_num": False}
            self.assertEqual(win._cover_group_label(g),
                             "寶積部類·淨土經／論／疏")
            win.config["cover"]["bulei"] = {
                "depth": 0, "layout": "lines", "sep": "·", "show_num": True}
            self.assertEqual(win._cover_group_label(g),
                             "06 寶積部類 / 淨土經／論／疏")
            # 显式 depth=3 探深（超出截断的段只反映首部）
            win.config["cover"]["bulei"] = {
                "depth": 3, "layout": "lines", "sep": "·", "show_num": False}
            self.assertEqual(win._cover_group_label(g),
                             "寶積部類 / 淨土經／論／疏 / 阿彌陀經")
            # 总开关关 → 空；书名模式 all → 部类＋书名逐个拼接
            win.config["cover"]["bulei"] = {"enabled": False, "titles": "all"}
            self.assertEqual(win._cover_group_label(g, ["T0001 長阿含經"]), "")
            win.config["cover"]["bulei"] = {
                "depth": 0, "layout": "lines", "sep": "·", "show_num": False,
                "titles": "all"}
            self.assertEqual(
                win._cover_group_label(g, ["T0366 佛說阿彌陀經", "T0367 稱讚經"]),
                "寶積部類 / 淨土經／論／疏 / T0366 佛說阿彌陀經 / T0367 稱讚經")
            # titles=none（默认）不拼书名；｜ 转全角防切分
            win.config["cover"]["bulei"] = {"titles": "none"}
            self.assertEqual(win._cover_group_label(g, ["X"]),
                             "寶積部類 / 淨土經／論／疏")
            win.config["cover"]["bulei"] = {"titles": "all"}
            self.assertEqual(win._cover_group_label(g, ["A｜B"]),
                             "寶積部類 / 淨土經／論／疏 / A／B")
            # 回归：depth=0 不得输出首部叶子书名（本緣部類/譬喻經组）
            g2 = {"label": "本緣部類 / 譬喻經",
                  "stem": "s", "segments": ["本緣部類", "譬喻經"],
                  "full_segments": ["本緣部類", "譬喻經",
                                    "醫喻經 (1卷)【宋 施護譯】"],
                  "works": []}
            win.config["cover"]["bulei"] = {"depth": 0, "titles": "none"}
            self.assertEqual(win._cover_group_label(g2),
                             "本緣部類 / 譬喻經")
            # 无段回退 segments；全空回空串（封面不画副标题）
            self.assertEqual(win._cover_group_label({"segments": []}), "")
        finally:
            win.config["cover"] = old_cover


    def test_merge_ask_dialog_reject_aborts(self):
        # 「合并时选择」→ 弹框；取消则中止（并覆盖 QDialog.Accepted 判定）
        import cbeta_publish.gui.merge_dialog as md
        win = self.win
        col = Path(win.config["collections_dir"]) / "custom" / "ask.json"
        col.write_text(json.dumps({"id": "ask", "name": "ask", "category": "custom",
                                   "tags": [], "work_ids": ["T0001"]},
                                  ensure_ascii=False), encoding="utf-8")
        win._load_collections()
        for i in range(win.coll_combo.count()):
            if str(win.coll_combo.itemData(i)).endswith("ask.json"):
                win.coll_combo.setCurrentIndex(i)
                break
        win.config.setdefault("merge", {})["mode"] = "ask"

        class _D:
            def __init__(self, *a, **k):
                pass

            def exec(self):
                return 0                     # != QDialog.Accepted

            def chosen(self):
                return ("none", 2)

            def _refresh(self):
                pass

        real = md.MergeDialog
        md.MergeDialog = _D
        try:
            win._merge()
        finally:
            md.MergeDialog = real
            col.unlink(missing_ok=True)
        self.assertIn("未选择分册模式", win.detail.text())


class MergeDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _ensure_app()

    def test_chosen_and_preview(self):
        from cbeta_publish.gui.merge_dialog import MergeDialog
        rows = [("01 阿含部類 / 長阿含經", 2, "01 阿含部類_長阿含經")]
        dlg = MergeDialog(None, default_mode="catalog", default_depth=2,
                          preview=lambda m, d: rows)
        try:
            self.assertTrue(dlg.rb_catalog.isChecked())
            self.assertEqual(dlg.chosen(), ("catalog", 2))
            # 清单只显示文件名（无后缀）；例子行显示原文全文＋部数
            self.assertEqual(dlg.lst.item(0).text(),
                             "01 阿含部類_長阿含經")
            self.assertEqual(dlg.lbl_example.text(),
                             "例：01 阿含部類 / 長阿含經（2 部）")
            dlg.rb_none.setChecked(True)
            self.assertFalse(dlg.sp_depth.isEnabled())
            self.assertEqual(dlg.chosen(), ("none", 2))
            # 不分册：无例子行，清单只显示文件名（随模板实时展开）
            self.assertEqual(dlg.lbl_example.text(), "")
            self.assertEqual(dlg.lst.count(), 1)
            self.assertEqual(dlg.lst.item(0).text(),
                             "01 阿含部類_長阿含經")
        finally:
            dlg.close()

    def test_template_input_and_example_follows_depth(self):
        # 模板输入框在深度右侧；例子随深度动态变化；模板改动实时进预览
        from cbeta_publish.gui.merge_dialog import MergeDialog
        seen = []

        def preview(m, d):
            seen.append((m, d))
            if d >= 2:
                return [("A / B", 3, "A_B.pdf"), ("A / C", 1, "A_C.pdf")]
            return [("A", 4, "A.pdf")]

        dlg = MergeDialog(None, default_mode="catalog", default_depth=2,
                          default_template="{coll}.{nn}.{seg}",
                          preview=preview)
        try:
            self.assertEqual(dlg.template(), "{coll}.{nn}.{seg}")
            # 深度行：spin 右边是模板输入
            drow = dlg.sp_depth.parent()
            texts = [drow.layout().itemAt(i).widget()
                     for i in range(drow.layout().count())]
            kinds = [type(w).__name__ for w in texts if w is not None]
            self.assertEqual(kinds[:3], ["QLabel", "QSpinBox", "QLabel"])
            self.assertIn("QLineEdit", kinds)
            self.assertEqual(dlg.lbl_example.text(), "例：A / B（3 部）")
            dlg.sp_depth.setValue(1)
            self.assertEqual(dlg.lbl_example.text(), "例：A（4 部）")
            self.assertEqual(dlg.lst.item(0).text(), "A.pdf")
            self.assertEqual(seen[-1], ("catalog", 1))
            dlg.ed_template.setText("{seg0}")
            self.assertEqual(dlg.template(), "{seg0}")
        finally:
            dlg.close()

    def test_none_preview_follows_template_live(self):
        # 不分册：模板输入即实时刷新文件名（无例子行）
        from cbeta_publish.gui.merge_dialog import MergeDialog

        def preview(m, d):
            assert m == "none"
            return [("（不分册）", 2, "NAME")]

        dlg = MergeDialog(None, default_mode="none", default_depth=2,
                          preview=preview)
        try:
            self.assertEqual(dlg.lbl_example.text(), "")
            self.assertEqual(dlg.lst.count(), 1)
            self.assertEqual(dlg.lst.item(0).text(), "NAME")
            # 模板改动即重算（不分册也一样）
            calls = []
            dlg._preview = lambda m, d: calls.append((m, d)) or [
                ("（不分册）", 2, "N2")]
            dlg.ed_template.setText("x")
            self.assertTrue(calls and calls[-1][0] == "none", calls)
            self.assertEqual(dlg.lst.item(0).text(), "N2")
        finally:
            dlg.close()


class BlankSaveDupTest(unittest.TestCase):
    """空白丛书保存：重名拦截（与新建/另存一致）；路径归一化后改名避让，不覆盖。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        _ensure_app().processEvents()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _stub(self, name, cat):
        win = self.win
        self._old_ask = win._ask_name_category
        self._old_box = win._wrap_box
        self.boxes = []
        win._ask_name_category = lambda *a, **k: (name, cat)
        win._wrap_box = lambda *a, **k: self.boxes.append(a) or None

    def _unstub(self):
        self.win._ask_name_category = self._old_ask
        self.win._wrap_box = self._old_box

    def _add_mem(self, rel, d):
        # rel 允许斜杠形式，模拟不同来源的路径写法
        p = str(self.tmp / "collections" / rel)
        self.win._collections.append((p, d))
        return p

    def test_duplicate_name_blocked(self):
        win = self.win
        x = self.tmp / "collections" / "custom" / "X.json"
        x.write_text(json.dumps({"id": "x", "name": "X", "category": "custom",
                                 "tags": [], "work_ids": []}, ensure_ascii=False),
                     encoding="utf-8")
        before = x.read_text(encoding="utf-8")
        self._add_mem("custom/X.json", {"id": "x", "name": "X", "category": "custom",
                                        "tags": [], "work_ids": []})
        blank_path = self._add_mem("custom/空白.json",
                                   {"id": "b", "name": "空白", "category": "custom",
                                    "tags": [], "work_ids": []})
        blank_d = win._coll_dict(blank_path)
        self._stub("X", "custom")
        try:
            ret = win._finalize_blank_save(blank_path, blank_d)
        finally:
            self._unstub()
        self.assertIs(ret, False)
        self.assertTrue(any("重名" in str(a) for a in self.boxes), self.boxes)
        self.assertEqual(x.read_text(encoding="utf-8"), before)  # 原文件未被覆盖
        self.assertEqual(blank_d["name"], "空白")  # 未改名，保持空白态

    def test_path_forms_normalized_no_overwrite(self):
        # 内存路径为斜杠形式＋大小写差异时，仍检出占用并改名，不覆盖同文件
        win = self.win
        mem_path = (str(self.tmp / "collections" / "custom" / "Y.json")).replace("\\", "/")
        win._collections.append((mem_path, {"id": "y", "name": "Y", "category": "custom",
                                            "tags": [], "work_ids": []}))
        blank_path = self._add_mem("custom/空白2.json",
                                   {"id": "b2", "name": "空白2", "category": "custom",
                                    "tags": [], "work_ids": []})
        blank_d = win._coll_dict(blank_path)
        self._stub("y", "custom")   # 与 "Y" 仅大小写不同，精确查重放过
        try:
            ret = win._finalize_blank_save(blank_path, blank_d)
        finally:
            self._unstub()
        self.assertIsNot(ret, False)
        targets = [str(pp) for pp, dd in win._collections if dd is blank_d]
        self.assertEqual(len(targets), 1)
        # 未指向已占用文件（改名避让），磁盘未产生 y.json/Y.json
        import os as _os
        self.assertTrue(targets[0].endswith("y_1.json"), targets)
        for pp, dd in win._collections:
            if dd is not blank_d:
                self.assertNotEqual(_os.path.normcase(str(pp)),
                                    _os.path.normcase(targets[0]))
        self.assertFalse((self.tmp / "collections" / "custom" / "y.json").exists())
        self.assertFalse((self.tmp / "collections" / "custom" / "Y.json").exists())
        # 走真实写盘：落到 y_1.json，不碰已占用文件
        self.assertTrue(win._save_one_collection(targets[0]))
        self.assertTrue((self.tmp / "collections" / "custom" / "y_1.json").is_file())
        self.assertFalse((self.tmp / "collections" / "custom" / "Y.json").exists())


class RenameCollectionTest(unittest.TestCase):
    """丛书改名：管理行「改名」在删除左；重名拦截（与空白保存一致）；成功立即落盘。
    右栏布局：空白按钮与丛书下拉框同行（下拉框 stretch 收窄）；标签按钮改名「标签」。"""

    @classmethod
    def setUpClass(cls):
        cls.win, cls.tmp = _make_window()
        _ensure_app().processEvents()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _add(self, rel, d):
        p = self.tmp / "collections" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        sp = str(p)
        self.win._collections.append((sp, d))
        self.win.coll_combo.addItem(d.get("name", p.stem), sp)
        return sp

    def _select(self, path):
        win = self.win
        for i in range(win.coll_combo.count()):
            if win.coll_combo.itemData(i) == path:
                win.coll_combo.setCurrentIndex(i)
                return
        self.fail(f"combo 缺少 {path}")

    def test_right_layout_blank_left_of_combo(self):
        from PySide6.QtWidgets import QHBoxLayout
        win = self.win
        lay = win.coll_combo.parentWidget().layout()
        self.assertIsInstance(lay, QHBoxLayout)
        self.assertIs(lay.itemAt(0).widget(), win.btn_blank)
        self.assertIs(lay.itemAt(1).widget(), win.coll_combo)
        self.assertEqual(lay.stretch(1), 1)

    def test_mgmt_row_order_and_tags_label(self):
        win = self.win
        texts = [win.btn_save.text(), win.btn_saveas.text(), win.btn_restore.text(),
                 win.btn_rename.text(), win.btn_delete.text(), win.btn_tags.text()]
        self.assertEqual(texts, ["保存", "另存", "恢复", "改名", "删除", "标签"])

    def test_rename_duplicate_blocked(self):
        from unittest import mock
        win = self.win
        x = self._add("custom/RX.json", {"id": "rx", "name": "RX",
                                         "category": "custom", "tags": [], "work_ids": []})
        b = self._add("custom/R空白.json", {"id": "rb", "name": "R空白",
                                            "category": "custom", "tags": [], "work_ids": []})
        before = Path(x).read_text(encoding="utf-8")
        boxes = []
        old_box = win._wrap_box
        win._wrap_box = lambda *a, **k: boxes.append(a) or None
        self._select(b)
        try:
            with mock.patch("cbeta_publish.gui.main_window.QInputDialog.getText",
                            return_value=("RX", True)):
                win._rename_collection()
        finally:
            win._wrap_box = old_box
        self.assertTrue(any("重名" in str(a) for a in boxes), boxes)
        self.assertEqual(win._coll_dict(b)["name"], "R空白")  # 未改名
        self.assertEqual(Path(x).read_text(encoding="utf-8"), before)  # 原文件未动

    def test_rename_saves_immediately(self):
        from unittest import mock
        win = self.win
        b = self._add("custom/R改.json", {"id": "rg", "name": "R改",
                                          "category": "custom", "tags": [], "work_ids": []})
        boxes = []
        old_box = win._wrap_box
        win._wrap_box = lambda *a, **k: boxes.append(a) or None
        self._select(b)
        try:
            with mock.patch("cbeta_publish.gui.main_window.QInputDialog.getText",
                            return_value=("R改好", True)):
                win._rename_collection()
        finally:
            win._wrap_box = old_box
        self.assertEqual(boxes, [])  # 无弹窗
        on_disk = json.loads(Path(b).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["name"], "R改好")  # 已落盘
        self.assertEqual(win._coll_dict(b)["name"], "R改好")
        self.assertNotIn(b, win._changed_colls)  # 无星号残留
        for i in range(win.coll_combo.count()):
            if win.coll_combo.itemData(i) == b:
                self.assertEqual(win.coll_combo.itemText(i), "R改好")

    def test_name_enter_opens_category_popup(self):
        # 「保存空白丛书」弹窗：名称框回车应打开分类下拉，而不是直接接受弹窗
        # （默认项是「＋ 新建分类…」，直接接受会跳进新建分类）
        from PySide6.QtWidgets import QApplication, QLineEdit, QComboBox
        from PySide6.QtCore import QTimer, QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        win = self.win
        seen = {}

        def act():
            dlg = QApplication.activeModalWidget()
            seen["dlg"] = dlg
            le = dlg.findChild(QLineEdit)
            cb = dlg.findChild(QComboBox)
            seen["cb"] = cb
            le.setFocus()
            QApplication.sendEvent(le, QKeyEvent(QEvent.KeyPress, Qt.Key_Return,
                                                 Qt.NoModifier))
            _ensure_app().processEvents()
            seen["popup"] = cb.view().isVisible()   # 分类下拉已弹出
            seen["still_open"] = dlg.isVisible()     # 未被回车直接接受
            dlg.reject()

        QTimer.singleShot(0, act)
        win._ask_name_category("保存空白丛书", "空白")
        self.assertTrue(seen.get("still_open"))     # 未因回车而关闭
        self.assertTrue(seen.get("popup"))           # 回车打开了分类下拉

    def test_delete_refreshes_left_coll_tree(self):
        # 左栏当前为「丛书」视图：右栏删除丛书后，左栏同步去掉该丛书
        from PySide6.QtCore import Qt
        win = self.win
        b = self._add("custom/R删.json", {"id": "rd", "name": "R删",
                                          "category": "custom", "tags": [], "work_ids": []})
        win.nav_combo.setCurrentText("丛书")
        win._refresh_coll_tree()   # 确保左栏含刚加入的丛书
        _ensure_app().processEvents()

        def _tree_names():
            return [win.tree.topLevelItem(i).data(0, Qt.UserRole).get("name")
                    for i in range(win.tree.topLevelItemCount())]

        self.assertIn("R删", _tree_names())
        self._select(b)
        win._delete_collection()   # 本会话新建且为空 → 不弹确认
        _ensure_app().processEvents()
        self.assertNotIn("R删", _tree_names())
        self.assertFalse(Path(b).exists())

    def test_rename_refreshes_left_coll_tree(self):
        # 左栏当前为「丛书」视图：右栏改名后，左栏同步显示新名
        from unittest import mock
        from PySide6.QtCore import Qt
        win = self.win
        b = self._add("custom/R名.json", {"id": "rn", "name": "R名",
                                          "category": "custom", "tags": [], "work_ids": []})
        win.nav_combo.setCurrentText("丛书")
        win._refresh_coll_tree()   # 确保左栏含刚加入的丛书（nav 可能已是「丛书」不触发刷新）
        _ensure_app().processEvents()

        def _tree_names():
            return [win.tree.topLevelItem(i).data(0, Qt.UserRole).get("name")
                    for i in range(win.tree.topLevelItemCount())]

        self.assertIn("R名", _tree_names())
        self._select(b)
        with mock.patch("cbeta_publish.gui.main_window.QInputDialog.getText",
                        return_value=("R名好", True)):
            win._rename_collection()
        _ensure_app().processEvents()
        names = _tree_names()
        self.assertIn("R名好", names)
        self.assertNotIn("R名", names)


if __name__ == "__main__":
    unittest.main()
