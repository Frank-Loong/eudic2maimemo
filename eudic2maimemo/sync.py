"""同步编排：欧路 → 墨墨云词本。

支持把不同生词本写入不同云词本（`EUDIC_ROUTES`），未配置路由的书走默认云词本。
"""

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
ORPHAN_HEADER = "手动保留"


def to_cn_date(iso_time: str) -> str:
    """把欧路的 UTC 时间转成中国时区的日期。"""
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


@dataclass(frozen=True)
class Target:
    """一个云词本及其对应的欧路生词本集合。"""

    notepad_id: str
    book_ids: list[str]


def plan_targets(config: Config) -> list[Target]:
    """按 EUDIC_ROUTES 把生词本分组到云词本，未配置的书走默认云词本。"""
    groups: dict[str, list[str]] = {}
    for book_id in config.eudic_category_ids:
        notepad_id = config.routes.get(book_id) or config.maimemo_notepad_id
        groups.setdefault(notepad_id, []).append(book_id)
    return [
        Target(notepad_id=notepad_id, book_ids=book_ids)
        for notepad_id, book_ids in groups.items()
    ]


@dataclass
class SyncReport:
    mode: str
    fetched: int = 0
    added: int = 0
    skipped: int = 0
    low_star: int = 0
    total: int = 0
    blocks: int = 0
    requests: int = 0
    wrote: bool = False
    dry_run: bool = False
    added_words: list[str] = field(default_factory=list)
    orphaned: int = 0
    targets: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        head = "预览" if self.dry_run else ("已写入" if self.wrote else "无变化")
        parts = [f"{head}｜模式={self.mode}"]
        if len(self.targets) > 1:
            parts.append(f"{len(self.targets)} 个云词本")
        parts.append(f"欧路匹配 {self.fetched}")
        parts.append(f"新增 {self.added}")
        if self.skipped:
            parts.append(f"按规则跳过 {self.skipped}")
        if self.low_star:
            parts.append(f"低于星级未同步 {self.low_star}")
        parts.append(f"云词本共 {self.total} 词 / {self.blocks} 段")
        parts.append(f"请求 {self.requests} 次")
        return " · ".join(parts)


def _original_casing(blocks: list[Block]) -> dict[str, str]:
    """key -> 云词本里原本的写法，保留时维持原样。"""
    mapping: dict[str, str] = {}
    for block in blocks:
        for word in block.words:
            mapping.setdefault(word.strip().lower(), word)
    return mapping


def _sync_one(
    config: Config,
    target: Target,
    *,
    mode: str,
    dry_run: bool,
    limit: int | None,
    eudic: EudicClient,
    maimemo: MaimemoClient,
    report: SyncReport,
) -> None:
    notepad = maimemo.get_notepad(target.notepad_id)
    blocks = parse_blocks(notepad.content)
    existing = extract_keys(blocks)

    if mode == "full":
        words = eudic.fetch_all(target.book_ids)
        eudic_keys = {w.key for w in words}
        orphaned_keys = existing - eudic_keys

        base_blocks: list[Block] = []
        if orphaned_keys and config.keep_orphans:
            casing = _original_casing(blocks)
            kept = [casing[key] for key in sorted(orphaned_keys)]
            base_blocks = [Block(date=ORPHAN_HEADER, words=kept)]
            print(
                f"[info] 保留云词本中欧路没有的 {len(kept)} 个词条，置于「{ORPHAN_HEADER}」段",
                file=sys.stderr,
            )
        elif orphaned_keys:
            report.orphaned += len(orphaned_keys)
            print(
                f"[warn] 云词本里有 {len(orphaned_keys)} 个词不在欧路生词本中，"
                "全量重建会清掉它们（加 --keep-orphans 可保留，或用增量模式）",
                file=sys.stderr,
            )
    else:
        words = eudic.fetch_new(target.book_ids, existing)
        base_blocks = blocks

    report.fetched += len(words)

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
        kept_words = [w for w in fresh if not config.ignored(w.word)]
        report.skipped += len(fresh) - len(kept_words)
        fresh = kept_words

    if config.min_star > 0:
        kept_words = [w for w in fresh if w.star >= config.min_star]
        report.low_star += len(fresh) - len(kept_words)
        fresh = kept_words

    if limit is not None and 0 <= limit < len(fresh):
        if mode == "full":
            raise SyncError("--limit 不能和全量重建一起用：重建会按 limit 截断整个词本")
        fresh = fresh[:limit]

    merged = merge_blocks(base_blocks, group_by_date(fresh))
    report.added += len(fresh)
    report.added_words.extend(w.word for w in fresh)
    report.total += count_words(merged)
    report.blocks += len([b for b in merged if b.date])

    content = render_blocks(merged)
    if content == render_blocks(blocks) or dry_run:
        return

    maimemo.update_notepad(
        target.notepad_id,
        content,
        # 沿用云词本原有的标题与简介，多目标时才不会把别人的词本改名
        title=notepad.title or config.notepad_title,
        brief=notepad.brief or config.notepad_brief,
    )
    report.wrote = True


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
    targets = plan_targets(config)
    failures: list[str] = []

    for target in targets:
        try:
            _sync_one(
                config,
                target,
                mode=mode,
                dry_run=dry_run,
                limit=limit,
                eudic=eudic,
                maimemo=maimemo,
                report=report,
            )
        except SyncError as exc:
            failures.append(f"{target.notepad_id}: {exc}")
            print(f"[error] 云词本 {target.notepad_id} 同步失败：{exc}", file=sys.stderr)
            continue
        report.targets.append(
            {"notepad_id": target.notepad_id, "book_ids": target.book_ids}
        )

    report.requests = getattr(eudic.http, "request_count", 0) + getattr(
        maimemo.http, "request_count", 0
    )

    if failures:
        raise SyncError(f"{len(failures)} 个云词本同步失败：" + "；".join(failures))
    return report
