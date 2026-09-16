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
        (self.dir / "a.json").write_text("{}", encoding="utf-8")
        (self.dir / "run.json").write_text('// c\n{"k": 1}', encoding="utf-8")
        (self.dir / "bad.json").write_text("{oops", encoding="utf-8")
        (self.dir / "note.txt").write_text("x", encoding="utf-8")
        self.cfg = {"xml2pdf": {"path": "E:/dev/cbeta/xml2pdf", "preset_dir": str(self.dir)}}

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_list_presets(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertEqual(b.list_presets(self.cfg), ["a.json", "run.json"])

    def test_resolve_preset(self):
        import cbeta_publish.books.xml2pdf_bridge as b
        self.assertIsNone(b.resolve_preset(self.cfg, ""))
        self.assertEqual(b.resolve_preset(self.cfg, "a.json"), self.dir / "a.json")
        self.assertIsNone(b.resolve_preset(self.cfg, "nope.json"))

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

    def test_is_fresh(self):
        import os
        import time
        import cbeta_publish.books.xml2pdf_bridge as b
        dest = self.dir / "T0001.pdf"
        dest.write_bytes(b"x")
        self.assertTrue(b.is_fresh(dest, None))
        preset = self.dir / "p.json"
        preset.write_text("{}", encoding="utf-8")
        old = time.time() - 100
        os.utime(dest, (old, old))
        self.assertFalse(b.is_fresh(dest, preset))       # 预设更新过 → 重生成
        os.utime(preset, (old - 100, old - 100))
        self.assertTrue(b.is_fresh(dest, preset))

    def test_dirs_are_absolute_and_unified(self):
        # 目录统一绝对路径：缺省与相对值都按工程根解析
        import cbeta_publish.books.xml2pdf_bridge as b
        default = b.xml_books_dir({})
        self.assertTrue(default.is_absolute())
        self.assertEqual(b.xml_books_dir({"xml_to_ebooks_dir": "rel/xb"}),
                         b.PROJECT_ROOT / "rel" / "xb")
        abs_p = self.dir / "xb2"
        self.assertEqual(b.xml_books_dir({"xml_to_ebooks_dir": str(abs_p)}), abs_p)
        self.assertEqual(b.preset_dir({"xml2pdf": {"path": "E:/x", "preset_dir": "rel/p"}}),
                         b.PROJECT_ROOT / "rel" / "p")


if __name__ == "__main__":
    unittest.main()
