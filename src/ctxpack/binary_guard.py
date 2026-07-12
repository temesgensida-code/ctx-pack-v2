"""Binary-file detection.

A file is treated as binary if it contains a NUL byte, or if a large
fraction of its bytes fall outside the "plausible text" range. Both checks
run on a small sample (the first few KB), never the whole file, so this
stays cheap even on huge files.
"""

from __future__ import annotations

_TEXT_CHARS = bytearray(
    {7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7F}
)


def looks_binary(sample: bytes, nontext_threshold: float = 0.30) -> bool:
    if not sample:
        return False
    if b"\x00" in sample:
        return True
    nontext = sum(byte not in _TEXT_CHARS for byte in sample)
    return (nontext / len(sample)) > nontext_threshold
