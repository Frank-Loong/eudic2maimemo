import json
import unittest
from unittest.mock import Mock, patch

import requests

from eudic2maimemo.notify import prepare, send


class PrepareTest(unittest.TestCase):
    def test_placeholder_in_url_becomes_get(self):
        req = prepare("https://example.com/send?msg={content}", "新增 3 个词")
        self.assertEqual(req.method, "GET")
        self.assertIn("%E6%96%B0%E5%A2%9E", req.url)
        self.assertNotIn("{content}", req.url)

    def test_body_becomes_post(self):
        req = prepare("https://example.com/hook", "完成", '{"message":"{content}"}')
        self.assertEqual(req.method, "POST")
        self.assertEqual(json.loads(req.kwargs["data"].decode()), {"message": "完成"})
        self.assertEqual(req.kwargs["headers"]["Content-Type"], "application/json")

    def test_plain_url_uses_query_param(self):
        req = prepare("https://example.com/hook", "完成")
        self.assertEqual(req.method, "GET")
        self.assertEqual(req.kwargs["params"], {"content": "完成"})

    def test_json_body_escapes_message(self):
        """回归：消息里的引号和换行不能破坏 JSON 结构。"""
        message = '新增 "quoted"\n第二行'
        req = prepare("https://example.com/hook", message, '{"msgtype":"text","text":{"content":"{content}"}}')
        payload = json.loads(req.kwargs["data"].decode())
        self.assertEqual(payload["text"]["content"], message)

    def test_non_json_body_falls_back_to_plain_replace(self):
        req = prepare("https://example.com/hook", "完成", "content={content}")
        self.assertEqual(req.kwargs["data"].decode(), "content=完成")

    def test_empty_url_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare("", "x")

    def test_send_without_url_is_noop(self):
        self.assertFalse(send("", "x"))


class SendTest(unittest.TestCase):
    def test_success_returns_true(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"errcode": 0, "errmsg": "ok"}
        with patch("eudic2maimemo.notify.requests.request", return_value=response) as req:
            self.assertTrue(send("https://example.com/hook", "完成", '{"m":"{content}"}'))
        self.assertEqual(req.call_args.kwargs["data"].decode(), '{"m": "完成"}')

    def test_errcode_nonzero_is_failure(self):
        """企业微信这类机器人出错也返回 200，必须看 errcode。"""
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"errcode": 93000, "errmsg": "invalid webhook url"}
        with patch("eudic2maimemo.notify.requests.request", return_value=response):
            self.assertFalse(send("https://example.com/hook", "完成"))

    def test_non_json_response_counts_as_success(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("not json")
        with patch("eudic2maimemo.notify.requests.request", return_value=response):
            self.assertTrue(send("https://example.com/hook", "完成"))

    def test_transport_error_is_swallowed(self):
        with patch(
            "eudic2maimemo.notify.requests.request", side_effect=requests.ConnectionError("x")
        ):
            self.assertFalse(send("https://example.com/hook", "完成"))

    def test_http_error_is_swallowed(self):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("500")
        with patch("eudic2maimemo.notify.requests.request", return_value=response):
            self.assertFalse(send("https://example.com/hook", "完成"))


if __name__ == "__main__":
    unittest.main()
