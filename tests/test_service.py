import unittest

from eudic2maimemo.http import RateLimited, SyncError
from eudic2maimemo.service import run_forever


class RunForeverTest(unittest.TestCase):
    def test_runs_requested_times(self):
        calls = []
        sleeps = []

        def task():
            calls.append(1)
            return True

        runs = run_forever(
            task, interval_seconds=60, max_runs=3, sleep=sleeps.append
        )
        self.assertEqual(runs, 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [60, 60])  # 最后一轮之后不再等待

    def test_recovers_from_sync_error(self):
        errors = []

        def task():
            raise SyncError("网络抖动")

        runs = run_forever(
            task,
            interval_seconds=1,
            max_runs=2,
            sleep=lambda _: None,
            on_error=errors.append,
        )
        self.assertEqual(runs, 2)
        self.assertEqual(len(errors), 2)

    def test_rate_limit_stops_the_loop(self):
        def task():
            raise RateLimited("403")

        with self.assertRaises(RateLimited):
            run_forever(task, interval_seconds=1, max_runs=5, sleep=lambda _: None)

    def test_unexpected_exception_does_not_kill_loop(self):
        def task():
            raise ValueError("boom")

        runs = run_forever(task, interval_seconds=1, max_runs=2, sleep=lambda _: None)
        self.assertEqual(runs, 2)


if __name__ == "__main__":
    unittest.main()
