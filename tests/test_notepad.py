import unittest

from eudic2maimemo.notepad import (
    Block,
    count_words,
    extract_keys,
    merge_blocks,
    parse_blocks,
    render_blocks,
)


class ParseRenderTest(unittest.TestCase):
    def test_roundtrip(self):
        content = "#2026-10-28\nrelief groove\nprofile shift coefficient\n\n#2026-10-29\nagainst\n"
        blocks = parse_blocks(content)
        self.assertEqual([b.date for b in blocks], ["2026-10-28", "2026-10-29"])
        self.assertEqual(render_blocks(blocks), content)

    def test_empty(self):
        self.assertEqual(parse_blocks(""), [])
        self.assertEqual(render_blocks([]), "")

    def test_lines_without_header_are_preserved(self):
        blocks = parse_blocks("loose word\n\n#2026-01-01\ncat\n")
        self.assertEqual(blocks[0].date, "")
        self.assertEqual(blocks[0].words, ["loose word"])
        self.assertEqual(blocks[1].words, ["cat"])

    def test_blank_lines_are_dropped(self):
        blocks = parse_blocks("#2026-01-01\n\na\n\n\nb\n")
        self.assertEqual(blocks[0].words, ["a", "b"])

    def test_extract_keys_is_case_insensitive(self):
        blocks = [Block("2026-01-01", ["Cat", "dog"])]
        self.assertEqual(extract_keys(blocks), {"cat", "dog"})

    def test_count_words(self):
        blocks = [Block("d1", ["a", "b"]), Block("d2", ["c"])]
        self.assertEqual(count_words(blocks), 3)


class MergeTest(unittest.TestCase):
    def test_append_to_same_last_date(self):
        blocks = [Block("2026-10-29", ["against"])]
        merged = merge_blocks(blocks, {"2026-10-29": ["chargeable"]})
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].words, ["against", "chargeable"])

    def test_append_new_date(self):
        blocks = [Block("2026-10-29", ["against"])]
        merged = merge_blocks(blocks, {"2026-10-30": ["mesh"]})
        self.assertEqual([b.date for b in merged], ["2026-10-29", "2026-10-30"])
        self.assertEqual(merged[-1].words, ["mesh"])

    def test_multiple_dates_sorted(self):
        merged = merge_blocks([], {"2026-10-30": ["b"], "2026-10-28": ["a"]})
        self.assertEqual([b.date for b in merged], ["2026-10-28", "2026-10-30"])

    def test_does_not_mutate_input(self):
        blocks = [Block("2026-10-29", ["against"])]
        merge_blocks(blocks, {"2026-10-29": ["chargeable"]})
        self.assertEqual(blocks[0].words, ["against"])


if __name__ == "__main__":
    unittest.main()
