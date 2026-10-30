import time
import unittest
from unittest.mock import patch

import requests

from eudic2maimemo.http import (
    ApiError,
    AuthError,
    HttpClient,
    RateLimited,
    RateLimiter,
    SyncError,
)


class FakeResponse:
    def __init__(self, status, body="{}"):
        self.status_code = status
        self.text = body

    def json(self):
        return {}


class FakeSession:
    """按预设序列返回响应或抛异常。"""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else FakeResponse(200)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client_with(outcomes, retries=3):
    session = FakeSession(outcomes)
    http = HttpClient(session=session, retries=retries, backoff=0)
    return http, session


class HttpClientTest(unittest.TestCase):
    def setUp(self):
        # 去掉退避等待，测试才跑得快
        self.sleep = patch("eudic2maimemo.http.time.sleep", return_value=None)
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def test_returns_response_on_success(self):
        http, session = client_with([FakeResponse(200)])
        response = http.request("GET", "https://example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(http.request_count, 1)

    def test_retries_connection_errors(self):
        http, session = client_with(
            [requests.ConnectionError("boom"), requests.ConnectionError("boom"), FakeResponse(200)]
        )
        self.assertEqual(http.request("GET", "https://example.com").status_code, 200)
        self.assertEqual(session.calls, 3)

    def test_retries_server_errors(self):
        http, session = client_with([FakeResponse(502), FakeResponse(200)])
        self.assertEqual(http.request("GET", "https://example.com").status_code, 200)
        self.assertEqual(session.calls, 2)

    def test_gives_up_after_retries(self):
        http, _ = client_with([requests.ConnectionError("boom")] * 3, retries=3)
        with self.assertRaises(SyncError):
            http.request("GET", "https://example.com")

    def test_401_is_auth_error_and_not_retried(self):
        http, session = client_with([FakeResponse(401, "bad token")])
        with self.assertRaises(AuthError):
            http.request("GET", "https://example.com")
        self.assertEqual(session.calls, 1)

    def test_403_is_rate_limit_and_not_retried(self):
        http, session = client_with([FakeResponse(403, "访问过于频繁")])
        with self.assertRaises(RateLimited):
            http.request("GET", "https://example.com")
        self.assertEqual(session.calls, 1)

    def test_429_is_rate_limit(self):
        http, _ = client_with([FakeResponse(429)])
        with self.assertRaises(RateLimited):
            http.request("GET", "https://example.com")

    def test_other_4xx_is_api_error(self):
        http, _ = client_with([FakeResponse(400, "参数不正确：page")])
        with self.assertRaises(ApiError) as ctx:
            http.request("GET", "https://example.com")
        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("page", str(ctx.exception))

    def test_retry_warnings_go_to_stderr(self):
        """回归：诊断信息不能写进 stdout，否则 --json 的输出无法直接解析。"""
        import contextlib
        import io

        http, _ = client_with([requests.ConnectionError("boom"), FakeResponse(200)])
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            http.request("GET", "https://example.com")

        self.assertEqual(out.getvalue(), "")
        self.assertIn("重试", err.getvalue())


class RateLimiterTest(unittest.TestCase):
    def test_allows_burst_within_limit(self):
        limiter = RateLimiter(max_calls=3, period=0.2)
        started = time.monotonic()
        for _ in range(3):
            limiter.wait()
        self.assertLess(time.monotonic() - started, 0.2)

    def test_blocks_when_limit_reached(self):
        limiter = RateLimiter(max_calls=2, period=0.15)
        limiter.wait()
        limiter.wait()
        started = time.monotonic()
        limiter.wait()  # 第三次必须等窗口滑过去
        self.assertGreaterEqual(time.monotonic() - started, 0.1)


if __name__ == "__main__":
    unittest.main()
