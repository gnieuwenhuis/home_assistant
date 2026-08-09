#!/usr/bin/env python3
"""PostToolUse check on Python comments Claude just wrote.

Enforces the mechanical half of CLAUDE.md "Code Comments" and
.claude/rules/code-comments.md. Only comments present in the tool call's new
text are inspected, so pre-existing code is never flagged. Patterns are
deliberately conservative — a missed violation is cheaper than a false one.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tokenize
from pathlib import Path
from typing import Any

# Three-line explanations are established practice here; this catches walls of text.
MAX_COMMENT_BLOCK_LINES = 4

TODO_RE = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")

# Anchored at the start of the comment text.
TEMPORAL_PREFIX_RE = re.compile(
    r"^(?:"
    r"added|removed|refactored|renamed|switched|migrated"
    r"|changed to|updated to"
    r"|previously|formerly|originally|used to|no longer"
    r"|instead of|rather than"
    r"|replaces|replaced"
    r"|fix(?:ed)? (?:the|a|an|this)"
    r")\b",
    re.IGNORECASE,
)

TEMPORAL_ANYWHERE_RE = re.compile(
    r"\b(?:"
    r"unlike the (?:old|previous|former|original)"
    r"|we (?:decided|opted|chose)"
    r"|intentionally|deliberately"
    r"|workaround until"
    r"|temporary (?:workaround|fix|hack|solution)"
    r"|will be (?:added|removed|implemented|extended|supported)"
    r")\b",
    re.IGNORECASE,
)

# Tool directives and dividers are not prose; they never count toward a block.
DIRECTIVE_RE = re.compile(
    r"^(?:!|-\*-|type:|noqa|ruff:|mypy:|fmt:|pylint:|pragma:|pyright:|nosec)"
)
DIVIDER_RE = re.compile(r"^[-=#*_\s]*$")


def new_text(tool_name: str, tool_input: dict[str, Any]) -> str:
    """The text this tool call authored, as one blob."""
    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    if tool_name == "NotebookEdit":
        return str(tool_input.get("new_source", ""))
    parts = [str(tool_input.get("new_string", ""))]
    for edit in tool_input.get("edits", []) or []:
        if isinstance(edit, dict):
            parts.append(str(edit.get("new_string", "")))
    return "\n".join(p for p in parts if p)


def comments_from_file(path: Path) -> list[tuple[int, str]]:
    """(line, text) for every `#` comment, or [] if the file will not tokenize."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                found.append((tok.start[0], tok.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Mid-refactor file: fall back to a line scan, which cannot tell a `#`
        # inside a string from a real comment. Both callers tolerate that.
        return [
            (i, line.strip())
            for i, line in enumerate(source.splitlines(), 1)
            if line.lstrip().startswith("#")
        ]
    return found


def body(comment: str) -> str:
    return comment.lstrip("#").strip()


def is_prose(comment: str) -> bool:
    text = body(comment)
    return bool(text) and not DIRECTIVE_RE.match(text) and not DIVIDER_RE.match(text)


def comment_blocks(comments: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Prose comments grouped into runs of consecutive lines."""
    prose = sorted((line, text) for line, text in comments if is_prose(text))
    blocks: list[list[tuple[int, str]]] = []
    for entry in prose:
        if blocks and entry[0] == blocks[-1][-1][0] + 1:
            blocks[-1].append(entry)
        else:
            blocks.append([entry])
    return blocks


def thoughts(block: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """(line, text) per sentence in a block, so anchored patterns see real starts.

    A wrapped comment continues mid-sentence in lower case; a new thought either
    follows a terminator or starts capitalised. Splitting on that keeps
    "# rather than the whole table." from reading as a change-narrative opener.
    """
    out: list[tuple[int, str]] = []
    for index, (line, text) in enumerate(block):
        content = body(text)
        starts = index == 0 or content[:1].isupper() or body(block[index - 1][1])[-1:] in ".!?:"
        if starts:
            out.append((line, content))
        elif out:
            out[-1] = (out[-1][0], f"{out[-1][1]} {content}")
    return out


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_input = payload.get("tool_input") or {}
    path_str = tool_input.get("file_path") or ""
    if not path_str.endswith(".py"):
        return 0

    path = Path(path_str)
    if not path.is_file():
        return 0

    # Scratch and temp scripts are not repo code; CLAUDE.md conventions don't reach them.
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    if project and not path.resolve().is_relative_to(Path(project).resolve()):
        return 0

    authored = new_text(payload.get("tool_name", ""), tool_input)
    if not authored:
        return 0

    comments = comments_from_file(path)
    # A comment counts as newly written when its exact text appears in the blob
    # the tool just wrote.
    fresh = {line for line, text in comments if text and text in authored}
    if not fresh:
        return 0

    problems: list[str] = []

    for line, text in comments:
        if line in fresh and is_prose(text) and TODO_RE.search(body(text)):
            problems.append(
                f"{path.name}:{line}: leftover marker — {text.strip()}\n"
                f"    Implement it now or delete the comment; CLAUDE.md forbids TODO markers."
            )

    for block in comment_blocks(comments):
        if not any(line in fresh for line, _ in block):
            continue
        for line, sentence in thoughts(block):
            if TEMPORAL_PREFIX_RE.match(sentence) or TEMPORAL_ANYWHERE_RE.search(sentence):
                problems.append(
                    f"{path.name}:{line}: change-narrative comment — {sentence}\n"
                    f"    Reframe in the timeless present: describe what the code does, not what changed."
                )
        if len(block) > MAX_COMMENT_BLOCK_LINES:
            problems.append(
                f"{path.name}:{block[0][0]}-{block[-1][0]}: {len(block)}-line comment block.\n"
                f"    CLAUDE.md keeps inline comments to the non-obvious constraint. Trim it, or "
                f"move the detail to the commit message."
            )

    if not problems:
        return 0

    reason = (
        "Comment conventions (CLAUDE.md + .claude/rules/code-comments.md):\n\n"
        + "\n".join(problems)
        + "\n\nFix these in the file you just edited. If a match is a false positive "
        "(the checks are regex-based and conservative), say so in one line and carry on."
    )
    json.dump(
        {
            "decision": "block",
            "reason": reason,
            "systemMessage": f"Comment check flagged {len(problems)} item(s) in {path.name}",
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
