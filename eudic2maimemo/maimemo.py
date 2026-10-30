"""墨墨背单词开放 API 客户端（只用到云词本相关能力）。"""

from __future__ import annotations

from dataclasses import dataclass

from .http import ApiError, AuthError, HttpClient, SyncError

BASE = "https://open.maimemo.com/open/api/v1"


@dataclass(frozen=True)
class Notepad:
    id: str
    title: str
    content: str
    updated_time: str = ""


class MaimemoClient:
    def __init__(self, token: str, http: HttpClient | None = None) -> None:
        if not token:
            raise SyncError("缺少墨墨 token")
        self.token = token
        self.http = http or HttpClient()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _unwrap(self, response) -> dict:
        payload = response.json()
        if not payload.get("success", True):
            errors = payload.get("errors") or []
            detail = "; ".join(str(e.get("msg") or e) for e in errors) or str(payload)
            raise SyncError(f"墨墨接口返回失败：{detail}")
        return payload.get("data") or {}

    def list_notepads(self, limit: int = 50, offset: int = 0) -> list[Notepad]:
        response = self.http.request(
            "GET",
            f"{BASE}/notepads",
            headers=self.headers,
            params={"limits": limit, "offset": offset},
        )
        data = self._unwrap(response)
        return [
            Notepad(
                id=x.get("id") or "",
                title=x.get("title") or "",
                content=x.get("content") or "",
                updated_time=x.get("updated_time") or "",
            )
            for x in (data.get("notepads") or [])
        ]

    def get_notepad(self, notepad_id: str) -> Notepad:
        if not notepad_id:
            raise SyncError("缺少 MOMO_NOTEPAD_ID")
        try:
            response = self.http.request(
                "GET", f"{BASE}/notepads/{notepad_id}", headers=self.headers
            )
        except ApiError as exc:
            if exc.status == 404:
                raise SyncError(
                    f"云词本 {notepad_id} 不存在。用 `python -m eudic2maimemo doctor` 查看可用的 notepad id"
                ) from None
            raise
        except AuthError:
            raise SyncError("墨墨 token 无效或已过期，请重新生成") from None

        data = self._unwrap(response)
        notepad = data.get("notepad") or {}
        return Notepad(
            id=notepad.get("id") or notepad_id,
            title=notepad.get("title") or "",
            content=notepad.get("content") or "",
            updated_time=notepad.get("updated_time") or "",
        )

    def update_notepad(
        self, notepad_id: str, content: str, *, title: str, brief: str
    ) -> Notepad:
        payload = {
            "notepad": {
                "status": "UNPUBLISHED",
                "content": content,
                "title": title,
                "brief": brief,
                "tags": ["自用"],
            }
        }
        try:
            response = self.http.request(
                "POST",
                f"{BASE}/notepads/{notepad_id}",
                headers=self.headers,
                json_body=payload,
                timeout=180,
            )
        except AuthError:
            raise SyncError("墨墨 token 无效或已过期，请重新生成") from None

        data = self._unwrap(response)
        notepad = data.get("notepad") or {}
        return Notepad(
            id=notepad.get("id") or notepad_id,
            title=notepad.get("title") or title,
            content=notepad.get("content") or "",
            updated_time=notepad.get("updated_time") or "",
        )
