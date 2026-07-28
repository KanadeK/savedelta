from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .compare import CompareOptions, compare_views
from .demo import create_demo
from .errors import SaveDeltaError
from .inspect import inspect_file
from .report import render_text, write_report
from .snapshot import create_snapshot
from .source import load_source
from .util import format_bytes, parse_size, split_expectation


def _size_argument(value: str) -> int:
    try:
        return parse_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _expect_argument(value: str) -> tuple[int | float, int | float]:
    try:
        return split_expectation(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="savedelta",
        description=(
            "Capture application state, change one thing, and find exactly "
            "where it was stored."
        ),
        epilog=(
            "Quick start: savedelta demo demo-output && "
            "open demo-output/report.html"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser(
        "snapshot",
        help="capture a file or directory into a portable .sdelta archive",
    )
    snapshot.add_argument("source", help="file or directory to capture")
    snapshot.add_argument(
        "-o",
        "--output",
        required=True,
        help="output .sdelta path",
    )
    snapshot.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help="additional ignore glob; repeatable",
    )
    snapshot.add_argument(
        "--no-default-ignore",
        action="store_true",
        help="include volatile files normally ignored by default",
    )
    snapshot.add_argument(
        "--store",
        action="store_true",
        help="store without ZIP compression",
    )
    snapshot.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable capture statistics",
    )

    diff = subparsers.add_parser(
        "diff",
        help="compare files, directories, or .sdelta snapshots",
    )
    diff.add_argument("before", help="before file, directory, or .sdelta")
    diff.add_argument("after", help="after file, directory, or .sdelta")
    diff.add_argument(
        "-f",
        "--format",
        choices=("text", "json", "html"),
        default="text",
        help="report format (default: text)",
    )
    diff.add_argument("-o", "--output", help="write report to this path")
    diff.add_argument(
        "--expect",
        action="append",
        type=_expect_argument,
        default=[],
        metavar="FROM:TO",
        help="locate an expected value change, e.g. 100:250; repeatable",
    )
    diff.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="GLOB",
        help="additional ignore glob for live directories; repeatable",
    )
    diff.add_argument(
        "--no-default-ignore",
        action="store_true",
        help="include volatile files normally ignored by default",
    )
    diff.add_argument(
        "--no-renames",
        action="store_true",
        help="report identical moved files as add/remove instead of rename",
    )
    diff.add_argument(
        "--max-file-bytes",
        type=_size_argument,
        default=64 * 1024 * 1024,
        metavar="SIZE",
        help="deep-analysis limit per file (default: 64MiB)",
    )
    diff.add_argument(
        "--max-details",
        type=int,
        default=300,
        metavar="N",
        help="maximum detailed changes per file (default: 300)",
    )
    diff.add_argument(
        "--max-sqlite-rows",
        type=int,
        default=5_000,
        metavar="N",
        help="maximum rows scanned per SQLite table (default: 5000)",
    )
    diff.add_argument(
        "--fail-on-change",
        action="store_true",
        help="return exit code 1 when differences are found",
    )

    inspect = subparsers.add_parser(
        "inspect",
        help="identify one file and show safe metadata",
    )
    inspect.add_argument("file", help="file to inspect")
    inspect.add_argument(
        "-f",
        "--format",
        choices=("text", "json"),
        default="text",
    )
    inspect.add_argument(
        "--max-file-bytes",
        type=_size_argument,
        default=64 * 1024 * 1024,
        metavar="SIZE",
    )

    demo = subparsers.add_parser(
        "demo",
        help="generate before/after game state and a real HTML report",
    )
    demo.add_argument(
        "output",
        nargs="?",
        default="savedelta-demo",
        help="demo output directory (default: savedelta-demo)",
    )
    demo.add_argument(
        "--force",
        action="store_true",
        help="replace a non-empty demo directory",
    )
    demo.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable result",
    )
    return parser


