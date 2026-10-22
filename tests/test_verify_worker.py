# -*- coding: utf-8 -*-
"""校验线程异常时的失败口径：只补「未处理」作品，已通过的不算失败。"""
import unittest

from cbeta_publish.books.verify_worker import unprocessed_works


class UnprocessedWorksTest(unittest.TestCase):
    def test_only_unprocessed(self):
        works = ["A", "B", "C", "D"]
        verdicts = {"A": {"passed": ["pdf"]}, "B": {"passed": []}}
        failed = ["C"]
        self.assertEqual(unprocessed_works(works, verdicts, failed), ["D"])

    def test_all_done(self):
        self.assertEqual(unprocessed_works(["A"], {"A": {}}, []), [])
        self.assertEqual(unprocessed_works([], {}, []), [])


if __name__ == "__main__":
    unittest.main()
