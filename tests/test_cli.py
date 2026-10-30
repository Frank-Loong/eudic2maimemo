import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from eudic2maimemo import cli
from eudic2maimemo.config import Config
from eudic2maimemo.eudic import Word
from eudic2maimemo.http import SyncError


def config():
    return Config(eudic_api_key="NIS x", eudic_category_ids=["0"])


def _report():
    from eudic2maimemo.sync import SyncReport

    report = SyncReport(mode="incremental")
    return report


WORD = Word(
    word="cat",
    add_time="2026-01-05T10:00:00Z",
    star=3,
    phon="/kæt/",
    exp="<b>n.</b> 猫",
)


class ParserTest(unittest.TestCase):
    def test_help_without_command(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(cli.main([]), 0)
        self.assertIn("sync", buf.getvalue())

    def test_sync_defaults(self):
        args = cli.build_parser().parse_args(["sync"])
        self.assertFalse(args.full)
        self.assertFalse(args.dry_run)
        self.assertIsNone(args.limit)

    def test_serve_defaults(self):
        args = cli.build_parser().parse_args(["serve", "--interval", "6"])
        self.assertEqual(args.interval, 6.0)
        self.assertFalse(args.full)

    def test_stats_months_default(self):
        args = cli.build_parser().parse_args(["stats"])
        self.assertEqual(args.months, 12)


class ExportTest(unittest.TestCase):
    def run_export(self, fmt, words):
        tmp = tempfile.NamedTemporaryFile(suffix="." + fmt, delete=False)
        tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.remove(tmp.name))

        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.EudicClient"
        ) as client_cls:
            client_cls.return_value.fetch_all.return_value = words
            client_cls.return_value.http.request_count = 2
            with redirect_stdout(io.StringIO()):
                code = cli.main(["export", "--out", tmp.name, "--format", fmt])

        self.assertEqual(code, 0)
        with open(tmp.name, encoding="utf-8-sig") as fh:
            return fh.read()

    def test_csv_has_header_and_stripped_definition(self):
        content = self.run_export("csv", [WORD])
        self.assertIn("word,phon,star,added_at,definition", content)
        self.assertIn("/kæt/", content)
        self.assertIn("n. 猫", content)
        self.assertNotIn("<b>", content)

    def test_json_is_loadable(self):
        content = self.run_export("json", [WORD])
        data = json.loads(content)
        self.assertEqual(data[0]["word"], "cat")
        self.assertEqual(data[0]["star"], 3)

    def test_text_lists_word_and_date(self):
        content = self.run_export("text", [WORD])
        self.assertIn("cat\t2026-01-05", content)


