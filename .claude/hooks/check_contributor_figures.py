#!/usr/bin/env python3
"""Blocks per-contributor signal volumes from reaching the repo or GitHub.

Enforces .claude/rules/contributor-data.md. The line is attribution, not counting:
a number beside a contributor name is flagged, an aggregate naming no contributor
is not. Two entry points share one scan:

- PreToolUse on Bash denies `gh` and `git commit` invocations whose body carries
  a figure, because a posted comment or issue is public the moment it runs.
- PostToolUse on a write blocks the edit that authored one.

Only text the tool call itself authored is scanned, so pre-existing content is
never flagged. Unlike check_new_comments.py, the patterns here are deliberately
broad: a missed match publishes contributor data, while a false match costs one
line of dismissal.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

SCANNED_SUFFIXES = frozenset(
    {".md", ".py", ".yml", ".yaml", ".qmd", ".ipynb", ".txt", ".rst", ".sql", ".json"}
)

# Publishing verbs. A body reaching any of these is outside our control afterwards.
PUBLISHING_RE = re.compile(
    r"\bgh\s+(?:pr|issue|release)\s+(?:create|edit|comment)\b|\bgit\s+commit\b"
)

# Every registered source name ends in _signals, so new sources are covered
# without editing this list; the bare vendor names catch prose.
CONTRIBUTOR_RE = re.compile(
    r"\b(?:\w+_signals|meta|tomtom|tripadvisor|uber)\b", re.IGNORECASE
)

# Dates, versions, and hex digests would otherwise read as volumes.
NOISE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}"
    r"|\bv?\d+\.\d+\.\d+\S*"
    r"|0x[0-9a-fA-F]+"
    r"|\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"
)

CANDIDATE_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*%|\d{4,}")


def is_volume(token: str) -> bool:
    """A number shaped like a count, coverage share, or corpus size."""
    if "," in token or token.rstrip().endswith("%"):
        return True
    return not (len(token) == 4 and 1900 <= int(token) <= 2099)


def findings(text: str) -> list[str]:
    """One entry per line pairing a contributor with a volume-shaped number."""
    hits: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        masked = NOISE_RE.sub(" ", line)
        if not CONTRIBUTOR_RE.search(masked):
            continue
        volumes = [t for t in CANDIDATE_RE.findall(masked) if is_volume(t)]
        if volumes:
            hits.append(f"  line {number}: {', '.join(volumes)} — {line.strip()[:120]}")
    return hits


def bash_text(command: str) -> str:
    """The command plus any --body-file it points at."""
    parts = [command]
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    for flag, argument in zip(tokens, tokens[1:]):
        if flag in {"--body-file", "-F", "--file"}:
            try:
                parts.append(Path(argument).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(parts)


def authored_text(tool_name: str, tool_input: dict[str, Any]) -> str:
    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    if tool_name == "NotebookEdit":
        return str(tool_input.get("new_source", ""))
    parts = [str(tool_input.get("new_string", ""))]
    for edit in tool_input.get("edits", []) or []:
        if isinstance(edit, dict):
            parts.append(str(edit.get("new_string", "")))
    return "\n".join(p for p in parts if p)


def advice(hits: list[str], where: str) -> str:
    return (
        f"Contributor figures in {where} (.claude/rules/contributor-data.md):\n\n"
        + "\n".join(hits)
        + "\n\nA volume attached to a named contributor stays out of the repository and "
        "off GitHub. An aggregate total across contributors is fine — say the total, "
        "not the split. Where no honest total exists, state the shape of the result and "
        "keep the figures in a local spec.\n"
        "If a match is a false positive — a threshold, a sample size, a line count — "
        "say so in one line and carry on."
    )


def deny(hits: list[str]) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": advice(hits, "a command that publishes"),
            },
            "systemMessage": f"Blocked: {len(hits)} contributor figure(s) in an outbound body",
        },
        sys.stdout,
    )


def block(hits: list[str], name: str) -> None:
    json.dump(
        {
            "decision": "block",
            "reason": advice(hits, name),
            "systemMessage": f"Contributor-figure check flagged {len(hits)} line(s) in {name}",
        },
        sys.stdout,
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if not PUBLISHING_RE.search(command):
            return 0
        hits = findings(bash_text(command))
        if hits:
            deny(hits)
        return 0

    path_str = tool_input.get("file_path") or ""
    if not path_str or Path(path_str).suffix.lower() not in SCANNED_SUFFIXES:
        return 0

    # Scratch files outside the project are not published from here.
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    if project and not Path(path_str).resolve().is_relative_to(Path(project).resolve()):
        return 0

    hits = findings(authored_text(tool_name, tool_input))
    if hits:
        block(hits, Path(path_str).name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
