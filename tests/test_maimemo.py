import unittest

from eudic2maimemo.http import ApiError, AuthError, SyncError
from eudic2maimemo.maimemo import MaimemoClient


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.request_count = 0

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        self.request_count += 1
        if self.error:
            raise self.error
        return FakeResponse(self.response)


class ListNotepadsTest(unittest.TestCase):
    def test_parses_list(self):
        http = FakeHttp(
            {
                "success": True,
                "data": {
                    "notepads": [
                        {"id": "np-1", "title": "欧路生词", "content": "cat"},
                        {"id": "np-2", "title": "别的"},
                    ]
                },
            }
        )
        notepads = MaimemoClient("tok", http=http).list_notepads()
        self.assertEqual([n.id for n in notepads], ["np-1", "np-2"])
        self.assertEqual(notepads[1].content, "")

    def test_failure_payload_raises(self):
        http = FakeHttp({"success": False, "errors": [{"msg": "token 无效"}]})
        with self.assertRaises(SyncError) as ctx:
            MaimemoClient("tok", http=http).list_notepads()
        self.assertIn("token 无效", str(ctx.exception))


class GetNotepadTest(unittest.TestCase):
    def test_returns_content(self):
        http = FakeHttp(
            {"success": True, "data": {"notepad": {"id": "np-1", "title": "t", "content": "#2026-01-01\ncat\n"}}}
        )
        notepad = MaimemoClient("tok", http=http).get_notepad("np-1")
        self.assertIn("cat", notepad.content)
        self.assertEqual(notepad.title, "t")

    def test_404_gives_actionable_message(self):
        http = FakeHttp(error=ApiError(404, "not found"))
        with self.assertRaises(SyncError) as ctx:
            MaimemoClient("tok", http=http).get_notepad("np-missing")
        self.assertIn("doctor", str(ctx.exception))

    def test_auth_error_becomes_sync_error(self):
        http = FakeHttp(error=AuthError("bad token"))
        with self.assertRaises(SyncError):
            MaimemoClient("tok", http=http).get_notepad("np-1")

    def test_missing_notepad_id(self):
        with self.assertRaises(SyncError):
            MaimemoClient("tok", http=FakeHttp()).get_notepad("")


class LookupSpellingsTest(unittest.TestCase):
    def test_returns_matched_lowercase(self):
        http = FakeHttp(
            {"success": True, "data": {"voc": [{"spelling": "Cat"}, {"spelling": "dog"}]}}
        )
        found = MaimemoClient("tok", http=http).lookup_spellings(["cat", "dog", "cnc"])
        self.assertEqual(found, {"cat", "dog"})

    def test_batches_requests(self):
        http = FakeHttp({"success": True, "data": {"voc": []}})
        MaimemoClient("tok", http=http).lookup_spellings([f"w{i}" for i in range(2500)])
        self.assertEqual(len(http.calls), 3)

    def test_deduplicates_input(self):
        http = FakeHttp({"success": True, "data": {"voc": [{"spelling": "cat"}]}})
        MaimemoClient("tok", http=http).lookup_spellings(["cat", "cat", "CAT"])
        sent = http.calls[0]["json_body"]["spellings"]
        self.assertEqual(sent, ["cat", "CAT"])


class UpdateNotepadTest(unittest.TestCase):
    def test_sends_content_under_notepad_key(self):
        http = FakeHttp({"success": True, "data": {"notepad": {"id": "np-1", "title": "欧路生词"}}})
        MaimemoClient("tok", http=http).update_notepad(
            "np-1", "#2026-01-01\ncat\n", title="欧路生词", brief="来自欧路词典的生词"
        )
        body = http.calls[0]["json_body"]["notepad"]
        self.assertEqual(body["status"], "UNPUBLISHED")
        self.assertIn("cat", body["content"])
        self.assertEqual(body["title"], "欧路生词")

    def test_auth_error_becomes_sync_error(self):
        http = FakeHttp(error=AuthError("bad token"))
        with self.assertRaises(SyncError):
            MaimemoClient("tok", http=http).update_notepad("np-1", "x", title="t", brief="b")

    def test_empty_token_is_rejected(self):
        with self.assertRaises(SyncError):
            MaimemoClient("")


if __name__ == "__main__":
    unittest.main()
