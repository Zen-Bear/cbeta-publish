# -*- coding: utf-8 -*-
"""链路B 桥接：库调用 argv 装配、预设目录、平展输出、复用规则。

注：publish 侧不再自行定位 XML（CBReader 是 P5a 按卷切分，不符合
xml2pdf 要的 P5 整部经；XML 源解析归 xml2pdf 的 materialize_work），
一律传 work id。
"""
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.books import xml2pdf_bridge as _b


class BridgeConvertLibTest(unittest.TestCase):
    """库调用：argv 装配（-i 路径/回退传 id、-f/-o/--config）与取消。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.x2p = self.dir / "x2p"
        self.x2p.mkdir()
        self.cfg = {"xml2pdf": {"path": str(self.x2p)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _patch_run(self, code=0, touch=True):
        import cbeta_publish.books.xml2pdf_bridge as b
        real = b._run_cli
        calls = []

        def fake(argv):
            calls.append(list(argv))
            if touch:
                try:
                    oi = argv.index("-o")
                    Path(argv[oi + 1]).write_bytes(b"x")
                except Exception:
                    pass
            return code
        b._run_cli = fake
        return calls, lambda: setattr(b, "_run_cli", real)

    def test_argv_with_xml_and_preset(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        xml = self.dir / "T01n0001.xml"
        xml.write_text("<x/>", encoding="utf-8")
        out = self.dir / "T0001.pdf"
        preset = self.dir / "my.json"
        preset.write_text("{}", encoding="utf-8")
        calls, restore = self._patch_run()
        try:
            got = b.convert("T0001", xml, out, self.cfg, fmt="pdf", preset=preset)
        finally:
            restore()
        self.assertEqual(got, out)
        self.assertEqual(len(calls), 1)
        a = calls[0]
        self.assertEqual(a[a.index("-i") + 1], str(xml))
        self.assertEqual(a[a.index("-f") + 1], "pdf")
        self.assertEqual(a[a.index("-o") + 1], str(out))
        self.assertEqual(a[a.index("--config") + 1], str(preset))

    def test_argv_without_preset_omits_config(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        calls, restore = self._patch_run()
        try:
            b.convert("T0001", None, out, self.cfg, fmt="epub", preset=None)
        finally:
            restore()
        a = calls[0]
        self.assertEqual(a[a.index("-i") + 1], "T0001")   # 无本地 XML 传 id
        self.assertNotIn("--config", a)

    def test_argv_passes_cbeta_ebook_when_configured(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        ebook = self.dir / "ebook"
        ebook.mkdir()
        cfg = {"xml2pdf": {"path": str(self.x2p), "cbeta_ebook": str(ebook)}}
        calls, restore = self._patch_run()
        try:
            b.convert("T0001", None, out, cfg)
        finally:
            restore()
        a = calls[0]
        self.assertEqual(a[a.index("--cbeta-ebook") + 1], str(ebook))
        # 未配置 → 用默认 CBETA XML 目录（不可空，仍会传）
        calls2, restore2 = self._patch_run()
        try:
            b.convert("T0001", None, out, self.cfg)
        finally:
            restore2()
        self.assertEqual(calls2[0][calls2[0].index("--cbeta-ebook") + 1],
                         str(b.xml_work_dir(self.cfg)))
        self.assertEqual(b.xml_work_dir({}), b.PROJECT_ROOT / "cbeta_xml")

    def test_stop_cancels_before_run(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        calls, restore = self._patch_run()
        try:
            got = b.convert("T0001", None, out, self.cfg, stop=lambda: True)
        finally:
            restore()
        self.assertIsNone(got)
        self.assertEqual(calls, [])

    def test_nonzero_code_returns_none(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        calls, restore = self._patch_run(code=1, touch=False)
        try:
            got = b.convert("T0001", None, out, self.cfg)
        finally:
            restore()
        self.assertIsNone(got)

    def test_missing_x2p_dir_returns_none(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        out = self.dir / "T0001.pdf"
        got = b.convert("T0001", None, out, {"xml2pdf": {"path": str(self.dir / "nope")}})
        self.assertIsNone(got)


class BridgePresetDirTest(unittest.TestCase):
    """预设目录：列出合法预设、解析、平展输出目录。"""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        # 预设目录固定在 xml2pdf 仓库下 presets/：用临时仓库根模拟
        self.root = self.dir / "x2p"
        (self.root / "presets").mkdir(parents=True)
        (self.root / "presets" / "a.json").write_text("{}", encoding="utf-8")
        (self.root / "presets" / "run.json").write_text('// c\n{"k": 1}', encoding="utf-8")
        (self.root / "presets" / "note.txt").write_text("x", encoding="utf-8")
        self.cfg = {"xml2pdf": {"path": str(self.root)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_list_presets(self):
        # 上游 API 不可用（临时仓库根无 pycbeta）时回退本地扫描：stem 名
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.list_presets(self.cfg), ["a", "run"])

    def test_resolve_preset(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        d = self.root / "presets"
        self.assertIsNone(b.resolve_preset(self.cfg, ""))
        self.assertEqual(b.resolve_preset(self.cfg, "a"), d / "a.json")
        self.assertEqual(b.resolve_preset(self.cfg, "a.json"), d / "a.json")
        self.assertIsNone(b.resolve_preset(self.cfg, "nope"))

    def test_load_and_save_preset(self):
        # load/save 走上游 API（不可用时回退本地读写）
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.load_preset_dict("a.json", self.cfg), {})
        p = b.save_preset(self.cfg, "我的配置", {"default_page": "a4"})
        self.assertIsNotNone(p)
        self.assertEqual(p, self.root / "presets" / "我的配置.json")
        self.assertEqual(b.load_preset_dict("我的配置", self.cfg), {"default_page": "a4"})
        self.assertIn("我的配置", b.list_presets(self.cfg))

    def test_flat_dest_and_find_built(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        base = self.dir / "out"
        base.mkdir()
        self.assertEqual(b.xml_dest("T0001", "pdf", base), base / "T0001.pdf")
        self.assertIsNone(b.find_built("T0001", "pdf", base))
        (base / "T0001 中論.pdf").write_bytes(b"x")     # GUI 产出的平展命名也认
        self.assertEqual(b.find_built("T0001", "pdf", base), base / "T0001 中論.pdf")
        (base / "T0001.pdf").write_bytes(b"x")          # 精确名优先
        self.assertEqual(b.find_built("T0001", "pdf", base), base / "T0001.pdf")

    def test_ensure_one_missing_vs_all(self):
        # 仅缺：已有产物直接复用（不调 convert）；全部：一律重跑 convert 并覆盖原路径
        import cbeta_publish.books.xml2pdf_bridge as b
        base = self.dir / "out"
        base.mkdir()
        calls = []

        def fake_convert(w, xml, out, config, fmt="pdf", preset=None, stop=None):
            calls.append(Path(out))
            Path(out).write_bytes(b"x")
            return Path(out)
        real = b.convert
        b.convert = fake_convert
        try:
            # 无产物 → 生成
            p, reused = b.ensure_one("T0001", "pdf", base, self.cfg)
            self.assertFalse(reused)
            self.assertEqual(len(calls), 1)
            # 已有 → 仅缺模式复用
            p2, reused2 = b.ensure_one("T0001", "pdf", base, self.cfg)
            self.assertTrue(reused2)
            self.assertEqual(p2, p)
            self.assertEqual(len(calls), 1)
            # 全部模式 → 重跑，覆盖同名
            p3, reused3 = b.ensure_one("T0001", "pdf", base, self.cfg, regen_all=True)
            self.assertFalse(reused3)
            self.assertEqual(len(calls), 2)
            self.assertEqual(p3, p)
            # 异名产物（GUI 命名）在全部模式下也覆盖原路径，不留两份
            (base / "T0001.pdf").unlink()
            gui = base / "T0001 中論.pdf"
            gui.write_bytes(b"x")
            p4, _ = b.ensure_one("T0001", "pdf", base, self.cfg, regen_all=True)
            self.assertEqual(p4, gui)
            self.assertEqual(len(calls), 3)
            self.assertFalse((base / "T0001.pdf").exists())
        finally:
            b.convert = real

    def test_dirs_are_absolute_and_unified(self):
        # 目录统一绝对路径：缺省与相对值都按工程根解析
        import cbeta_publish.books.xml2pdf_bridge as b
        default = b.xml_books_dir({})
        self.assertTrue(default.is_absolute())
        self.assertEqual(b.xml_books_dir({"xml_to_ebooks_dir": "rel/xb"}),
                         b.PROJECT_ROOT / "rel" / "xb")
        abs_p = self.dir / "xb2"
        self.assertEqual(b.xml_books_dir({"xml_to_ebooks_dir": str(abs_p)}), abs_p)
        # 预设目录固定在仓库下 presets/
        self.assertEqual(b.presets_dir({"xml2pdf": {"path": "E:/x"}}),
                         Path("E:/x") / "presets")


if __name__ == "__main__":
    unittest.main()
