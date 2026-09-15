# -*- coding: utf-8 -*-
"""链路B 桥接：XML 定位测试（sutra_mapping + 两种文件命名）。"""
import shutil
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.catalog.mapping_service import MappingService
from cbeta_publish.books.xml2pdf_bridge import find_xml

MULU = Path(__file__).resolve().parents[1] / "mulu" / "sutra_mapping.txt"


class BridgeFindXmlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.map = MappingService(MULU)

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "T" / "T01").mkdir(parents=True)
        (self.dir / "T" / "T02").mkdir(parents=True)
        # GitHub 命名（整部）与 CBReader 命名（分卷）各一
        (self.dir / "T" / "T01" / "T01n0001.xml").write_text("<x/>", encoding="utf-8")
        (self.dir / "T" / "T02" / "T02n0099_001.xml").write_text("<x/>", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_github_style(self):
        cfg = {"book_dir": str(self.dir)}
        p = find_xml("T0001", cfg, mapping=self.map)
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "T01n0001.xml")

    def test_cbreader_style(self):
        cfg = {"book_dir": str(self.dir)}
        p = find_xml("T0099", cfg, mapping=self.map)
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "T02n0099_001.xml")

    def test_missing(self):
        cfg = {"book_dir": str(self.dir)}
        self.assertIsNone(find_xml("T9999", cfg, mapping=self.map))

    def test_local_xml_root_fallback(self):
        cfg = {"local_xml_root": str(self.dir)}
        p = find_xml("T0001", cfg, mapping=self.map)
        self.assertIsNotNone(p)


if __name__ == "__main__":
    unittest.main()
