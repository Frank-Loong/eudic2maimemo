import unittest

from eudic2maimemo.words import lemma_candidates


class LemmaTest(unittest.TestCase):
    def test_plural(self):
        self.assertIn("cat", lemma_candidates("cats"))
        self.assertIn("phrase", lemma_candidates("phrases"))
        self.assertIn("study", lemma_candidates("studies"))

    def test_plural_keeps_es_variant(self):
        """phrases 既可能是 +s，也可能是 +es，两个候选都要给。"""
        self.assertIn("phras", lemma_candidates("phrases"))
        self.assertIn("phrase", lemma_candidates("phrases"))

    def test_past_tense(self):
        self.assertIn("demonstrate", lemma_candidates("demonstrated"))
        self.assertIn("plan", lemma_candidates("planned"))

    def test_progressive(self):
        self.assertIn("run", lemma_candidates("running"))
        self.assertIn("make", lemma_candidates("making"))

    def test_adverb(self):
        self.assertIn("quick", lemma_candidates("quickly"))

    def test_comparative(self):
        self.assertIn("happy", lemma_candidates("happier"))

    def test_skips_short_and_phrases(self):
        self.assertEqual(lemma_candidates("cat"), [])
        self.assertEqual(lemma_candidates("a"), [])
        self.assertEqual(lemma_candidates("cover letter"), [])

    def test_candidates_exclude_input(self):
        self.assertNotIn("cats", lemma_candidates("cats"))

    def test_no_duplicate_candidates(self):
        cands = lemma_candidates("phrases")
        self.assertEqual(len(cands), len(set(cands)))


if __name__ == "__main__":
    unittest.main()
