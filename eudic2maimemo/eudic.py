"""欧路词典 Open API 客户端。

这里集中处理了同类项目最容易踩的三个坑：

1. page 从 **0** 开始（不是 1）。
2. 默认按添加时间**正序**返回，最老的在最前。
3. 单方向最多只能翻到 page 50（即 5100 条），超出直接 400。

而接口其实支持 ``sort=desc``（最新在前）。因此：

* 全量：正序 0..50 拿最老的 5100 条，再用倒序补最新，直到与正序区间重叠 → 取并集。
* 增量：直接用倒序从第 0 页读，整页都是已知词就停 → 通常 1~2 次请求。

只翻正序会在词本超过 5100 条时**静默丢失最新词**，这是同类项目的通病。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .http import HttpClient, RateLimiter, SyncError

BASE = "https://api.frdic.com/api/open/v1"
PAGE_SIZE = 100
MAX_PAGE = 50  # page 0..50 → 单方向上限 5100 条


@dataclass(frozen=True)
class Word:
    word: str
    add_time: str = ""
    star: int = 0
    phon: str = ""
    exp: str = ""

    @property
    def key(self) -> str:
        return self.word.strip().lower()


@dataclass(frozen=True)
class Book:
    id: str
    name: str
    add_time: str = ""


class EudicClient:
    def __init__(
        self,
        headers: dict[str, str],
        *,
        language: str = "en",
        http: HttpClient | None = None,
    ) -> None:
        self.headers = headers
        self.language = language
        self.http = http or HttpClient(limiter=RateLimiter())

    # ---------- 基础接口 ----------

    def list_books(self) -> list[Book]:
        response = self.http.request(
            "GET",
            f"{BASE}/studylist/category",
            headers=self.headers,
            params={"language": self.language},
        )
        data = response.json().get("data") or []
        return [Book(id=str(x.get("id")), name=x.get("name") or "", add_time=x.get("add_time") or "") for x in data]

    def _page(self, book_id: str, page: int, sort: str | None) -> list[Word]:
        params = {
            "language": self.language,
            "category_id": book_id,
            "page": page,
            "page_size": PAGE_SIZE,
        }
        if sort:
            params["sort"] = sort
        response = self.http.request(
            "GET", f"{BASE}/studylist/words", headers=self.headers, params=params
        )
        payload = response.json()
        raw = payload.get("data")
        if raw is None:
            message = payload.get("message") or "返回体缺少 data 字段"
            raise SyncError(f"欧路返回异常：{message}")
        return [
            Word(
                word=x.get("word") or "",
                add_time=x.get("add_time") or "",
                star=int(x.get("star") or 0),
                phon=x.get("phon") or "",
                exp=x.get("exp") or "",
            )
            for x in raw
            if (x.get("word") or "").strip()
        ]

    def lookup(self, word: str) -> dict | None:
        response = self.http.request(
            "GET",
            f"{BASE}/studylist/word",
            headers=self.headers,
            params={"language": self.language, "word": word},
        )
        try:
            return response.json()
        except ValueError:
            return None

    # ---------- 两个方向的翻页 ----------

    def fetch_asc(self, book_id: str, max_page: int = MAX_PAGE) -> list[Word]:
        """正序（最老在前）。"""
        words: list[Word] = []
        for page in range(0, max_page + 1):
            chunk = self._page(book_id, page, sort=None)
            if not chunk:
                break
            words.extend(chunk)
            if len(chunk) < PAGE_SIZE:
                break
        return words

    def fetch_desc(
        self,
        book_id: str,
        *,
        stop_at_time: str | None = None,
        known_keys: set[str] | None = None,
        max_page: int = MAX_PAGE,
    ) -> list[Word]:
        """倒序（最新在前）。

        stop_at_time: 读到比该时间更早的条目就停（与正序区间对齐）。
        known_keys:   某一页全部命中已知词就停（增量模式）。
        """
        words: list[Word] = []
        for page in range(0, max_page + 1):
            chunk = self._page(book_id, page, sort="desc")
            if not chunk:
                break

            if known_keys is not None:
                fresh = [w for w in chunk if w.key not in known_keys]
                if not fresh:
                    break
                words.extend(fresh)
            else:
                words.extend(chunk)

            if stop_at_time and (chunk[-1].add_time or "") <= stop_at_time:
                break
            if len(chunk) < PAGE_SIZE:
                break
        return words

    # ---------- 组合策略 ----------

    def fetch_all(self, book_ids: Iterable[str]) -> list[Word]:
        """全量：正序 5100 + 倒序补最新，取并集。"""
        merged: dict[str, Word] = {}
        for book_id in book_ids:
            asc = self.fetch_asc(book_id)
            for word in asc:
                merged.setdefault(word.key, word)
            if not asc:
                continue
            newest = max(w.add_time for w in asc)
            for word in self.fetch_desc(book_id, stop_at_time=newest):
                merged.setdefault(word.key, word)
        return sorted(merged.values(), key=lambda w: w.add_time)

    def fetch_new(self, book_ids: Iterable[str], known_keys: set[str]) -> list[Word]:
        """增量：倒序早停，只取已知集合之外的词。"""
        merged: dict[str, Word] = {}
        for book_id in book_ids:
            for word in self.fetch_desc(book_id, known_keys=known_keys):
                merged.setdefault(word.key, word)
        return sorted(merged.values(), key=lambda w: w.add_time)
