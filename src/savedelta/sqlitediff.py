from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import AnalysisError
from .util import json_safe, sha256_bytes, truncate_text


@dataclass(slots=True)
class TableState:
    name: str
    schema: str | None
    columns: list[str]
    key_columns: list[str]
    key_mode: str
    row_count: int
    rows: dict[str, list[Any]] | None
    rows_truncated: bool


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _materialize(data: bytes) -> Path:
    descriptor, name = tempfile.mkstemp(prefix="savedelta-sqlite-", suffix=".db")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only = ON")
    try:
        connection.execute("PRAGMA trusted_schema = OFF")
    except sqlite3.DatabaseError:
        pass
    return connection


def _master(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return [
        {
            "type": row[0],
            "name": row[1],
            "table": row[2],
            "sql": row[3],
        }
        for row in rows
    ]


def _row_key(values: tuple[Any, ...]) -> str:
    return json.dumps(
        json_safe(list(values)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _table_state(
    connection: sqlite3.Connection,
    *,
    name: str,
    schema: str | None,
    max_rows: int,
) -> TableState:
    quoted = _quote_identifier(name)
    info_rows = connection.execute(f"PRAGMA table_info({quoted})").fetchall()
    columns = [str(row[1]) for row in info_rows]
    primary_key = [
        str(row[1])
        for row in sorted(info_rows, key=lambda row: int(row[5]) or 1_000_000)
        if int(row[5]) > 0
    ]
    row_count = int(connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0])
    if row_count > max_rows:
        return TableState(
            name=name,
            schema=schema,
            columns=columns,
            key_columns=primary_key,
            key_mode="primary_key" if primary_key else "none",
            row_count=row_count,
            rows=None,
            rows_truncated=True,
        )

    rows: dict[str, list[Any]] = {}
    if primary_key:
        select = f"SELECT * FROM {quoted}"
        order = ", ".join(_quote_identifier(item) for item in primary_key)
        fetched = connection.execute(f"{select} ORDER BY {order}").fetchall()
        indexes = [columns.index(item) for item in primary_key]
        for row in fetched:
            key = _row_key(tuple(row[index] for index in indexes))
            rows[key] = [json_safe(value) for value in row]
        key_mode = "primary_key"
        key_columns = primary_key
    else:
        try:
            fetched = connection.execute(
                f"SELECT rowid, * FROM {quoted} ORDER BY rowid"
            ).fetchall()
            for row in fetched:
                key = _row_key((row[0],))
                rows[key] = [json_safe(value) for value in row]
            key_mode = "rowid"
            key_columns = ["rowid"]
            columns = ["rowid", *columns]
        except sqlite3.DatabaseError:
            fetched = connection.execute(f"SELECT * FROM {quoted}").fetchall()
            for row in fetched:
                safe_row = [json_safe(value) for value in row]
                key = sha256_bytes(
                    json.dumps(
                        safe_row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                rows[key] = safe_row
            key_mode = "row_hash"
            key_columns = []

    return TableState(
        name=name,
        schema=schema,
        columns=columns,
        key_columns=key_columns,
        key_mode=key_mode,
        row_count=row_count,
        rows=rows,
        rows_truncated=False,
    )


def _database_state(data: bytes, max_rows: int) -> dict[str, Any]:
    path = _materialize(data)
    try:
        connection = _connect_read_only(path)
        try:
            master = _master(connection)
            tables: dict[str, TableState] = {}
            for item in master:
                if item["type"] != "table":
                    continue
                tables[item["name"]] = _table_state(
                    connection,
                    name=item["name"],
                    schema=item["sql"],
                    max_rows=max_rows,
                )
            return {"master": master, "tables": tables}
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AnalysisError(f"cannot inspect SQLite database: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)


def _row_preview(
    state: TableState,
    key: str,
    row: list[Any],
    *,
    value_limit: int = 180,
) -> dict[str, Any]:
    values = {
        column: (
            truncate_text(value, value_limit) if isinstance(value, str) else value
        )
        for column, value in zip(state.columns, row)
    }
    try:
        decoded_key = json.loads(key)
    except json.JSONDecodeError:
        decoded_key = key
    return {"key": decoded_key, "values": values}


def analyze_sqlite(
    before_data: bytes,
    after_data: bytes,
    *,
    max_rows_per_table: int = 5_000,
    max_row_changes: int = 200,
) -> dict[str, Any]:
    before = _database_state(before_data, max_rows_per_table)
    after = _database_state(after_data, max_rows_per_table)

    before_master = {
        (item["type"], item["name"]): item for item in before["master"]
    }
    after_master = {(item["type"], item["name"]): item for item in after["master"]}
    schema_changes: list[dict[str, Any]] = []
    for key in sorted(set(before_master) | set(after_master)):
        old = before_master.get(key)
        new = after_master.get(key)
        if old is None:
            schema_changes.append(
                {"kind": "added", "type": key[0], "name": key[1], "after": new["sql"]}
            )
        elif new is None:
            schema_changes.append(
                {
                    "kind": "removed",
                    "type": key[0],
                    "name": key[1],
                    "before": old["sql"],
                }
            )
        elif old["sql"] != new["sql"]:
            schema_changes.append(
                {
                    "kind": "changed",
                    "type": key[0],
                    "name": key[1],
                    "before": old["sql"],
                    "after": new["sql"],
                }
            )

    table_changes: list[dict[str, Any]] = []
    truncated = False
    before_tables: dict[str, TableState] = before["tables"]
    after_tables: dict[str, TableState] = after["tables"]
    for name in sorted(set(before_tables) | set(after_tables)):
        old = before_tables.get(name)
        new = after_tables.get(name)
        if old is None:
            table_changes.append(
                {
                    "table": name,
                    "kind": "added",
                    "rows_before": 0,
                    "rows_after": new.row_count,
                }
            )
            continue
        if new is None:
            table_changes.append(
                {
                    "table": name,
                    "kind": "removed",
                    "rows_before": old.row_count,
                    "rows_after": 0,
                }
            )
            continue

        change: dict[str, Any] = {
            "table": name,
            "kind": "changed",
            "rows_before": old.row_count,
            "rows_after": new.row_count,
            "row_delta": new.row_count - old.row_count,
            "columns_before": old.columns,
            "columns_after": new.columns,
            "key_mode_before": old.key_mode,
            "key_mode_after": new.key_mode,
            "rows_scanned": not old.rows_truncated and not new.rows_truncated,
            "row_changes": [],
        }
        if old.rows is not None and new.rows is not None:
            old_keys = set(old.rows)
            new_keys = set(new.rows)
            row_changes: list[dict[str, Any]] = []
            for key in sorted(old_keys - new_keys):
                if len(row_changes) >= max_row_changes:
                    truncated = True
                    break
                row_changes.append(
                    {
                        "kind": "removed",
                        **_row_preview(old, key, old.rows[key]),
                    }
                )
            for key in sorted(new_keys - old_keys):
                if len(row_changes) >= max_row_changes:
                    truncated = True
                    break
                row_changes.append(
                    {
                        "kind": "added",
                        **_row_preview(new, key, new.rows[key]),
                    }
                )
            for key in sorted(old_keys & new_keys):
                if old.rows[key] == new.rows[key]:
                    continue
                if len(row_changes) >= max_row_changes:
                    truncated = True
                    break
                row_changes.append(
                    {
                        "kind": "changed",
                        "key": json_safe(json.loads(key)),
                        "before": _row_preview(old, key, old.rows[key])["values"],
                        "after": _row_preview(new, key, new.rows[key])["values"],
                    }
                )
            change["row_changes"] = row_changes
            change["row_change_count"] = len(row_changes)
        else:
            change["row_change_count"] = None

        if (
            change["row_delta"] != 0
            or change["row_changes"]
            or old.columns != new.columns
            or old.schema != new.schema
        ):
            table_changes.append(change)

    return {
        "kind": "sqlite",
        "schema_change_count": len(schema_changes),
        "schema_changes": schema_changes,
        "table_change_count": len(table_changes),
        "table_changes": table_changes,
        "row_changes_truncated": truncated,
        "max_rows_per_table": max_rows_per_table,
    }
