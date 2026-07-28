#!/usr/bin/env python3
"""Fast, dependency-free repository checks used locally and in CI."""

from __future__ import annotations

import ast
import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".cfg",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".toml",
    ".txt",
    ".yml",
    ".yaml",
}
REQUIRED_FILES = {
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "assets/social-preview.svg",
    "docs/report.schema.json",
    "LICENSE",
    "README.md",
    "SECURITY.md",
}
PLACEHOLDER_PATTERNS = (
    re.compile(r"\bTODO\b"),
    re.compile(r"\bFIXME\b"),
    re.compile(r"your[-_ ]?(?:name|username|email)", re.IGNORECASE),
)


def tracked_candidates() -> list[Path]:
    roots = [
        ROOT / ".github",
        ROOT / "assets",
        ROOT / "docs",
        ROOT / "examples",
        ROOT / "scripts",
        ROOT / "src",
        ROOT / "tests",
    ]
    files = [
        ROOT / ".editorconfig",
        ROOT / ".gitignore",
        ROOT / "CHANGELOG.md",
        ROOT / "CODE_OF_CONDUCT.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "LICENSE",
        ROOT / "MANIFEST.in",
        ROOT / "README.md",
        ROOT / "SECURITY.md",
        ROOT / "SUPPORT.md",
        ROOT / "pyproject.toml",
    ]
    for directory in roots:
        if directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(set(files))


def check_text(path: Path, errors: list[str]) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {
        ".editorconfig",
        ".gitignore",
        "Makefile",
    }:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"{path.relative_to(ROOT)}: not UTF-8 ({exc})")
        return None
    if "\r" in text:
        errors.append(f"{path.relative_to(ROOT)}: contains CR line endings")
    for number, line in enumerate(text.splitlines(), start=1):
        if line != line.rstrip():
            errors.append(
                f"{path.relative_to(ROOT)}:{number}: trailing whitespace"
            )
        if "\t" in line and path.name != "Makefile":
            errors.append(f"{path.relative_to(ROOT)}:{number}: tab character")
    return text


def check_python(path: Path, text: str, errors: list[str]) -> None:
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        errors.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
    if path.is_relative_to(ROOT / "src"):
        for pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                errors.append(
                    f"{path.relative_to(ROOT)}: placeholder {match.group(0)!r}"
                )


def check_readme_links(errors: list[str]) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", readme):
        if "://" in target or target.startswith("#"):
            continue
        clean = target.split("#", 1)[0]
        if clean and not (ROOT / clean).exists():
            errors.append(f"README.md: missing local link target {clean!r}")
    for target in re.findall(r'<img[^>]+src="([^"]+)"', readme):
        if "://" not in target and not (ROOT / target).exists():
            errors.append(f"README.md: missing image target {target!r}")


def check_metadata(errors: list[str]) -> None:
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    version = project["version"]
    init_text = (ROOT / "src/savedelta/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', init_text, re.MULTILINE)
    if match is None or match.group(1) != version:
        errors.append("version mismatch between pyproject.toml and __init__.py")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    if f"## [{version}]" not in changelog:
        errors.append(f"CHANGELOG.md: missing {version} release")
    if project.get("dependencies"):
        errors.append("pyproject.toml: runtime dependencies must remain empty")
    if project.get("name") != "savedelta":
        errors.append("pyproject.toml: project name must be savedelta")


def main() -> int:
    errors: list[str] = []
    for required in sorted(REQUIRED_FILES):
        if not (ROOT / required).is_file():
            errors.append(f"missing required file: {required}")

    for path in tracked_candidates():
        text = check_text(path, errors)
        if text is None:
            continue
        if path.suffix == ".py":
            check_python(path, text, errors)
        elif path.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                errors.append(
                    f"{path.relative_to(ROOT)}:{exc.lineno}: invalid JSON: {exc.msg}"
                )

    check_readme_links(errors)
    check_metadata(errors)
    if errors:
        print("Repository checks failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    python_count = sum(
        path.suffix == ".py" for path in tracked_candidates()
    )
    print(f"Repository checks passed ({python_count} Python files inspected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
