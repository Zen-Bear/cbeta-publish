# -*- coding: utf-8 -*-
"""SutraList 服务（SutraService）：只登记真作品编号，目录/区间节点不当作品。"""
import json
import tempfile
import unittest
from pathlib import Path

from cbeta_publish.catalog.sutra_service import SutraService


class SutraServiceTest(unittest.TestCase):
    def _service(self, data):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = Path(tmp.name) / "SutraList.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return SutraService(p)

    def test_keeps_only_leaf_work_ids(self):
        # 目录节点（TX 太虛大師全書）与区间节点（X01-02 …、J32-33）首词不是作品编号，不进表
        svc = self._service([
            {"title": "TX 太虛大師全書", "children": [
                {"title": "TXa001 太虛大師全書．編纂說明"},
                {"title": "TX0001 太虛大師全書．第一編　佛法總學"}]},
            {"title": "X01-02 印度撰述 X0001-0207", "children": [
                {"title": "X0001 某經"}]},
            {"title": "J32-33"},
            {"title": "T 大正新脩大藏經", "children": [
                {"title": "T0001 長阿含經"},
                {"title": "T0150A 七處三觀經"},
                {"title": "ZW0018b 某書"}]},
        ])
        self.assertEqual(sorted(svc.all_ids()),
                         ["T0001", "T0150A", "TX0001", "TXa001", "X0001", "ZW0018b"])

    def test_title_of_falls_back_to_id_for_container_nodes(self):
        svc = self._service([
            {"title": "TX 太虛大師全書", "children": [
                {"title": "TXa001 太虛大師全書．編纂說明"},
                {"title": "TX0001 太虛大師全書．第一編　佛法總學"}]},
        ])
        # 目录节点不再登记标题：title_of 回退为原样（不再吐出「TX 太虛大師全書」）
        self.assertEqual(svc.title_of("TX"), "TX")
        self.assertEqual(svc.title_of("TXa001"), "TXa001 太虛大師全書．編纂說明")
        self.assertEqual(svc.title_of("TX0001"), "TX0001 太虛大師全書．第一編　佛法總學")
        self.assertEqual(svc.title_of("NOPE"), "NOPE")


if __name__ == "__main__":
    unittest.main()
