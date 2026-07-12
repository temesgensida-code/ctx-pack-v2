"""Token counting: exact via tiktoken when reachable, heuristic otherwise.

Kept isolated so the rest of the engine never has to know or care which
counting strategy is active.
"""

from __future__ import annotations

import sys

_ENCODER = None
_BACKEND = "heuristic"

try:
    import tiktoken

    try:
        # This downloads/caches a BPE ranking file on first use — it can
        # fail with no network access (offline dev boxes, CI sandboxes,
        # air-gapped environments), so we degrade gracefully rather than
        # crash the whole pipeline.
        _ENCODER = tiktoken.get_encoding("cl100k_base")
        _BACKEND = "tiktoken"
    except Exception as e:  # noqa: BLE001 - deliberately broad, see above
        print(
            f"[pack_engine] tiktoken available but offline/unreachable "
            f"({e.__class__.__name__}); falling back to heuristic token "
            f"counting.",
            file=sys.stderr,
        )
        _ENCODER = None

except ImportError:
    print(
        "[pack_engine] tiktoken not installed; falling back to heuristic "
        "token counting.",
        file=sys.stderr,
    )


def backend() -> str:
    """Returns 'tiktoken' or 'heuristic' depending on what's active."""
    return _BACKEND


def count_tokens(text: str) -> int:
    if _ENCODER is not None:
        return len(_ENCODER.encode(text, disallowed_special=()))
    # Heuristic fallback: ~4 chars/token for English-ish source code.
    # Good enough for budgeting decisions when tiktoken is unreachable.
    return max(1, len(text) // 4)
