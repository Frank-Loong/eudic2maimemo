"""云词本内容的解析、渲染与增量合并。

内容格式（与欧路/墨墨生态里通行的写法一致）::

    #2026-10-28
    relief groove
    profile shift coefficient

    #2026-10-29
    against
    chargeable

`#YYYY-MM-DD` 是分组标记，墨墨会把它当作章节标题，日期之后的每行就是一个词条。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    date: str
    words: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.words = [w.strip() for w in self.words if w and w.strip()]


def word_key(word: str) -> str:
    return word.strip().lower()


def parse_blocks(content: str | None) -> list[Block]:
    """把 content 拆成日期块。没有日期头的行会归入 date="" 的块并原样保留。"""
    blocks: list[Block] = []
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            blocks.append(Block(date=line.lstrip("#").strip(), words=[]))
        elif blocks:
            blocks[-1].words.append(line)
        else:
            blocks.append(Block(date="", words=[line]))
    return blocks


def render_blocks(blocks: list[Block]) -> str:
    out: list[str] = []
    for block in blocks:
        if block.date:
            out.append(f"#{block.date}")
        out.extend(block.words)
        out.append("")
    return "\n".join(out).rstrip() + "\n" if out else ""


def extract_keys(blocks: list[Block]) -> set[str]:
    return {word_key(w) for block in blocks for w in block.words}


def count_words(blocks: list[Block]) -> int:
    return sum(len(block.words) for block in blocks)


def merge_blocks(blocks: list[Block], words_by_date: dict[str, list[str]]) -> list[Block]:
    """把按日期分组的新词并入现有块，尽量接续到已有日期的段落后面。

    返回全新的块列表，不修改入参（调用方需要拿原内容做"是否变化"的比较）。
    """
    result = [Block(date=block.date, words=list(block.words)) for block in blocks]
    for date in sorted(words_by_date):
        words = [w.strip() for w in words_by_date[date] if w and w.strip()]
        if not words:
            continue
        if result and result[-1].date == date:
            result[-1].words.extend(words)
        else:
            result.append(Block(date=date, words=words))
    return result
