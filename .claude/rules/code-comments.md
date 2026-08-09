---
globs:
  - "**/*.py"
---

# Comment Framing

CLAUDE.md governs comment *length and scope* (one or two short lines, only the
non-obvious constraint). This rule governs *framing*: how a comment is worded
once you have decided it earns its place.

> **Timeless Present Rule**: write from the perspective of a reader meeting the
> code for the first time, with no knowledge of what came before. The code
> simply *is*.

Change-narrative comments are a category error, not a style preference. The
edit that produced the code is ephemeral; the code's behavior is not.

## Five Detection Questions

Signal words are examples — extrapolate to semantically similar wording.

### 1. Does it describe an action taken rather than what exists?

| Contaminated | Timeless |
|---|---|
| `# Added mutex to fix race condition` | `# Mutex serializes cache access from concurrent requests` |
| `# Changed to use batch API` | `# Batch API reduces round-trips from N to 1` |

Signals: Added, Replaced, Now uses, Changed to, New, Updated, Refactored.

### 2. Does it compare to something not in the code?

| Contaminated | Timeless |
|---|---|
| `# Unlike the old approach, this is thread-safe` | `# Thread-safe: each worker gets independent state` |
| `# Previously handled in caller` | `# Encapsulated here; caller must not manage lifecycle` |

Signals: Instead of, Rather than, Previously, Replaces, Unlike the old, No longer.

### 3. Does it describe intent rather than behavior?

| Contaminated | Timeless |
|---|---|
| `# TODO: add retry logic later` | *(delete, or implement retry now)* |
| `# Temporary workaround until API v2` | `# API v1 lacks filtering; filter client-side` |

Signals: Will, TODO, Planned, Eventually, For future, Temporary, Workaround until.

### 4. Does it describe the author's choice rather than code behavior?

| Contaminated | Timeless |
|---|---|
| `# Deliberately using a lock over a queue` | `# Lock serializes access (single-writer pattern)` |
| `# We decided to cache at this layer` | `# Cache here: avoids a DB round-trip on the hot path` |

Signals: intentionally, deliberately, chose, decided, by design, we opted.

Test: delete the intent word. If the comment still makes sense, it was noise.
If it does not, reframe around the technical reason.

### 5. Does it point at a location rather than describe code?

`# After the write call`, `# Insert before validation` — always delete.
Position in the file already encodes this.

**Catch-all**: if a comment only makes sense to someone who knows the code's
history, it is contaminated even if it matches none of the above.

## Subtle Cases

Detection needs semantic judgment, not keyword matching.

| Comment | Verdict | Reasoning |
|---|---|---|
| `# Now handles edge cases properly` | Contaminated | "properly" implies it was improper before |
| `# Now blocks until the connection is ready` | Clean | "now" describes a runtime moment, not history |
| `# Fixed the null pointer issue` | Contaminated | describes a fix, not behavior |
| `# Returns None when the key is absent` | Clean | describes behavior |

## The Transformation

**Extract the technical justification, discard the change narrative.**

`# Added mutex to fix race` → `# Mutex serializes concurrent access`
