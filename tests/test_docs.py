"""文档与代码的一致性检查。

这类问题出现过两次（功能写进文档却没给用法、代码加了参数文档没跟上），
靠人记不住，交给 CI。
"""

import argparse
import re
import unittest
from pathlib import Path

from eudic2maimemo import cli

ROOT = Path(__file__).resolve().parents[1]
ZH = (ROOT / "README.md").read_text(encoding="utf-8")
EN = (ROOT / "README.en.md").read_text(encoding="utf-8")


def _section(text, start, end):
    return text[text.index(start) : text.index(end)]


def _cli_flags():
    parser = cli.build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    flags = set()
    for sub in subs.choices.values():
        for action in sub._actions:
            flags.update(
                opt
                for opt in action.option_strings
                if opt.startswith("--") and opt not in ("--help", "--max-runs")
            )
    return flags


class ConfigTableTest(unittest.TestCase):
    def setUp(self):
        self.zh_vars = re.findall(
            r"^\| `([A-Z_]+)` \|",
            _section(ZH, "## 配置项", "### 过滤掉"),
            re.M,
        )
        self.en_vars = re.findall(
            r"^\| `([A-Z_]+)` \|",
            _section(EN, "## Configuration", "### Filtering"),
            re.M,
        )

    def test_tables_match(self):
        self.assertEqual(self.zh_vars, self.en_vars)

    def test_every_documented_variable_is_read_by_code(self):
        source = "".join(
            (ROOT / "eudic2maimemo" / name).read_text(encoding="utf-8")
            for name in ("config.py", "cli.py")
        )
        missing = [v for v in self.zh_vars if v not in source]
        self.assertEqual(missing, [], f"文档里写了但代码没读：{missing}")

    def test_every_code_variable_is_documented(self):
        source = (ROOT / "eudic2maimemo" / "config.py").read_text(encoding="utf-8")
        read = set(re.findall(r'env\.get\("([A-Z_]+)"\)', source))
        read |= set(
            re.findall(
                r'float\(os\.getenv\("([A-Z_]+)"\)',
                (ROOT / "eudic2maimemo" / "cli.py").read_text(encoding="utf-8"),
            )
        )
        # 允许写在表格之外的兼容别名，只要文档里提到即可
        undocumented = sorted(v for v in read if v not in ZH)
        self.assertEqual(undocumented, [], f"代码读取但文档没写：{undocumented}")


class CommandDocsTest(unittest.TestCase):
    def test_every_cli_flag_is_documented(self):
        missing = sorted(f for f in _cli_flags() if f not in ZH and f not in EN)
        self.assertEqual(missing, [], f"未写入文档的参数：{missing}")

    def test_commands_in_table_are_real(self):
        table = _section(ZH, "## 常用命令", "## 已知限制")
        commands = re.findall(r"^\| `([a-z][^`]*)` \|", table, re.M)
        self.assertGreaterEqual(len(commands), 5)
        parser = cli.build_parser()
        for command in commands:
            head = command.split()[0]
            # 只验证子命令存在，参数由上一用例覆盖
            self.assertIn(head, parser._subparsers._group_actions[0].choices)


class StructureTest(unittest.TestCase):
    def test_heading_counts_match(self):
        self.assertEqual(ZH.count("\n## "), EN.count("\n## "))
        self.assertEqual(ZH.count("\n### "), EN.count("\n### "))

    def test_code_fences_are_labelled(self):
        for name, text in (("README.md", ZH), ("README.en.md", EN)):
            inside = False
            unlabelled = 0
            for line in text.splitlines():
                if line.startswith("```"):
                    if not inside and line.strip() == "```":
                        unlabelled += 1
                    inside = not inside
            self.assertEqual(unlabelled, 0, f"{name} 有 {unlabelled} 个未标语言的代码块")


if __name__ == "__main__":
    unittest.main()
