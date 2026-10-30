"""生词本画像：规模、增长节奏、标记习惯、数据缺口。

这些数字用来回答两个问题：值不值得整理，以及整理该从哪儿下手。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .eudic import Word

CJK = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class WordStats:
    total: int = 0
    unique: int = 0
    first_date: str = "-"
    last_date: str = "-"
    by_month: dict[str, int] = field(default_factory=dict)
    stars: dict[int, int] = field(default_factory=dict)
    missing_phon: int = 0
    missing_exp: int = 0
    phrases: int = 0
    chinese: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "unique": self.unique,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "by_month": self.by_month,
            "stars": self.stars,
            "missing_phon": self.missing_phon,
            "missing_exp": self.missing_exp,
            "phrases": self.phrases,
            "chinese": self.chinese,
        }


def summarize(words: list[Word]) -> WordStats:
    if not words:
        return WordStats()

    keys = {w.key for w in words}
    times = sorted(w.add_time for w in words if w.add_time)
    months = Counter(t[:7] for t in times if len(t) >= 7)
    stars = Counter(w.star for w in words)

    return WordStats(
        total=len(words),
        unique=len(keys),
        first_date=times[0][:10] if times else "-",
        last_date=times[-1][:10] if times else "-",
        by_month=dict(sorted(months.items())),
        stars=dict(sorted(stars.items())),
        missing_phon=sum(1 for w in words if not w.phon.strip()),
        missing_exp=sum(1 for w in words if not w.exp.strip()),
        phrases=sum(1 for w in words if " " in w.word.strip()),
        chinese=sum(1 for w in words if CJK.search(w.word)),
    )


def format_summary(stats: WordStats, *, recent_months: int = 12) -> str:
    lines = [
        f"总词数 {stats.total}（去重 {stats.unique}）",
        f"时间跨度 {stats.first_date} ~ {stats.last_date}",
        "",
        f"星级分布：{_fmt_pairs(stats.stars)}",
        "",
        "数据缺口：",
        f"  无音标 {stats.missing_phon} · 无释义 {stats.missing_exp}",
        f"  词组（含空格）{stats.phrases} · 中文词条 {stats.chinese}",
    ]

    months = list(stats.by_month.items())
    if months:
        tail = months[-recent_months:]
        peak = max(v for _, v in tail) or 1
        lines += ["", f"最近 {len(tail)} 个月新增："]
        for month, count in tail:
            bar = "█" * max(1, round(count / peak * 24)) if count else ""
            lines.append(f"  {month}  {count:>6}  {bar}")

    return "\n".join(lines)


def _fmt_pairs(mapping: dict) -> str:
    if not mapping:
        return "-"
    return " · ".join(f"{k}星 {v}" for k, v in mapping.items())
