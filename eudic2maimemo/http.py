"""HTTP 层：限流 + 重试。

欧路开放 API 的限流是硬性的：

    1 分钟   30 次
    30 分钟  500 次

超限返回 403，并按官方说明封停 1 小时。所以这里不能"失败就立刻重试"，
必须先做主动节流（默认 28 次/分钟，留两次余量），遇到 403 直接判为
限流错误交给上层处理，避免把封停时间越拖越长。
"""

from __future__ import annotations

import random
import sys
import time
from collections import deque
from typing import Any

import requests


class SyncError(Exception):
    """同步流程中的可预期错误（配置、鉴权、数据格式等）。"""


class AuthError(SyncError):
    """token 无效或过期。"""


class RateLimited(SyncError):
    """触发了服务端限流。"""


class ApiError(SyncError):
    """服务端返回了非预期的状态码。"""

    def __init__(self, status: int, body: str = "") -> None:
        self.status = status
        self.body = body
        snippet = body.strip().replace("\n", " ")[:300]
        super().__init__(f"HTTP {status}: {snippet}")


class RateLimiter:
    """滑动窗口限流器。"""

    def __init__(self, max_calls: int = 28, period: float = 60.0) -> None:
        self.max_calls = max_calls
        self.period = period
        self._calls: deque[float] = deque()

    def wait(self) -> None:
        while True:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= self.period:
                self._calls.popleft()
            if len(self._calls) < self.max_calls:
                self._calls.append(now)
                return
            sleep_for = self.period - (now - self._calls[0]) + 0.05
            if sleep_for > 0:
                time.sleep(sleep_for)


class HttpClient:
    """带节流与指数退避的 HTTP 客户端。"""

    def __init__(
        self,
        limiter: RateLimiter | None = None,
        timeout: float = 45.0,
        retries: int = 5,
        backoff: float = 2.0,
        session: requests.Session | None = None,
    ) -> None:
        self.limiter = limiter
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.session = session or requests.Session()
        self.request_count = 0

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        timeout: float | None = None,
    ) -> requests.Response:
        last_error: Exception | None = None

        for attempt in range(self.retries):
            if self.limiter is not None:
                self.limiter.wait()

            self.request_count += 1
            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=timeout or self.timeout,
                )
            except requests.RequestException as exc:  # 连接重置 / SSL EOF / 超时
                last_error = exc
                self._sleep(attempt, label=type(exc).__name__)
                continue

            status = response.status_code
            if status in (401, 403):
                # 401 鉴权失败；403 在欧路是限流。两者重试都不会自愈。
                body = _safe_text(response)
                if status == 401:
                    raise AuthError(f"鉴权失败(401)：{body}") from None
                raise RateLimited(
                    f"触发限流(403)，已停止本次同步以免封停：{body}"
                ) from None
            if status == 429:
                raise RateLimited("触发限流(429)，已停止本次同步") from None
            if status >= 500:
                last_error = ApiError(status, _safe_text(response))
                self._sleep(attempt, label=f"HTTP {status}")
                continue
            if status >= 400:
                raise ApiError(status, _safe_text(response))

            return response

        raise SyncError(f"请求重试 {self.retries} 次仍失败：{last_error}")

    def _sleep(self, attempt: int, *, label: str = "") -> None:
        delay = self.backoff ** attempt + random.uniform(0, 0.8)
        print(f"[warn] {label}，{delay:.1f}s 后重试（第 {attempt + 1} 次）", file=sys.stderr, flush=True)
        time.sleep(delay)


def _safe_text(response: requests.Response) -> str:
    try:
        return response.text[:500]
    except Exception:  # pragma: no cover - 极端情况下取不到 body
        return ""
