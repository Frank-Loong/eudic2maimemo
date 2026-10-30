import types
import unittest

from eudic2maimemo.config import Config
from eudic2maimemo.eudic import Word
from eudic2maimemo.http import SyncError
from eudic2maimemo.maimemo import Notepad
from eudic2maimemo.sync import run_sync, to_cn_date


def word(text, day="2026-10-29T00:00:00Z"):
    return Word(word=text, add_time=day)


class FakeEudic:
    def __init__(self, all_words=None, new_words=None):
        self._all = all_words or []
        self._new = new_words or []
        self.http = types.SimpleNamespace(request_count=2)

    def fetch_all(self, book_ids):
        return list(self._all)

    def fetch_new(self, book_ids, known_keys):
        return [w for w in self._new if w.key not in known_keys]


class FakeMaimemo:
    def __init__(self, content=""):
        self.content = content
        self.saved = None
        self.http = types.SimpleNamespace(request_count=1)

    def get_notepad(self, notepad_id):
        return Notepad(id=notepad_id, title="欧路生词", content=self.content)

    def update_notepad(self, notepad_id, content, *, title, brief):
        self.saved = content
        self.content = content
        return Notepad(id=notepad_id, title=title, content=content)


def make_config():
    return Config(
        eudic_api_key="NIS test",
        eudic_category_ids=["0"],
        maimemo_token="token",
        maimemo_notepad_id="np-test",
    )


class SyncTest(unittest.TestCase):
    def test_incremental_appends_new_words(self):
        maimemo = FakeMaimemo("#2026-10-29\nagainst\n")
        eudic = FakeEudic(new_words=[word("against"), word("chargeable")])
        report = run_sync(make_config(), eudic=eudic, maimemo=maimemo)

        self.assertEqual(report.added, 1)
        self.assertTrue(report.wrote)
        self.assertIn("chargeable", maimemo.saved)
        self.assertIn("#2026-10-29", maimemo.saved)
        self.assertEqual(maimemo.saved.count("against"), 1)

    def test_no_change_does_not_write(self):
        maimemo = FakeMaimemo("#2026-10-29\nagainst\n")
        eudic = FakeEudic(new_words=[word("against")])
        report = run_sync(make_config(), eudic=eudic, maimemo=maimemo)

        self.assertEqual(report.added, 0)
        self.assertFalse(report.wrote)
        self.assertIsNone(maimemo.saved)

    def test_dry_run_does_not_write(self):
        maimemo = FakeMaimemo("")
        eudic = FakeEudic(new_words=[word("cat")])
        report = run_sync(make_config(), eudic=eudic, maimemo=maimemo, dry_run=True)

        self.assertEqual(report.added, 1)
        self.assertFalse(report.wrote)
        self.assertIsNone(maimemo.saved)

    def test_full_rebuild_replaces_content(self):
        maimemo = FakeMaimemo("#2020-01-01\nstale\n")
        eudic = FakeEudic(all_words=[word("cat", "2026-10-01T00:00:00Z")])
        report = run_sync(make_config(), mode="full", eudic=eudic, maimemo=maimemo)

        self.assertTrue(report.wrote)
        self.assertNotIn("stale", maimemo.saved)
        self.assertIn("cat", maimemo.saved)
        self.assertEqual(report.total, 1)
        self.assertEqual(report.orphaned, 1)

    def test_full_rebuild_keeps_words_already_in_notepad(self):
        """回归：全量重建时，云词本里已有的词也必须写回去，否则等于清空。"""
        maimemo = FakeMaimemo("#2026-01-01\ncat\n")
        eudic = FakeEudic(all_words=[word("cat", "2026-01-01T00:00:00Z"), word("dog", "2026-01-02T00:00:00Z")])
        report = run_sync(make_config(), mode="full", eudic=eudic, maimemo=maimemo)

        self.assertTrue(report.wrote)
        self.assertEqual(report.total, 2)
        self.assertIn("cat", maimemo.saved)
        self.assertIn("dog", maimemo.saved)

    def test_full_rebuild_identical_content_is_noop(self):
        maimemo = FakeMaimemo("#2026-01-01\ncat\n")
        eudic = FakeEudic(all_words=[word("cat", "2026-01-01T00:00:00Z")])
        report = run_sync(make_config(), mode="full", eudic=eudic, maimemo=maimemo)

        self.assertFalse(report.wrote)
        self.assertIsNone(maimemo.saved)

    def test_limit_is_rejected_with_full(self):
        maimemo = FakeMaimemo("")
        eudic = FakeEudic(all_words=[word(f"w{i}") for i in range(5)])
        with self.assertRaises(SyncError):
            run_sync(make_config(), mode="full", eudic=eudic, maimemo=maimemo, limit=2)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(SyncError):
            run_sync(make_config(), mode="bogus", eudic=FakeEudic(), maimemo=FakeMaimemo())

    def test_limit_caps_new_words(self):
        maimemo = FakeMaimemo("")
        eudic = FakeEudic(new_words=[word(f"w{i}") for i in range(5)])
        report = run_sync(make_config(), eudic=eudic, maimemo=maimemo, limit=2)

        self.assertEqual(report.added, 2)
        self.assertEqual(len(report.added_words), 2)

    def test_ignore_patterns_skip_words(self):
        maimemo = FakeMaimemo("")
        eudic = FakeEudic(new_words=[word("cover letter"), word("cat"), word("可持续发展")])
        config = make_config()
        config.ignore_patterns = [r"\s", r"[\u4e00-\u9fff]"]

        report = run_sync(config, eudic=eudic, maimemo=maimemo)

        self.assertEqual(report.added, 1)
        self.assertEqual(report.skipped, 2)
        self.assertIn("cat", maimemo.saved)
        self.assertNotIn("cover letter", maimemo.saved)

    def test_min_star_filters_low_star_words(self):
        maimemo = FakeMaimemo("")
        eudic = FakeEudic(
            new_words=[
                Word(word="one", add_time="2026-10-01T00:00:00Z", star=1),
                Word(word="four", add_time="2026-10-01T00:00:00Z", star=4),
                Word(word="five", add_time="2026-10-01T00:00:00Z", star=5),
            ]
        )
        config = make_config()
        config.min_star = 4

        report = run_sync(config, eudic=eudic, maimemo=maimemo)

        self.assertEqual(report.added, 2)
        self.assertEqual(report.low_star, 1)
        self.assertNotIn("one", maimemo.saved)

    def test_min_star_zero_keeps_everything(self):
        maimemo = FakeMaimemo("")
        eudic = FakeEudic(new_words=[Word(word="one", star=1)])
        report = run_sync(make_config(), eudic=eudic, maimemo=maimemo)
        self.assertEqual(report.added, 1)
        self.assertEqual(report.low_star, 0)

    def test_invalid_ignore_pattern_raises(self):
        config = make_config()
        config.ignore_patterns = ["[unclosed"]
        with self.assertRaises(SyncError):
            config.compile_ignore_patterns()


class DateTest(unittest.TestCase):
    def test_utc_converted_to_china_date(self):
        # 2026-10-29T21:38Z = 2026-10-30 05:38 (UTC+8)
        self.assertEqual(to_cn_date("2026-10-29T21:38:20Z"), "2026-10-30")

    def test_bad_input(self):
        self.assertEqual(to_cn_date(""), "未知日期")
        self.assertEqual(to_cn_date("not-a-date"), "未知日期")


if __name__ == "__main__":
    unittest.main()
