"""词形候选。

墨墨的词典接口只按精确拼写匹配，且只收录原形：`cat` 能查到，`cats` 查不到。
报告"哪些词背不了"时，如果直接拿原词去查，会把大量屈折变化误判成缺失。

这里做最朴素的规则还原，不引第三方词形库——够用，且没有额外依赖。
"""

from __future__ import annotations

VOWELS = set("aeiou")


def _undouble(stem: str) -> list[str]:
    """planned -> plan，running -> run。"""
    if len(stem) >= 2 and stem[-1] == stem[-2] and stem[-1] not in VOWELS and stem[-1] != "s":
        return [stem[:-1]]
    return []


def lemma_candidates(word: str) -> list[str]:
    """给一个词，返回可能的原形候选（去重，保留顺序）。"""
    w = word.strip().lower()
    if len(w) <= 2 or " " in w:
        return []

    out: list[str] = []

    def add(*items: str) -> None:
        for item in items:
            if len(item) >= 2 and item != w and item not in out:
                out.append(item)

    if w.endswith("ies") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3:
        add(w[:-2], w[:-1])
    elif w.endswith("s") and not w.endswith("ss"):
        add(w[:-1])

    if w.endswith("ied") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 3:
        stem = w[:-2]
        add(stem, stem + "e", *_undouble(stem))

    if w.endswith("ing") and len(w) > 4:
        stem = w[:-3]
        add(stem, stem + "e", *_undouble(stem))

    if w.endswith("ly") and len(w) > 4:
        add(w[:-2])

    if w.endswith("ier") and len(w) > 4:
        add(w[:-3] + "y")
    elif w.endswith(("er", "est")) and len(w) > 4:
        add(w[:-2] if w.endswith("er") else w[:-3])

    return out
