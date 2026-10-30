"""常驻服务模式：按固定间隔跑同步。

给 systemd、Docker、或者挂在自己机器上长期运行用。GitHub Actions 用户不需要这个。
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from .http import RateLimited, SyncError

CN_TZ = timezone(timedelta(hours=8))


def run_forever(
    task: Callable[[], bool],
    *,
    interval_seconds: float,
    max_runs: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_error: Callable[[Exception], None] | None = None,
) -> int:
    """循环执行 task，返回实际执行次数。

    task 返回 True 表示本轮正常，False 表示无变化（都不影响下一轮）。
    抛出的异常会被记录后吞掉，除非是限流——限流时直接结束进程，
    让 systemd / Docker 的重启策略接管，避免继续朝已封停的接口发请求。
    """
    runs = 0
    while max_runs is None or runs < max_runs:
        runs += 1
        started = datetime.now(CN_TZ)
        print(f"[serve] 第 {runs} 轮开始 {started:%Y-%m-%d %H:%M:%S}", file=sys.stderr, flush=True)
        try:
            task()
        except RateLimited:
            raise
        except SyncError as exc:
            print(f"[serve] 本轮失败：{exc}", file=sys.stderr, flush=True)
            if on_error:
                on_error(exc)
        except Exception as exc:  # 网络抖动之类，下一轮再看
            print(f"[serve] 本轮异常：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            if on_error:
                on_error(exc)

        if max_runs is not None and runs >= max_runs:
            break
        next_at = datetime.now(CN_TZ) + timedelta(seconds=interval_seconds)
        print(f"[serve] 下一轮 {next_at:%Y-%m-%d %H:%M:%S}", file=sys.stderr, flush=True)
        sleep(interval_seconds)

    return runs
