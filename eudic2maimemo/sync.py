"""同步编排：欧路 → 墨墨云词本。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import Config
from .eudic import EudicClient, Word
from .http import SyncError
from .maimemo import MaimemoClient
from .notepad import (
    Block,
    count_words,
    extract_keys,
    merge_blocks,
    parse_blocks,
    render_blocks,
)

CN_TZ = timezone(timedelta(hours=8))


def to_cn_date(iso_time: str) -> str:
    """把欧路的 UTC 时间转成中国时区的日期（墨墨的日期分组按 UTC+8 更符合直觉）。"""
    if not iso_time:
        return "未知日期"
    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    except ValueError:
        return "未知日期"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CN_TZ).strftime("%Y-%m-%d")


def group_by_date(words: list[Word]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for word in words:
        grouped.setdefault(to_cn_date(word.add_time), []).append(word.word)
    return grouped


@dataclass
class SyncReport:
    mode: str
    fetched: int = 0
    added: int = 0
    skipped: int = 0
    total: int = 0
    blocks: int = 0
    requests: int = 0
    wrote: bool = False
    dry_run: bool = False
    added_words: list[str] = field(default_factory=list)
    orphaned: int = 0

    def summary(self) -> str:
        head = "预览" if self.dry_run else ("已写入" if self.wrote else "无变化")
        parts = [
            f"{head}｜模式={self.mode}",
            f"欧路匹配 {self.fetched}",
            f"新增 {self.added}",
        ]
        if self.skipped:
            parts.append(f"按规则跳过 {self.skipped}")
        parts += [
            f"云词本共 {self.total} 词 / {self.blocks} 段",
            f"请求 {self.requests} 次",
        ]
        return " · ".join(parts)


def run_sync(
    config: Config,
    *,
    mode: str = "incremental",
    dry_run: bool = False,
    limit: int | None = None,
    eudic: EudicClient | None = None,
    maimemo: MaimemoClient | None = None,
) -> SyncReport:
    if mode not in ("incremental", "full"):
        raise SyncError(f"未知模式：{mode}")

    config.require_maimemo()
    eudic = eudic or EudicClient(config.eudic_headers, language=config.language)
    maimemo = maimemo or MaimemoClient(config.maimemo_token)

    report = SyncReport(mode=mode, dry_run=dry_run)

    notepad = maimemo.get_notepad(config.maimemo_notepad_id)
    blocks: list[Block] = parse_blocks(notepad.content)
    existing = extract_keys(blocks)

    if mode == "full":
        words = eudic.fetch_all(config.eudic_category_ids)
        base_blocks: list[Block] = []
        orphaned = existing - {w.key for w in words}
        if orphaned:
            report.orphaned = len(orphaned)
            print(
                f"[warn] 云词本里有 {len(orphaned)} 个词不在欧路生词本中，"
                "全量重建会把这些词一起清掉（如不想清，请用增量模式）",
                file=sys.stderr,
            )
    else:
        words = eudic.fetch_new(config.eudic_category_ids, existing)
        base_blocks = blocks

    report.fetched = len(words)

    # 全量模式是从空白重建，云词本里已有的词也必须写回去（否则重建等于清空）；
    # 增量模式只写云词本里还没有的词。两种模式都做批内去重。
    fresh: list[Word] = []
    seen: set[str] = set()
    for word in words:
        if word.key in seen:
            continue
        if mode != "full" and word.key in existing:
            continue
        seen.add(word.key)
        fresh.append(word)

    if config.ignore_patterns:
        kept = [w for w in fresh if not config.ignored(w.word)]
        report.skipped = len(fresh) - len(kept)
        if report.skipped:
            print(f"[info] 按忽略规则跳过 {report.skipped} 个词条", file=sys.stderr)
        fresh = kept

    if limit is not None and 0 <= limit < len(fresh):
        if mode == "full":
            raise SyncError("--limit 不能和全量重建一起用：重建会按 limit 截断整个词本")
        print(f"[warn] 本次将新增 {len(fresh)} 个，按 --limit 只取最早的前 {limit} 个", file=sys.stderr)
        fresh = fresh[:limit]

    merged = merge_blocks(base_blocks, group_by_date(fresh))

    report.added = len(fresh)
    report.added_words = [w.word for w in fresh]
    report.total = count_words(merged)
    report.blocks = len([b for b in merged if b.date])
    report.requests = getattr(eudic.http, "request_count", 0) + getattr(
        maimemo.http, "request_count", 0
    )

    content = render_blocks(merged)
    if content == render_blocks(blocks):
        return report

    if dry_run:
        return report

    maimemo.update_notepad(
        config.maimemo_notepad_id,
        content,
        title=config.notepad_title,
        brief=config.notepad_brief,
    )
    report.wrote = True
    report.requests = getattr(eudic.http, "request_count", 0) + getattr(
        maimemo.http, "request_count", 0
    )
    return report
