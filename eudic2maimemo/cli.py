"""命令行入口。

    python -m eudic2maimemo sync           增量同步（默认）
    python -m eudic2maimemo sync --full    全量重建
    python -m eudic2maimemo serve          常驻，按间隔同步
    python -m eudic2maimemo doctor         连通性与配置自检
    python -m eudic2maimemo stats          词本画像
    python -m eudic2maimemo export         导出当前欧路全量词表
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from dataclasses import asdict

from . import notify
from .config import Config
from .eudic import EudicClient
from .http import RateLimited, SyncError
from .maimemo import MaimemoClient
from .notepad import count_words, extract_keys, parse_blocks
from .service import run_forever
from .stats import format_summary, summarize
from .sync import run_sync


def _notify(config: Config, message: str) -> None:
    if config.notify_url:
        notify.send(config.notify_url, message, config.notify_body or None)


def cmd_sync(args: argparse.Namespace) -> int:
    config = Config.from_env()
    if args.ignore:
        config.ignore_patterns.extend(args.ignore)
        config.compile_ignore_patterns()

    try:
        report = _run_once(config, args, verbose=not args.json)
    except SyncError as exc:
        _notify(config, f"同步失败：{exc}")
        raise
    line = report.summary()

    if args.json:
        # 只要 JSON 能直接进管道，人读信息在 verbose=False 时已经静音
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))

    if not args.dry_run and _should_notify(config, report):
        _notify(config, line)
    return 0


def _should_notify(config: Config, report) -> bool:
    """默认只在有新增词时推送，避免每天一条"无变化"把群刷满。

    失败一定会推（在异常分支里）。想每轮都收到，设 NOTIFY_ALWAYS=1。
    """
    return config.notify_always or report.added > 0


def _run_once(config: Config, args: argparse.Namespace, *, verbose: bool = True):
    report = run_sync(
        config,
        mode="full" if getattr(args, "full", False) else "incremental",
        dry_run=getattr(args, "dry_run", False),
        limit=getattr(args, "limit", None),
    )
    if verbose:
        print(f"[done] {report.summary()}")
        if report.added_words and not getattr(args, "quiet", False):
            preview = ", ".join(report.added_words[:20])
            more = " ..." if len(report.added_words) > 20 else ""
            print(f"[new] {preview}{more}")
    return report


def cmd_serve(args: argparse.Namespace) -> int:
    """常驻模式。给 systemd / Docker 用，按固定间隔跑增量同步。"""
    config = Config.from_env()
    if args.ignore:
        config.ignore_patterns.extend(args.ignore)
        config.compile_ignore_patterns()

    interval_hours = args.interval
    if interval_hours is None:
        try:
            interval_hours = float(os.getenv("SYNC_INTERVAL_HOURS") or 24)
        except ValueError:
            interval_hours = 24.0
    interval_seconds = max(60.0, interval_hours * 3600)

    print(
        f"[serve] 启动，间隔 {interval_hours:g} 小时，"
        f"生词本 {', '.join(config.eudic_category_ids)}",
        file=sys.stderr,
        flush=True,
    )

    def task() -> bool:
        try:
            report = _run_once(config, args, verbose=not args.quiet)
        except SyncError as exc:
            _notify(config, f"同步失败：{exc}")
            raise
        if _should_notify(config, report):
            _notify(config, report.summary())
        return report.added > 0

    try:
        run_forever(
            task,
            interval_seconds=interval_seconds,
            max_runs=args.max_runs,
            on_error=lambda exc: _notify(config, f"同步失败：{exc}"),
        )
    except RateLimited as exc:
        print(f"[serve] 触发限流，退出让重启策略接管：{exc}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("[serve] 收到中断，退出", file=sys.stderr, flush=True)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = Config.from_env()
    ok = True

    print("== 配置 ==")
    print(f"欧路 token      : {'已设置' if config.eudic_api_key else '缺失'}")
    print(f"欧路生词本 ID   : {', '.join(config.eudic_category_ids)}")
    print(f"墨墨 token      : {'已设置' if config.maimemo_token else '缺失'}")
    print(f"墨墨云词本 ID   : {config.maimemo_notepad_id or '缺失'}")

    if not config.eudic_api_key and not config.maimemo_token:
        print("\n[error] 欧路和墨墨的密钥都没设置，先把其中一个填进 .env 或仓库 Secrets")
        return 2

    eudic = None
    if config.eudic_api_key:
        print("\n== 欧路词典 ==")
        eudic = EudicClient(config.eudic_headers, language=config.language)
        try:
            books = eudic.list_books()
        except SyncError as exc:
            print(f"[fail] 欧路鉴权失败：{exc}")
            return 2
        for book in books:
            mark = " *" if book.id in config.eudic_category_ids else ""
            print(f"  {book.id:>20}  {book.name}{mark}")

        for book_id in config.eudic_category_ids:
            try:
                head = eudic.fetch_desc(book_id, max_page=0)
                tail = eudic.fetch_asc(book_id, max_page=0)
            except SyncError as exc:
                print(f"[fail] 生词本 {book_id} 读取失败：{exc}")
                ok = False
                continue
            newest = head[0].add_time[:10] if head else "-"
            oldest = tail[0].add_time[:10] if tail else "-"
            print(f"  生词本 {book_id}: 最新 {newest} / 最老 {oldest}")
    else:
        print("\n== 欧路词典 ==\n  跳过（未设置 EUDIC_API_KEY）")

    notepad_words: set[str] = set()
    if config.maimemo_token:
        print("\n== 墨墨背单词 ==")
        maimemo = MaimemoClient(config.maimemo_token)
        try:
            notepads = maimemo.list_notepads()
        except SyncError as exc:
            print(f"[fail] 墨墨鉴权失败：{exc}")
            return 2
        for np in notepads:
            mark = " *" if np.id == config.maimemo_notepad_id else ""
            print(f"  {np.title or '(无标题)'}{mark}  {np.id}")

        if not config.maimemo_notepad_id:
            print("\n[action] 上面每个 np- 开头的字符串就是一个云词本的 ID")
            print("         挑一个填到 MOMO_NOTEPAD_ID（Secrets 或 .env），再跑一次")
            return 1

        try:
            notepad = maimemo.get_notepad(config.maimemo_notepad_id)
        except SyncError as exc:
            print(f"[fail] 读取云词本失败：{exc}")
            return 2
        blocks = parse_blocks(notepad.content)
        notepad_words = extract_keys(blocks)
        print(f"  当前云词本: {notepad.title}，{count_words(blocks)} 词 / {len(blocks)} 段")
    else:
        print("\n== 墨墨背单词 ==\n  跳过（未设置 MOMO_API_KEY）")

    if args.deep:
        if eudic is None or not config.maimemo_notepad_id:
            print("\n[warn] --deep 需要欧路密钥和云词本 ID 都配好")
            return 1
        print("\n== 覆盖度（深度检查，会翻完整个生词本）==")
        words = eudic.fetch_all(config.eudic_category_ids)
        eudic_keys = {w.key for w in words}
        missing = eudic_keys - notepad_words
        extra = notepad_words - eudic_keys
        print(f"  欧路全量: {len(words)} 词（本次请求 {eudic.http.request_count} 次）")
        print(f"  云词本已有: {len(notepad_words & eudic_keys)}")
        print(f"  尚未同步: {len(missing)}")
        if extra:
            print(f"  云词本独有（欧路里没有）: {len(extra)}")
        if missing:
            preview = ", ".join(sorted(missing)[:20])
            print(f"  缺失示例: {preview}")
            ok = False

    print("\n[ok]" if ok else "\n[warn] 存在待处理项")
    return 0 if ok else 1


def cmd_export(args: argparse.Namespace) -> int:
    config = Config.from_env()
    eudic = EudicClient(config.eudic_headers, language=config.language)
    words = eudic.fetch_all(config.eudic_category_ids)
    words.sort(key=lambda w: w.add_time)

    if not args.out:
        for word in words:
            print(word.word)
        return 0

    if args.format == "csv":
        import csv

        def clean(exp: str) -> str:
            # 欧路释义里带 <br> 之类的标签，去掉后把多余空白压成一个空格
            text = re.sub(r"<[^>]+>", " ", exp or "")
            return re.sub(r"\s+", " ", text).strip()

        with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["word", "phon", "star", "added_at", "definition"])
            for word in words:
                writer.writerow(
                    [word.word, word.phon, word.star, word.add_time[:10], clean(word.exp)]
                )
    elif args.format == "json":
        payload = [
            {
                "word": w.word,
                "phon": w.phon,
                "star": w.star,
                "add_time": w.add_time,
                "exp": w.exp,
            }
            for w in words
        ]
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    else:
        with open(args.out, "w", encoding="utf-8") as fh:
            for word in words:
                fh.write(f"{word.word}\t{word.add_time[:10]}\n")

    print(f"[done] 已导出 {len(words)} 个词到 {args.out}（{args.format}）")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    config = Config.from_env()
    eudic = EudicClient(config.eudic_headers, language=config.language)
    words = eudic.fetch_all(config.eudic_category_ids)
    stats = summarize(words)

    if args.json:
        print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"生词本 {', '.join(config.eudic_category_ids)}")
        print(format_summary(stats, recent_months=args.months))
        print()
        print(f"（本次请求 {eudic.http.request_count} 次）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eudic2maimemo",
        description="把欧路词典生词本同步到墨墨背单词云词本",
    )
    sub = parser.add_subparsers(dest="command")

    p_sync = sub.add_parser("sync", help="同步（默认增量）")
    p_sync.add_argument("--full", action="store_true", help="全量重建云词本内容")
    p_sync.add_argument("--dry-run", action="store_true", help="只预览，不写入墨墨")
    p_sync.add_argument("--limit", type=int, default=None, help="本次最多同步多少个新词")
    p_sync.add_argument(
        "--ignore",
        action="append",
        metavar="正则",
        help="额外的忽略规则，可重复；命中则不写入（如 '\\s' 跳过词组、'[\\u4e00-\\u9fff]' 跳过中文）",
    )
    p_sync.add_argument("--json", action="store_true", help="输出机器可读结果")
    p_sync.add_argument("--quiet", action="store_true", help="不打印新增词列表")
    p_sync.set_defaults(func=cmd_sync)

    p_serve = sub.add_parser("serve", help="常驻运行，按固定间隔同步")
    p_serve.add_argument(
        "--interval",
        type=float,
        default=None,
        metavar="小时",
        help="同步间隔，单位小时；默认读 SYNC_INTERVAL_HOURS，否则 24",
    )
    p_serve.add_argument("--full", action="store_true", help="每轮都全量重建（一般不需要）")
    p_serve.add_argument("--ignore", action="append", metavar="正则", help="额外的忽略规则")
    p_serve.add_argument("--quiet", action="store_true", help="不打印新增词列表")
    p_serve.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help=argparse.SUPPRESS,
    )
    p_serve.set_defaults(func=cmd_serve, dry_run=False, limit=None, json=False)

    p_doc = sub.add_parser("doctor", help="检查配置、token 与云词本状态")
    p_doc.add_argument("--deep", action="store_true", help="翻完整个生词本做覆盖度对比")
    p_doc.set_defaults(func=cmd_doctor)

    p_exp = sub.add_parser("export", help="导出欧路全量词表")
    p_exp.add_argument("--out", default=None, help="输出文件路径（默认打印到 stdout）")
    p_exp.add_argument(
        "--format",
        choices=["text", "csv", "json"],
        default="text",
        help="导出格式，仅 --out 时生效",
    )
    p_exp.set_defaults(func=cmd_export)

    p_stats = sub.add_parser("stats", help="词本画像：规模、增长节奏、数据缺口")
    p_stats.add_argument("--months", type=int, default=12, help="展示最近多少个月（默认 12）")
    p_stats.add_argument("--json", action="store_true", help="输出机器可读结果")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def _setup_console() -> None:
    """Windows 下把控制台切到 UTF-8。

    PyInstaller 打出来的 exe 默认跟随系统代码页（简体中文是 936），
    在 Git Bash、Windows Terminal 这类按 UTF-8 读的终端里会显示乱码。
    把控制台代码页和输出流都改成 UTF-8 之后，cmd、PowerShell、Git Bash 都能正常显示。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except SyncError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
