import unittest

from eudic2maimemo.eudic import PAGE_SIZE, EudicClient
from eudic2maimemo.http import SyncError


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeHttp:
    """按 (category_id, page, sort) 返回预置数据，并记录调用。"""

    def __init__(self, asc_pages, desc_pages):
        self.asc_pages = asc_pages
        self.desc_pages = desc_pages
        self.calls = []
        self.request_count = 0

    def request(self, method, url, *, headers=None, params=None, json_body=None, timeout=None):
        self.calls.append(dict(params or {}))
        self.request_count += 1
        page = int(params["page"])
        sort = params.get("sort")
        source = self.desc_pages if sort == "desc" else self.asc_pages
        return FakeResponse({"data": source.get(page, [])})


def make_words(count, start_day, prefix="w"):
    """生成 count 个词，日期逐条递增，便于断言顺序。"""
    out = []
    for i in range(count):
        day = start_day + i
        out.append(
            {
                "word": f"{prefix}{i}",
                "add_time": f"2026-01-{day:02d}T00:00:00Z" if day <= 28 else f"2026-02-{day - 28:02d}T00:00:00Z",
                "star": 1,
            }
        )
    return out


class PaginationTest(unittest.TestCase):
    def test_starts_at_page_zero(self):
        """page 必须从 0 开始，否则会漏掉最早的一整页。"""
        http = FakeHttp({0: make_words(3, 1)}, {})
        client = EudicClient({}, http=http)
        words = client.fetch_asc("0")
        self.assertEqual(len(words), 3)
        self.assertEqual(http.calls[0]["page"], 0)

    def test_stops_on_short_page(self):
        http = FakeHttp({0: make_words(PAGE_SIZE, 1), 1: make_words(5, 1, "x")}, {})
        client = EudicClient({}, http=http)
        words = client.fetch_asc("0")
        self.assertEqual(len(words), PAGE_SIZE + 5)
        self.assertEqual([c["page"] for c in http.calls], [0, 1])

    def test_desc_early_stop_when_page_fully_known(self):
        """增量：第一页全是已知词时应只发一次请求。"""
        page0 = make_words(4, 1, "known")
        http = FakeHttp({}, {0: page0})
        client = EudicClient({}, http=http)
        words = client.fetch_new(["0"], {"known0", "known1", "known2", "known3"})
        self.assertEqual(words, [])
        self.assertEqual(len(http.calls), 1)

    def test_desc_keeps_going_when_partially_known(self):
        page0 = make_words(4, 1, "new")
        page1 = make_words(2, 1, "old")
        http = FakeHttp({}, {0: page0, 1: page1})
        client = EudicClient({}, http=http)
        known = {"new2", "new3", "old0", "old1"}
        words = client.fetch_new(["0"], known)
        self.assertEqual({w.word for w in words}, {"new0", "new1"})

    def test_desc_stops_when_overlapping_asc_range(self):
        asc = make_words(2, 1, "old")
        desc_page0 = make_words(2, 5, "new")
        http = FakeHttp({0: asc}, {0: desc_page0, 1: make_words(2, 1, "overlap")})
        client = EudicClient({}, http=http)
        client.fetch_desc("0", stop_at_time="2026-01-02T00:00:00Z")
        self.assertEqual(len(http.calls), 1)


class FixedHttp:
    """对任何请求都返回同一份 payload。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.request_count = 0

    def request(self, method, url, *, headers=None, params=None, json_body=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        self.request_count += 1
        return FakeResponse(self.payload)


class UnparsableResponse:
    def json(self):
        raise ValueError("not json")


class UnparsableHttp(FixedHttp):
    def request(self, *args, **kwargs):
        return UnparsableResponse()


class MetadataTest(unittest.TestCase):
    def test_list_books(self):
        http = FixedHttp(
            {"data": [{"id": 0, "name": "我的生词本", "add_time": "2024-09-12T00:00:00Z"}]}
        )
        books = EudicClient({}, http=http).list_books()
        self.assertEqual(books[0].id, "0")
        self.assertEqual(books[0].name, "我的生词本")

    def test_list_books_handles_empty(self):
        self.assertEqual(EudicClient({}, http=FixedHttp({"data": []})).list_books(), [])

    def test_lookup_returns_payload(self):
        http = FixedHttp({"word": "cat", "category_ids": [0]})
        self.assertEqual(EudicClient({}, http=http).lookup("cat")["word"], "cat")

    def test_lookup_returns_none_on_bad_body(self):
        self.assertIsNone(EudicClient({}, http=UnparsableHttp({})).lookup("cat"))

    def test_missing_data_field_raises(self):
        http = FixedHttp({"message": "参数不正确：page"})
        with self.assertRaises(SyncError) as ctx:
            EudicClient({}, http=http).fetch_asc("0")
        self.assertIn("参数不正确", str(ctx.exception))


class FullSyncTest(unittest.TestCase):
    def test_union_of_asc_and_desc(self):
        """全量必须把正序与倒序补的最新词合并，且去重。"""
        asc = make_words(3, 1, "a")          # 最老的 3 个
        desc_new = make_words(2, 20, "b")    # 最新的 2 个
        http = FakeHttp({0: asc}, {0: desc_new})
        client = EudicClient({}, http=http)
        words = client.fetch_all(["0"])
        self.assertEqual({w.word for w in words}, {"a0", "a1", "a2", "b0", "b1"})
        self.assertEqual(len(words), 5)

    def test_deduplicates_same_word(self):
        asc = [{"word": "cat", "add_time": "2026-01-01T00:00:00Z"}]
        desc = [{"word": "Cat", "add_time": "2026-01-01T00:00:00Z"}]
        http = FakeHttp({0: asc}, {0: desc})
        client = EudicClient({}, http=http)
        words = client.fetch_all(["0"])
        self.assertEqual(len(words), 1)

    def test_sorted_by_add_time(self):
        http = FakeHttp({0: make_words(2, 10, "a")}, {0: make_words(2, 1, "b")})
        client = EudicClient({}, http=http)
        words = client.fetch_all(["0"])
        times = [w.add_time for w in words]
        self.assertEqual(times, sorted(times))


if __name__ == "__main__":
    unittest.main()
