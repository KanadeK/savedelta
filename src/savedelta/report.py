from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .models import DeltaReport, FileChange
from .util import format_bytes, truncate_text


def render_json(report: DeltaReport, *, pretty: bool = True) -> str:
    return (
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2 if pretty else None,
            sort_keys=False,
        )
        + "\n"
    )


def _text_detail(change: FileChange, lines: list[str], maximum: int) -> None:
    details = change.details
    kind = details.get("kind")
    if kind in {"json", "toml", "ini"}:
        for item in details.get("changes", [])[:maximum]:
            before = truncate_text(item.get("before", "∅"), 90)
            after = truncate_text(item.get("after", "∅"), 90)
            lines.append(
                f"    {item.get('kind', '?'):12} {item.get('path', '$')}: "
                f"{before} -> {after}"
            )
    elif kind == "text":
        for line in details.get("unified_diff", [])[:maximum]:
            lines.append(f"    {line}")
    elif kind == "binary":
        for span in details.get("spans", [])[:maximum]:
            start = span.get("start", 0)
            end = span.get("end", span.get("before_end", "?"))
            rendered_end = f"0x{end:X}" if isinstance(end, int) else str(end)
            lines.append(
                f"    0x{int(start):X}..{rendered_end}: "
                f"{span.get('before_hex', '')} -> {span.get('after_hex', '')}"
            )
        for group in details.get("expectation_matches", []):
            for candidate in group.get("candidates", [])[:5]:
                lines.append(
                    "    candidate "
                    f"{candidate['from']}->{candidate['to']} at "
                    f"{candidate['offset_hex']} as "
                    f"{candidate['type']}/{candidate['endian']} "
                    f"(confidence {candidate['confidence']:.0%})"
                )
    elif kind == "sqlite":
        for table in details.get("table_changes", [])[:maximum]:
            lines.append(
                f"    table {table['table']}: "
                f"{table.get('rows_before', 0)} -> {table.get('rows_after', 0)} rows"
            )
    elif kind == "zip":
        for item in details.get("changes", [])[:maximum]:
            lines.append(
                f"    {item.get('status', '?'):8} {item.get('path', '?')}"
            )


def render_text(report: DeltaReport, *, detail_limit: int = 20) -> str:
    summary = report.summary
    lines = [
        f"SaveDelta {report.tool_version}",
        f"Before: {report.before}",
        f"After:  {report.after}",
        (
            "Result: "
            f"{summary['changed']} changed "
            f"({summary['modified']} modified, {summary['added']} added, "
            f"{summary['removed']} removed, {summary['renamed']} renamed); "
            f"{summary['unchanged']} unchanged"
        ),
    ]
    if report.expectations:
        lines.append("")
        lines.append("Expected value changes")
        for expectation in report.expectations:
            lines.append(
                f"  {expectation['from']} -> {expectation['to']}: "
                f"{expectation['match_count']} candidate(s)"
            )
            for match in expectation.get("matches", [])[:5]:
                location = match.get("path") or match.get("offset_hex", "")
                lines.append(
                    f"    {match.get('file', '?')} {location} "
                    f"(confidence {float(match.get('confidence', 0.0)):.0%})"
                )
    if report.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.extend(f"  - {warning}" for warning in report.warnings)
    if report.changes:
        lines.append("")
        lines.append("Changes")
        symbols = {
            "modified": "~",
            "added": "+",
            "removed": "-",
            "renamed": ">",
        }
        for change in report.changes:
            lines.append(
                f"  {symbols.get(change.status, '?')} {change.path} "
                f"[{change.format}] — {change.summary}"
            )
            _text_detail(change, lines, detail_limit)
            for warning in change.warnings:
                lines.append(f"    warning: {warning}")
    return "\n".join(lines) + "\n"


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _json_value(value: Any, limit: int = 180) -> str:
    if value is None:
        return '<span class="muted">∅</span>'
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return f"<code>{_e(truncate_text(text, limit))}</code>"