def _snapshot_command(args: argparse.Namespace) -> int:
    path, stats = create_snapshot(
        args.source,
        args.output,
        ignore_patterns=args.ignore,
        default_ignores=not args.no_default_ignore,
        compress=not args.store,
    )
    if args.json:
        sys.stdout.write(json.dumps(stats, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(
            f"Captured {stats['files']} file(s), "
            f"{format_bytes(int(stats['input_bytes']))} -> "
            f"{path} ({format_bytes(int(stats['snapshot_bytes']))})\n"
        )
        for warning in stats["warnings"]:
            sys.stdout.write(f"Warning: {warning}\n")
    return 0


def _diff_command(args: argparse.Namespace) -> int:
    if args.max_details < 1:
        raise ValueError("--max-details must be at least 1")
    if args.max_sqlite_rows < 0:
        raise ValueError("--max-sqlite-rows cannot be negative")
    before = load_source(
        args.before,
        ignore_patterns=args.ignore,
        default_ignores=not args.no_default_ignore,
    )
    after = load_source(
        args.after,
        ignore_patterns=args.ignore,
        default_ignores=not args.no_default_ignore,
    )
    report = compare_views(
        before,
        after,
        options=CompareOptions(
            expectations=tuple(args.expect),
            max_file_bytes=args.max_file_bytes,
            max_changes_per_file=args.max_details,
            max_binary_spans=args.max_details,
            max_sqlite_rows=args.max_sqlite_rows,
            detect_renames=not args.no_renames,
        ),
    )
    output = args.output
    if args.format == "html" and output is None:
        output = "savedelta-report.html"
    result = write_report(report, format_name=args.format, output=output)
    if isinstance(result, Path):
        sys.stdout.write(
            f"Wrote {args.format.upper()} report to {result} "
            f"({report.summary['changed']} changed file(s))\n"
        )
    else:
        sys.stdout.write(result)
    return 1 if args.fail_on_change and report.has_changes else 0


def _inspect_text(result: dict[str, object]) -> str:
    lines = [
        f"Path:    {result['path']}",
        f"Format:  {result['format']}",
        f"Size:    {format_bytes(int(result['size']))}",
        f"SHA-256: {result['sha256']}",
        f"Entropy: {result['entropy']} bits/byte",
    ]
    text = result.get("text")
    if isinstance(text, dict):
        lines.append(
            f"Text:    {text['encoding']}, {text['line_count']} line(s), "
            f"{text['character_count']} character(s)"
        )
    sqlite = result.get("sqlite")
    if isinstance(sqlite, dict) and "objects" in sqlite:
        lines.append(f"SQLite:  {len(sqlite['objects'])} schema object(s)")
        for item in sqlite["objects"][:20]:
            lines.append(f"  {item['type']:7} {item['name']}")
    archive = result.get("zip")
    if isinstance(archive, dict) and "entry_count" in archive:
        lines.append(
            f"ZIP:     {archive['entry_count']} entries, "
            f"{format_bytes(int(archive['expanded_bytes']))} expanded"
        )
    strings = result.get("strings")
    if isinstance(strings, list) and strings:
        lines.append("Strings:")
        for item in strings[:20]:
            lines.append(f"  0x{int(item['offset']):X}  {item['text']}")
    return "\n".join(lines) + "\n"


def _inspect_command(args: argparse.Namespace) -> int:
    result = inspect_file(args.file, max_file_bytes=args.max_file_bytes)
    if args.format == "json":
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(_inspect_text(result))
    return 0


def _demo_command(args: argparse.Namespace) -> int:
    result = create_demo(args.output, force=args.force)
    if args.json:
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    else:
        summary = result["summary"]
        sys.stdout.write(
            "Demo complete.\n"
            f"  HTML report: {result['html_report']}\n"
            f"  JSON report: {result['json_report']}\n"
            f"  Result: {summary['changed']} changed file(s); "
            "100 -> 250 value candidates included.\n"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            return _snapshot_command(args)
        if args.command == "diff":
            return _diff_command(args)
        if args.command == "inspect":
            return _inspect_command(args)
        if args.command == "demo":
            return _demo_command(args)
        parser.error(f"unknown command: {args.command}")
    except BrokenPipeError:
        return 0
    except (SaveDeltaError, FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        sys.stderr.write(f"savedelta: error: {exc}\n")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
