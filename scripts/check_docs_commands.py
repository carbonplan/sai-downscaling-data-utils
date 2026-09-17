#!/usr/bin/env python
"""Check that every download command shown in the docs still runs.

The README, the notebooks, `download.sh` and `download.py`'s own docstring all
show example commands. This runs each of them with `--dry-run`, which reads a
little metadata and downloads nothing, so an example that drifts out of step
with the tool fails here instead of in front of a reader.

Run it with `pixi run python scripts/check_docs_commands.py`.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import download  # noqa: E402

# The ways the docs spell a call to the tool.
ENTRY_POINT = re.compile(
    r"^\s*(?:\./)?(?:pixi run download|scripts/download\.sh|python scripts/download\.py)\s+(?P<args>.+)$",
    re.MULTILINE,
)


def documented_text() -> list[tuple[str, str]]:
    """The text of every file that shows example commands, as (name, text).

    Every read says encoding="utf-8". Without it Python uses the locale encoding,
    which is cp1252 on Windows, and the notebooks contain characters it cannot read.
    """
    sources = [
        (p.name, p.read_text(encoding="utf-8"))
        for p in (REPO / "README.md", REPO / "scripts" / "download.sh", REPO / "scripts" / "download.py")
    ]
    for path in sorted((REPO / "notebooks").glob("*.ipynb")):
        notebook = json.loads(path.read_text(encoding="utf-8"))
        markdown = "\n".join(
            "".join(cell["source"]) for cell in notebook["cells"] if cell["cell_type"] == "markdown"
        )
        sources.append((path.name, markdown))
    return sources


def commands() -> list[tuple[str, list[str]]]:
    """Every documented command, as (where it came from, argv), without duplicates."""
    found: list[tuple[str, list[str]]] = []
    seen = set()
    for name, text in documented_text():
        # Examples wrap over several lines with a trailing backslash.
        joined = re.sub(r"\\\n\s*", " ", text)
        for match in ENTRY_POINT.finditer(joined):
            argv = shlex.split(match.group("args"), comments=True)
            if not argv or "--help" in argv:
                continue
            if "--dry-run" not in argv:
                argv.append("--dry-run")
            key = tuple(argv)
            if key not in seen:
                seen.add(key)
                found.append((name, argv))
    return found


def main() -> int:
    found = commands()
    if not found:
        print("error: no commands found in the docs; has the way they are written changed?")
        return 1

    failed = []
    for name, argv in found:
        try:
            code = download.main(argv)
        except SystemExit as exc:  # argparse and the tool's own error paths
            code = exc.code
        except Exception as exc:  # noqa: BLE001 - report, then carry on to the next one
            code = f"{type(exc).__name__}: {exc}"
        if code not in (0, None):
            failed.append((name, argv, code))

    print(f"\nchecked {len(found)} documented commands, {len(failed)} failed")
    for name, argv, code in failed:
        print(f"  {name}: {' '.join(argv)}\n    -> {code}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
