"""Shared data structures passed between pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FileRecord:
    abs_path: Path
    rel_path: str
    ok: bool = False
    skipped_reason: Optional[str] = None
    content: str = ""
    tokens: int = 0
    priority: int = 1          # base tier from priority.py
    effective_priority: int = 1  # after dependency-graph propagation
    secrets_found: int = 0
    included: bool = False