class StatsTest(unittest.TestCase):
    def test_json_output(self):
        buf = io.StringIO()
        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.EudicClient"
        ) as client_cls:
            client_cls.return_value.fetch_all.return_value = [WORD]
            client_cls.return_value.http.request_count = 1
            with redirect_stdout(buf):
                code = cli.main(["stats", "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["unique"], 1)

    def test_text_output_mentions_total(self):
        buf = io.StringIO()
        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.EudicClient"
        ) as client_cls:
            client_cls.return_value.fetch_all.return_value = [WORD]
            client_cls.return_value.http.request_count = 1
            with redirect_stdout(buf):
                cli.main(["stats"])

        self.assertIn("总词数 1", buf.getvalue())


class ErrorHandlingTest(unittest.TestCase):
    def test_sync_error_exits_nonzero(self):
        with patch("eudic2maimemo.cli.Config.from_env", side_effect=SyncError("缺 token")):
            self.assertEqual(cli.main(["sync"]), 1)

    def test_notify_is_called_on_success(self):
        sent = []
        with patch("eudic2maimemo.cli.Config.from_env") as from_env, patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync, patch("eudic2maimemo.cli.notify.send", side_effect=lambda *a: sent.append(a)):
            cfg = config()
            cfg.notify_url = "https://example.com/hook"
            from_env.return_value = cfg
            run_sync.return_value.added = 1
            run_sync.return_value.added_words = ["cat"]
            run_sync.return_value.summary.return_value = "完成"

            with redirect_stdout(io.StringIO()):
                cli.main(["sync"])

        self.assertEqual(len(sent), 1)
        self.assertIn("完成", sent[0][1])

    def test_no_notification_when_nothing_changed(self):
        sent = []
        with patch("eudic2maimemo.cli.Config.from_env") as from_env, patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync, patch("eudic2maimemo.cli.notify.send", side_effect=lambda *a: sent.append(a)):
            cfg = config()
            cfg.notify_url = "https://example.com/hook"
            from_env.return_value = cfg
            run_sync.return_value.added = 0
            run_sync.return_value.added_words = []
            run_sync.return_value.summary.return_value = "无变化"

            with redirect_stdout(io.StringIO()):
                cli.main(["sync"])

        self.assertEqual(sent, [])

    def test_notify_always_overrides(self):
        sent = []
        with patch("eudic2maimemo.cli.Config.from_env") as from_env, patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync, patch("eudic2maimemo.cli.notify.send", side_effect=lambda *a: sent.append(a)):
            cfg = config()
            cfg.notify_url = "https://example.com/hook"
            cfg.notify_always = True
            from_env.return_value = cfg
            run_sync.return_value.added = 0
            run_sync.return_value.added_words = []
            run_sync.return_value.summary.return_value = "无变化"

            with redirect_stdout(io.StringIO()):
                cli.main(["sync"])

        self.assertEqual(len(sent), 1)


class DoctorTest(unittest.TestCase):
    def test_no_credentials_returns_two(self):
        buf = io.StringIO()
        with patch("eudic2maimemo.cli.Config.from_env", return_value=Config(eudic_api_key="")):
            with redirect_stdout(buf):
                code = cli.main(["doctor"])
        self.assertEqual(code, 2)
        self.assertIn("都没设置", buf.getvalue())

    def test_missing_notepad_id_lists_ids_and_hints(self):
        """找云词本 ID 的场景：只配了 token，没配 ID。"""
        from eudic2maimemo.maimemo import Notepad

        cfg = Config(eudic_api_key="", maimemo_token="tok", maimemo_notepad_id="")
        buf = io.StringIO()
        with patch("eudic2maimemo.cli.Config.from_env", return_value=cfg), patch(
            "eudic2maimemo.cli.MaimemoClient"
        ) as client_cls:
            client_cls.return_value.list_notepads.return_value = [
                Notepad(id="np-abc", title="欧路生词", content="")
            ]
            with redirect_stdout(buf):
                code = cli.main(["doctor"])

        out = buf.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("np-abc", out)
        self.assertIn("MOMO_NOTEPAD_ID", out)


class MinStarTest(unittest.TestCase):
    def test_cli_overrides_config(self):
        captured = {}
        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync:
            run_sync.side_effect = lambda cfg, **kw: captured.update(min_star=cfg.min_star) or _report()
            with redirect_stdout(io.StringIO()):
                cli.main(["sync", "--min-star", "4"])
        self.assertEqual(captured["min_star"], 4)

    def test_negative_min_star_is_clamped(self):
        captured = {}
        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync:
            run_sync.side_effect = lambda cfg, **kw: captured.update(min_star=cfg.min_star) or _report()
            with redirect_stdout(io.StringIO()):
                cli.main(["sync", "--min-star", "-2"])
        self.assertEqual(captured["min_star"], 0)


class DoctorDictTest(unittest.TestCase):
    def test_reports_missing_entries(self):
        from eudic2maimemo.eudic import Word
        from eudic2maimemo.maimemo import Notepad

        cfg = Config(
            eudic_api_key="NIS x",
            eudic_category_ids=["0"],
            maimemo_token="tok",
            maimemo_notepad_id="np-1",
        )
        buf = io.StringIO()
        with patch("eudic2maimemo.cli.Config.from_env", return_value=cfg), patch(
            "eudic2maimemo.cli.EudicClient"
        ) as eudic_cls, patch("eudic2maimemo.cli.MaimemoClient") as mm_cls:
            eudic_cls.return_value.list_books.return_value = []
            eudic_cls.return_value.fetch_desc.return_value = []
            eudic_cls.return_value.fetch_asc.return_value = []
            eudic_cls.return_value.fetch_all.return_value = [
                Word(word="cat"),
                Word(word="cnc"),
            ]
            eudic_cls.return_value.http.request_count = 1
            mm_cls.return_value.list_notepads.return_value = [Notepad(id="np-1", title="t", content="")]
            mm_cls.return_value.get_notepad.return_value = Notepad(id="np-1", title="t", content="")
            mm_cls.return_value.lookup_spellings.return_value = {"cat"}

            with redirect_stdout(buf):
                cli.main(["doctor", "--dict"])

        out = buf.getvalue()
        self.assertIn("词典直接收录 1", out)
        self.assertIn("查不到 1", out)
        self.assertIn("cnc", out)


class ServeTest(unittest.TestCase):
    def test_serve_wires_interval_and_runs_task(self):
        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync, patch("eudic2maimemo.cli.run_forever") as forever:
            run_sync.return_value.added = 0

            def fake_forever(task, **kwargs):
                task()
                return 1

            forever.side_effect = fake_forever
            with redirect_stdout(io.StringIO()):
                code = cli.main(["serve", "--interval", "6"])

        self.assertEqual(code, 0)
        self.assertEqual(forever.call_args.kwargs["interval_seconds"], 6 * 3600)
        self.assertTrue(run_sync.called)

    def test_serve_exits_on_rate_limit(self):
        from eudic2maimemo.http import RateLimited

        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.run_forever", side_effect=RateLimited("403")
        ):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["serve"]), 2)


class SyncJsonTest(unittest.TestCase):
    def test_sync_prints_json_report(self):
        buf = io.StringIO()
        with patch("eudic2maimemo.cli.Config.from_env", return_value=config()), patch(
            "eudic2maimemo.cli.run_sync"
        ) as run_sync:
            from eudic2maimemo.sync import SyncReport

            report = SyncReport(mode="incremental", fetched=3, added=1, total=10, blocks=2)
            run_sync.return_value = report

            with redirect_stdout(buf):
                cli.main(["sync", "--json"])

        payload = json.loads(buf.getvalue())
        self.assertEqual(payload["added"], 1)
        self.assertEqual(payload["total"], 10)


if __name__ == "__main__":
    unittest.main()
