"""Regex-based secret detection and masking.

Deliberately conservative: patterns favor false positives over missed
leaks, since a hit is always masked (never silently dropped or, worse,
silently shipped in the clear).
"""

from __future__ import annotations

import re

# (label, pattern) — label shows up in the [REDACTED:label] marker and in
# the stderr warning, so keep these short and human-readable.
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Generic API Key", re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9_\-/+=]{16,}['\"]?"
    )),
    ("Private Key Block", re.compile(
        r"-----BEGIN (RSA|EC|OPENSSH|PGP|DSA) PRIVATE KEY-----"
    )),
    ("Slack Token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Generic Bearer/JWT", re.compile(
        r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
    )),
    ("Password Assignment", re.compile(
        r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]{6,}['\"]?"
    )),
]


def mask_secrets(text: str, rel_path: str = "") -> tuple[str, int]:
    """Returns (masked_text, hit_count). rel_path is accepted for call-site
    symmetry with logging but isn't required for the masking itself."""
    hits = 0

    for label, pattern in SECRET_PATTERNS:
        def _mask(m: re.Match, label=label) -> str:  # noqa: ANN001
            nonlocal hits
            hits += 1
            return f"[REDACTED:{label}]"

        text = pattern.sub(_mask, text)

    return text, hits
