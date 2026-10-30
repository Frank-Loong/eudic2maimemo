"""配置读取与校验。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .http import SyncError

try:  # python-dotenv 是可选依赖，GHA 里用 secrets 注入即可
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


def _parse_routes(raw: str | None) -> dict[str, str]:
    """解析 `生词本ID=云词本ID` 形式的映射，多个用分号或换行隔开。"""
    routes: dict[str, str] = {}
    for part in re.split(r"[;\n]+", raw or ""):
        if "=" not in part:
            continue
        book, notepad = (x.strip() for x in part.split("=", 1))
        if not book or not notepad:
            continue
        if not notepad.startswith("np-"):
            raise SyncError(f"路由里的云词本 ID 应以 np- 开头：{notepad}")
        routes[book] = notepad
    return routes


def _int_or_zero(value: str | None) -> int:
    try:
        return max(0, int((value or "0").strip()))
    except ValueError:
        return 0


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _split_ids(raw: str | None, default: str = "0") -> list[str]:
    value = (raw or default).replace(" ", "")
    ids = [x for x in value.split(",") if x]
    return ids or [default]


@dataclass
class Config:
    eudic_api_key: str
    eudic_category_ids: list[str] = field(default_factory=lambda: ["0"])
    maimemo_token: str = ""
    maimemo_notepad_id: str = ""
    notepad_title: str = "欧路生词"
    notepad_brief: str = "来自欧路词典的生词"
    language: str = "en"
    ignore_patterns: list[str] = field(default_factory=list)
    notify_url: str = ""
    notify_body: str = ""
    notify_always: bool = False
    min_star: int = 0
    routes: dict[str, str] = field(default_factory=dict)
    keep_orphans: bool = False

    def ignored(self, word: str) -> bool:
        """词条是否命中忽略规则（正则，忽略大小写）。"""
        return any(re.search(pattern, word, re.IGNORECASE) for pattern in self.ignore_patterns)

    def compile_ignore_patterns(self) -> None:
        """启动时校验正则，避免跑到一半才发现写法有误。"""
        for pattern in self.ignore_patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise SyncError(f"忽略规则不是合法正则：{pattern!r}（{exc}）") from None

    @property
    def eudic_headers(self) -> dict[str, str]:
        return {
            "Authorization": self.eudic_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @property
    def maimemo_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.maimemo_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def require_maimemo(self) -> None:
        missing = [
            name
            for name, value in (
                ("MOMO_API_KEY", self.maimemo_token),
                ("MOMO_NOTEPAD_ID", self.maimemo_notepad_id),
            )
            if not value
        ]
        if missing:
            raise SyncError(f"缺少配置：{', '.join(missing)}")

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        if env is None:
            if load_dotenv is not None:
                load_dotenv()
            env = dict(os.environ)

        # 同时兼容本项目的命名与老项目的命名，降低迁移成本
        api_key = (
            env.get("EUDIC_API_KEY")
            or env.get("EUDIC_AUTHORIZATION")
            or ""
        ).strip()
        # 允许只填 token 本体，自动补 NIS 前缀
        if api_key and not api_key.upper().startswith("NIS"):
            api_key = f"NIS {api_key}"

        raw_ignore = env.get("IGNORE_PATTERNS") or ""
        ignore = [p.strip() for p in re.split(r"[\n;]+", raw_ignore) if p.strip()]

        config = cls(
            eudic_api_key=api_key,
            eudic_category_ids=_split_ids(
                env.get("EUDIC_CATEGORY_IDS") or env.get("EUDIC_CATEGORY_ID")
            ),
            maimemo_token=(env.get("MOMO_API_KEY") or env.get("MAIMEMO_TOKEN") or "").strip(),
            maimemo_notepad_id=(
                env.get("MOMO_NOTEPAD_ID") or env.get("MAIMEMO_NOTEPAD_ID") or ""
            ).strip(),
            notepad_title=env.get("MOMO_NOTEPAD_TITLE") or "欧路生词",
            notepad_brief=env.get("MOMO_NOTEPAD_BRIEF") or "来自欧路词典的生词",
            language=env.get("EUDIC_LANGUAGE") or "en",
            ignore_patterns=ignore,
            notify_url=(env.get("NOTIFY_URL") or "").strip(),
            notify_body=env.get("NOTIFY_BODY") or "",
            notify_always=_truthy(env.get("NOTIFY_ALWAYS")),
            min_star=_int_or_zero(env.get("MIN_STAR")),
            routes=_parse_routes(env.get("EUDIC_ROUTES")),
            keep_orphans=_truthy(env.get("KEEP_ORPHANS")),
        )
        config.compile_ignore_patterns()
        return config
