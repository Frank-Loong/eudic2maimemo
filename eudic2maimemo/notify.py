"""同步结果通知。

支持三种写法，按 URL / body 里有没有 `{content}` 自动判断：

* URL 里带占位符：GET 替换后的地址（Server 酱这类）
* 配了 body：POST JSON，body 里的占位符被替换
* 都没配：GET 带 `content` 查询参数

通知失败只打印警告，不影响同步结果。
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from urllib.parse import quote

import requests

TIMEOUT = 20


@dataclass
class Notification:
    method: str
    url: str
    kwargs: dict


def _fill(node, message: str):
    """在 JSON 结构里逐层替换占位符，保证转义正确。"""
    if isinstance(node, str):
        return node.replace("{content}", message)
    if isinstance(node, list):
        return [_fill(item, message) for item in node]
    if isinstance(node, dict):
        return {key: _fill(value, message) for key, value in node.items()}
    return node


def prepare(url: str, message: str, body: str | None = None) -> Notification:
    """把配置和消息拼成一次具体的请求（纯函数，便于测试）。

    正文如果是 JSON（企业微信机器人、Server 酱这类），会先解析再替换占位符，
    这样消息里带引号、换行也不会破坏 JSON 结构；不是 JSON 就按纯文本替换。
    """
    url = (url or "").strip()
    if not url:
        raise ValueError("通知地址为空")

    if "{content}" in url:
        return Notification("GET", url.replace("{content}", quote(message)), {})

    if body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            data = body.replace("{content}", message).encode("utf-8")
        else:
            data = json.dumps(_fill(payload, message), ensure_ascii=False).encode("utf-8")
        return Notification(
            "POST",
            url,
            {"data": data, "headers": {"Content-Type": "application/json"}},
        )

    return Notification("GET", url, {"params": {"content": message}})


def send(url: str, message: str, body: str | None = None) -> bool:
    """发送通知，成功返回 True。异常一律吞掉，只记录。"""
    if not url:
        return False
    try:
        request = prepare(url, message, body)
        response = requests.request(
            request.method, request.url, timeout=TIMEOUT, **request.kwargs
        )
        response.raise_for_status()

        # 企业微信、钉钉这类机器人即使出错也返回 200，真正的结果在 errcode 里
        try:
            payload = response.json()
        except ValueError:
            return True
        if isinstance(payload, dict) and payload.get("errcode") not in (None, 0):
            print(
                f"[warn] 通知被拒：errcode={payload.get('errcode')} {payload.get('errmsg', '')}",
                file=sys.stderr,
            )
            return False
        return True
    except Exception as exc:  # 通知是附属功能，不该拖垮同步
        print(f"[warn] 通知发送失败：{exc}", file=sys.stderr)
        return False
