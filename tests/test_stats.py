import unittest

from eudic2maimemo.eudic import Word
from eudic2maimemo.stats import format_summary, summarize


def w(text, day="2026-10-01T00:00:00Z", star=1, phon="/x/", exp="释义"):
    return Word(word=text, add_time=day, star=star, phon=phon, exp=exp)


class SummarizeTest(unittest.TestCase):
    def test_empty(self):
        stats = summarize([])
        self.assertEqual(stats.total, 0)
        self.assertEqual(stats.first_date, "-")

    def test_counts_and_range(self):
        words = [
            w("a", "2024-09-18T00:00:00Z"),
            w("b", "2026-06-01T00:00:00Z"),
            w("c", "2026-06-02T00:00:00Z"),
        ]
        stats = summarize(words)
        self.assertEqual(stats.total, 3)
        self.assertEqual(stats.first_date, "2024-09-18")
        self.assertEqual(stats.last_date, "2026-06-02")
        self.assertEqual(stats.by_month, {"2024-09": 1, "2026-06": 2})

    def test_deduplicates_case_insensitively(self):
        stats = summarize([w("Cat"), w("cat"), w("dog")])
        self.assertEqual(stats.total, 3)
        self.assertEqual(stats.unique, 2)

    def test_detects_data_gaps(self):
        words = [
            w("ok"),
            w("no_phon", phon=""),
            w("no_exp", exp=""),
            w("cover letter"),
            w("可持续发展"),
        ]
        stats = summarize(words)
        self.assertEqual(stats.missing_phon, 1)
        self.assertEqual(stats.missing_exp, 1)
        self.assertEqual(stats.phrases, 1)
        self.assertEqual(stats.chinese, 1)

    def test_star_distribution(self):
        stats = summarize([w("a", star=1), w("b", star=1), w("c", star=5)])
        self.assertEqual(stats.stars, {1: 2, 5: 1})

    def test_summary_contains_key_numbers(self):
        text = format_summary(summarize([w("a"), w("b")]))
        self.assertIn("总词数 2", text)
        self.assertIn("无音标", text)


if __name__ == "__main__":
    unittest.main()
