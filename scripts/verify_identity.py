#!/usr/bin/env python3
"""Reject releases whose Git history contains an unexpected identity."""

from __future__ import annotations

import re
import subprocess
import sys


EXPECTED_NAME = "KanadeK"
EXPECTED_EMAIL = "121669563+KanadeK@users.noreply.github.com"
FORBIDDEN = re.compile(r"(codex|openai|copilot|bot@|noreply@anthropic)", re.I)


def main() -> int:
    result = subprocess.run(
        [
            "git",
            "log",
            "--format=%an%x00%ae%x00%cn%x00%ce",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip(), file=sys.stderr)
        return result.returncode
    errors: list[str] = []
    for number, line in enumerate(result.stdout.splitlines(), start=1):
        fields = line.split("\0")
        if len(fields) != 4:
            errors.append(f"commit {number}: malformed identity record")
            continue
        author_name, author_email, committer_name, committer_email = fields
        for role, name, email in (
            ("author", author_name, author_email),
            ("committer", committer_name, committer_email),
        ):
            if name != EXPECTED_NAME or email != EXPECTED_EMAIL:
                errors.append(
                    f"commit {number}: unexpected {role} {name} <{email}>"
                )
            if FORBIDDEN.search(f"{name} {email}"):
                errors.append(f"commit {number}: forbidden automated identity")
    if errors:
        print("Identity verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    commit_count = len(result.stdout.splitlines())
    if commit_count == 0:
        print("Identity verification failed: no commits", file=sys.stderr)
        return 1
    print(f"Identity verified for {commit_count} commit(s): {EXPECTED_NAME}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
