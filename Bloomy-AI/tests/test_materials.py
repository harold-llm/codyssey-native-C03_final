import unittest

from ai.rag.materials import is_owned

ORT = {"id": "ort-stage2", "title": "Oxford Reading Tree - Stage 2"}
SSS = {"id": "sss-abc", "title": "Super Simple Songs - ABC Song"}
DEMO = {"id": "demo-speaking-001", "title": "개발용 인사 놀이 카드"}


class OwnedMaterialTests(unittest.TestCase):
    def test_abbreviation_and_korean_aliases(self):
        for term in ("ORT", "ort 1~3단계", "옥스포드", "오알티", "Oxford Reading Tree", "ort"):
            self.assertTrue(is_owned(ORT, [term]), term)
        self.assertTrue(is_owned(SSS, ["슈퍼심플"]))

    def test_exact_id_and_title(self):
        self.assertTrue(is_owned(DEMO, ["demo-speaking-001"]))
        self.assertTrue(is_owned(DEMO, ["인사 놀이"]))

    def test_no_false_positive_inside_words(self):
        for term in ("short stories", "sorting game", "핑크퐁", ""):
            self.assertFalse(is_owned(ORT, [term]), term)


if __name__ == "__main__":
    unittest.main()