def _table(headers: list[str], rows: list[list[str]], classes: str = "") -> str:
    head = "".join(f"<th>{_e(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        f'<div class="table-wrap"><table class="{_e(classes)}">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _structured_html(details: dict[str, Any]) -> str:
    rows = []
    for item in details.get("changes", []):
        rows.append(
            [
                f"<code>{_e(item.get('path', '$'))}</code>",
                f'<span class="mini-badge">{_e(item.get("kind", "?"))}</span>',
                _json_value(item.get("before")),
                _json_value(item.get("after")),
            ]
        )
    note = (
        '<p class="notice">Additional changes were truncated by the report limit.</p>'
        if details.get("truncated")
        else ""
    )
    return note + _table(["Path", "Kind", "Before", "After"], rows)


def _text_html(details: dict[str, Any]) -> str:
    rendered = []
    for line in details.get("unified_diff", []):
        class_name = "ctx"
        if line.startswith("+") and not line.startswith("+++"):
            class_name = "add-line"
        elif line.startswith("-") and not line.startswith("---"):
            class_name = "del-line"
        elif line.startswith("@@"):
            class_name = "hunk"
        rendered.append(f'<span class="{class_name}">{_e(line)}</span>')
    note = (
        "\n… diff truncated …"
        if details.get("truncated")
        else ""
    )
    return f'<pre class="diff">{"".join(rendered)}{_e(note)}</pre>'


def _binary_heatmap(details: dict[str, Any]) -> str:
    size = max(
        int(details.get("size_before", 0)),
        int(details.get("size_after", 0)),
        1,
    )
    rects = []
    for span in details.get("spans", []):
        start = int(span.get("start", 0))
        end = int(
            span.get(
                "end",
                max(span.get("before_end", start), span.get("after_end", start)),
            )
        )
        x = 720 * start / size
        width = max(2.0, 720 * max(end - start, 1) / size)
        if x + width > 720:
            width = max(1.0, 720 - x)
        rects.append(
            f'<rect x="{x:.2f}" y="4" width="{width:.2f}" height="22" rx="2" />'
        )
    return (
        '<div class="heatmap-label"><span>0x0</span>'
        f"<span>0x{size:X}</span></div>"
        '<svg class="heatmap" viewBox="0 0 720 30" role="img" '
        'aria-label="Changed byte ranges"><rect class="track" x="0" y="4" '
        'width="720" height="22" rx="5" />'
        f'<g class="hot">{"".join(rects)}</g></svg>'
    )


def _binary_html(details: dict[str, Any]) -> str:
    metric_rows = [
        [
            _e(details.get("different_bytes", 0)),
            _e(f"{float(details.get('change_ratio', 0.0)):.2%}"),
            _e(f"{int(details.get('size_delta', 0)):+d} B"),
            _e(details.get("common_prefix_bytes", 0)),
            _e(details.get("common_suffix_bytes", 0)),
            _e(
                f"{details.get('entropy_before', 0)} → "
                f"{details.get('entropy_after', 0)}"
            ),
        ]
    ]
    spans = []
    for span in details.get("spans", []):
        start = int(span.get("start", 0))
        before_end = span.get("end", span.get("before_end", "?"))
        after_end = span.get("end", span.get("after_end", "?"))
        spans.append(
            [
                f"<code>0x{start:X}</code>",
                _e(f"{before_end} / {after_end}"),
                f"<code>{_e(span.get('before_hex', ''))}</code>",
                f"<code>{_e(span.get('after_hex', ''))}</code>",
                _e(span.get("before_ascii", "")),
                _e(span.get("after_ascii", "")),
            ]
        )
    candidates = []
    for group in details.get("expectation_matches", []):
        for item in group.get("candidates", []):
            candidates.append(
                [
                    f"<code>{_e(item['offset_hex'])}</code>",
                    _e(f"{item['from']} → {item['to']}"),
                    _e(item["type"]),
                    _e(item["endian"]),
                    _e(f"{float(item['confidence']):.0%}"),
                ]
            )
    compressed = (
        '<p class="notice">High entropy suggests compressed or encrypted content; '
        "field inference may be limited.</p>"
        if details.get("likely_compressed_or_encrypted")
        else ""
    )
    candidate_html = (
        "<h4>Expected-value candidates</h4>"
        + _table(["Offset", "Change", "Type", "Endian", "Confidence"], candidates)
        if candidates
        else ""
    )
    return (
        compressed
        + _binary_heatmap(details)
        + _table(
            [
                "Changed bytes",
                "Ratio",
                "Size delta",
                "Common prefix",
                "Common suffix",
                "Entropy",
            ],
            metric_rows,
        )
        + "<h4>Changed ranges</h4>"
        + _table(
            [
                "Start",
                "Before/after end",
                "Before hex",
                "After hex",
                "Before ASCII",
                "After ASCII",
            ],
            spans,
        )
        + candidate_html
    )


def _sqlite_html(details: dict[str, Any]) -> str:
    schema_rows = [
        [
            _e(item.get("kind", "?")),
            _e(item.get("type", "?")),
            f"<code>{_e(item.get('name', '?'))}</code>",
            _json_value(item.get("before")),
            _json_value(item.get("after")),
        ]
        for item in details.get("schema_changes", [])
    ]
    table_rows = []
    row_sections = []
    for table in details.get("table_changes", []):
        changes = table.get("row_changes", [])
        table_rows.append(
            [
                f"<code>{_e(table.get('table', '?'))}</code>",
                _e(table.get("kind", "changed")),
                _e(table.get("rows_before", 0)),
                _e(table.get("rows_after", 0)),
                _e(table.get("key_mode_after", table.get("key_mode_before", "—"))),
                _e(len(changes)),
            ]
        )
        if changes:
            rows = [
                [
                    _e(row.get("kind", "?")),
                    _json_value(row.get("key")),
                    _json_value(row.get("before", row.get("values"))),
                    _json_value(row.get("after")),
                ]
                for row in changes
            ]
            row_sections.append(
                f"<h4>{_e(table.get('table', '?'))} row changes</h4>"
                + _table(["Kind", "Key", "Before", "After"], rows)
            )
    schema_html = (
        "<h4>Schema objects</h4>"
        + _table(["Kind", "Type", "Name", "Before", "After"], schema_rows)
        if schema_rows
        else ""
    )
    return (
        schema_html
        + "<h4>Tables</h4>"
        + _table(
            ["Table", "Kind", "Rows before", "Rows after", "Key mode", "Row changes"],
            table_rows,
        )
        + "".join(row_sections)
    )


def _nested_summary(analysis: dict[str, Any] | None) -> str:
    if not analysis:
        return '<span class="muted">metadata only</span>'
    kind = analysis.get("kind", "?")
    if kind in {"json", "toml", "ini"}:
        return _e(f"{kind}: {analysis.get('change_count', 0)} values")
    if kind == "text":
        return _e(
            f"text: +{analysis.get('added_lines', 0)} "
            f"-{analysis.get('removed_lines', 0)} lines"
        )
    if kind == "binary":
        return _e(f"binary: {analysis.get('different_bytes', 0)} bytes")
    return _e(kind)


def _zip_html(details: dict[str, Any]) -> str:
    rows = []
    for item in details.get("changes", []):
        rows.append(
            [
                _e(item.get("status", "?")),
                f"<code>{_e(item.get('path', '?'))}</code>",
                _json_value(item.get("before")),
                _json_value(item.get("after")),
                _nested_summary(item.get("analysis")),
            ]
        )
    return _table(["Status", "Member", "Before", "After", "Deep analysis"], rows)


def _details_html(change: FileChange) -> str:
    kind = change.details.get("kind")
    if kind in {"json", "toml", "ini"}:
        return _structured_html(change.details)
    if kind == "text":
        return _text_html(change.details)
    if kind == "binary":
        return _binary_html(change.details)
    if kind == "sqlite":
        return _sqlite_html(change.details)
    if kind == "zip":
        return _zip_html(change.details)
    if kind == "rename":
        return (
            f"<p>Moved from <code>{_e(change.previous_path)}</code> to "
            f"<code>{_e(change.path)}</code> with identical content.</p>"
        )
    return ""


def render_html(report: DeltaReport) -> str:
    summary = report.summary
    expectation_rows = []
    for item in report.expectations:
        top = item.get("matches", [])[:5]
        locations = "<br>".join(
            f"<code>{_e(match.get('file', '?'))}</code> "
            f"{_e(match.get('path', match.get('offset_hex', '')))}"
            for match in top
        )
        expectation_rows.append(
            [
                _e(item["from"]),
                _e(item["to"]),
                _e(item["match_count"]),
                locations or '<span class="muted">No exact candidates</span>',
            ]
        )

    warnings_html = ""
    all_warnings = [
        *report.warnings,
        *(
            f"{change.path}: {warning}"
            for change in report.changes
            for warning in change.warnings
        ),
    ]
    if all_warnings:
        warnings_html = (
            '<section class="panel warnings"><h2>Warnings</h2><ul>'
            + "".join(f"<li>{_e(item)}</li>" for item in all_warnings)
            + "</ul></section>"
        )

    changes_html = []
    for index, change in enumerate(report.changes):
        before_size = format_bytes(change.before_size)
        after_size = format_bytes(change.after_size)
        open_attr = " open" if index < 3 else ""
        changes_html.append(
            f'<details class="change {change.status}"{open_attr}>'
            "<summary>"
            f'<span class="status">{_e(change.status)}</span>'
            f'<span class="path">{_e(change.path)}</span>'
            f'<span class="format">{_e(change.format)}</span>'
            f'<span class="summary-text">{_e(change.summary)}</span>'
            "</summary>"
            '<div class="change-body">'
            '<div class="file-meta">'
            f"<span>Before: <strong>{_e(before_size)}</strong></span>"
            f"<span>After: <strong>{_e(after_size)}</strong></span>"
            f"<span>SHA: <code>{_e((change.after_sha256 or change.before_sha256 or '')[:12])}</code></span>"
            "</div>"
            f"{_details_html(change)}"
            "</div></details>"
        )

    no_changes = (
        '<div class="empty"><strong>No differences found.</strong>'
        "<span>The inputs have identical file content.</span></div>"
        if not report.changes
        else ""
    )
    expectations_html = (
        '<section class="panel"><h2>Expected-value locator</h2>'
        "<p>Likely fields matching the values you supplied.</p>"
        + _table(["From", "To", "Candidates", "Top locations"], expectation_rows)
        + "</section>"
        if expectation_rows
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
  <title>SaveDelta report — {_e(summary['changed'])} changes</title>
  <style>
    :root {{
      color-scheme: dark light;
      --bg: #0a0d12; --panel: #111722; --panel-2: #171f2c;
      --text: #e8eef8; --muted: #8ea0b9; --line: #29364a;
      --cyan: #55d6d0; --amber: #ffbd5c; --red: #ff7185;
      --green: #66d994; --blue: #68a7ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: var(--bg); color: var(--text);
      font: 14px/1.55 ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
    }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 38px auto 72px; }}
    header {{ display: grid; gap: 18px; margin-bottom: 24px; }}
    .eyebrow {{ color: var(--cyan); font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: clamp(32px, 7vw, 64px); line-height: 1; letter-spacing: -.045em; }}
    h2 {{ margin: 0 0 14px; font-size: 20px; }}
    h4 {{ margin: 24px 0 10px; }}
    p {{ color: var(--muted); }}
    code {{ font: 12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }}
    .sources {{ display: grid; gap: 5px; color: var(--muted); }}
    .sources code {{ color: var(--text); }}
    .cards {{ display: grid; grid-template-columns: repeat(6, minmax(0,1fr)); gap: 10px; }}
    .card, .panel {{
      background: linear-gradient(145deg, var(--panel), var(--panel-2));
      border: 1px solid var(--line); border-radius: 14px;
    }}
    .card {{ padding: 15px; }}
    .card strong {{ display: block; font-size: 28px; line-height: 1.1; }}
    .card span {{ color: var(--muted); font-size: 12px; }}
    .panel {{ padding: 20px; margin: 16px 0; }}
    .warnings {{ border-color: color-mix(in srgb, var(--amber) 55%, var(--line)); }}
    .table-wrap {{ overflow: auto; border: 1px solid var(--line); border-radius: 10px; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 640px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; background: #0d131d; }}
    tr:last-child td {{ border-bottom: 0; }}
    details.change {{
      margin: 10px 0; border: 1px solid var(--line);
      border-radius: 12px; background: var(--panel); overflow: hidden;
    }}
    details.change[open] {{ border-color: #3c4c66; }}
    summary {{
      display: grid; grid-template-columns: 80px minmax(180px,1fr) 80px minmax(160px, .7fr);
      gap: 12px; align-items: center; padding: 14px 16px; cursor: pointer;
    }}
    summary:hover {{ background: var(--panel-2); }}
    .status {{ text-transform: uppercase; font-size: 11px; font-weight: 800; letter-spacing: .08em; }}
    .modified .status {{ color: var(--amber); }}
    .added .status {{ color: var(--green); }}
    .removed .status {{ color: var(--red); }}
    .renamed .status {{ color: var(--blue); }}
    .path {{ font-weight: 750; overflow-wrap: anywhere; }}
    .format {{ color: var(--cyan); font: 12px ui-monospace, monospace; }}
    .summary-text {{ color: var(--muted); }}
    .change-body {{ border-top: 1px solid var(--line); padding: 18px; }}
    .file-meta {{ display: flex; flex-wrap: wrap; gap: 18px; color: var(--muted); margin-bottom: 16px; }}
    .file-meta strong {{ color: var(--text); }}
    .mini-badge {{ display: inline-block; border: 1px solid var(--line); border-radius: 99px; padding: 1px 7px; font-size: 11px; }}
    pre.diff {{
      overflow: auto; padding: 14px; border: 1px solid var(--line); border-radius: 10px;
      background: #080b10; font: 12px/1.55 ui-monospace, SFMono-Regular, Consolas, monospace;
    }}
    pre.diff span {{ display: block; white-space: pre; }}
    .add-line {{ color: var(--green); background: #0f2a1c; }}
    .del-line {{ color: var(--red); background: #32151b; }}
    .hunk {{ color: var(--cyan); }}
    .notice {{ padding: 10px 12px; border-left: 3px solid var(--amber); background: #291f10; color: #ffd99b; }}
    .heatmap-label {{ display: flex; justify-content: space-between; color: var(--muted); font: 11px ui-monospace, monospace; }}
    .heatmap {{ display: block; width: 100%; height: 34px; margin-bottom: 12px; }}
    .track {{ fill: #263246; }} .hot rect {{ fill: var(--red); }}
    .muted {{ color: var(--muted); }}
    .empty {{ display: grid; place-items: center; gap: 4px; min-height: 180px; border: 1px dashed var(--line); border-radius: 14px; color: var(--muted); }}
    footer {{ margin-top: 28px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 850px) {{
      .cards {{ grid-template-columns: repeat(3,1fr); }}
      summary {{ grid-template-columns: 74px 1fr 70px; }}
      .summary-text {{ grid-column: 2 / -1; }}
    }}
    @media (max-width: 520px) {{
      main {{ width: min(100% - 20px, 1180px); margin-top: 22px; }}
      .cards {{ grid-template-columns: repeat(2,1fr); }}
      summary {{ grid-template-columns: 70px 1fr; }}
      .format {{ grid-column: 2; }}
    }}
    @media print {{
      :root {{ --bg: white; --panel: white; --panel-2: #f7f8fa; --text: #111; --muted: #555; --line: #ccc; }}
      main {{ width: 100%; margin: 0; }}
      details.change {{ break-inside: avoid; }}
      details.change:not([open]) > *:not(summary) {{ display: block; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">SaveDelta {_e(report.tool_version)}</div>
    <h1>State changed.<br>Here is where.</h1>
    <div class="sources">
      <span>Before · <code>{_e(report.before)}</code></span>
      <span>After&nbsp; · <code>{_e(report.after)}</code></span>
      <span>Generated · {_e(report.generated_at)}</span>
    </div>
  </header>
  <section class="cards" aria-label="Summary">
    <div class="card"><strong>{_e(summary['changed'])}</strong><span>Changed</span></div>
    <div class="card"><strong>{_e(summary['modified'])}</strong><span>Modified</span></div>
    <div class="card"><strong>{_e(summary['added'])}</strong><span>Added</span></div>
    <div class="card"><strong>{_e(summary['removed'])}</strong><span>Removed</span></div>
    <div class="card"><strong>{_e(summary['renamed'])}</strong><span>Renamed</span></div>
    <div class="card"><strong>{_e(summary['unchanged'])}</strong><span>Unchanged</span></div>
  </section>
  {expectations_html}
  {warnings_html}
  <section class="panel">
    <h2>File changes</h2>
    {no_changes}
    {''.join(changes_html)}
  </section>
  <footer>Read-only analysis. No input files were modified. Report schema {report.schema_version}.</footer>
</main>
</body>
</html>
"""


def write_report(
    report: DeltaReport,
    *,
    format_name: str,
    output: str | Path | None,
) -> str | Path:
    if format_name == "json":
        rendered = render_json(report)
    elif format_name == "html":
        rendered = render_html(report)
    elif format_name == "text":
        rendered = render_text(report)
    else:
        raise ValueError(f"unsupported report format: {format_name}")

    if output is None:
        return rendered
    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8", newline="\n")
    return destination
