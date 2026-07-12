"""File priority tiers, used to decide packing order when a token budget is
tight (lower tier number = packed earlier).

Rules are configurable via a `.ctxpackrc` file so a project can say "our
config files matter as much as our source code" without editing the engine.
Search order for the config file:

  1. An explicit path passed via --config
  2. <scan root>/.ctxpackrc
  3. <current working directory>/.ctxpackrc
  4. Built-in defaults (no file needed)

.ctxpackrc format — plain text, one rule per line::

    # comments start with #
    0: *.py *.rs *.go *.ts *.tsx *.js *.jsx *.java *.kt *.c *.cpp *.h *.hpp *.rb *.php
    1: *.json *.yml *.yaml *.toml *.ini *.cfg
    2: *.md *.rst *.txt
    3: *.lock *.log *.csv *.tsv
    default: 1

Lower tier numbers win ties and are evaluated in the order they appear in
the file, first match wins per file.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_FILENAME = ".ctxpackrc"

# Built-in fallback, used whenever no .ctxpackrc is found.
_DEFAULT_RULES: list[tuple[int, list[str]]] = [
    (0, ["*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs", "*.java",
         "*.kt", "*.c", "*.cpp", "*.h", "*.hpp", "*.rb", "*.php"]),
    (1, ["*.json", "*.yml", "*.yaml", "*.toml", "*.ini", "*.cfg"]),
    (2, ["*.md", "*.rst", "*.txt"]),
    (3, ["*.lock", "*.log", "*.csv", "*.tsv"]),
]
_DEFAULT_TIER = 1


@dataclass
class PriorityConfig:
    rules: list[tuple[int, list[str]]] = field(default_factory=lambda: list(_DEFAULT_RULES))
    default_tier: int = _DEFAULT_TIER
    source_path: Optional[Path] = None  # None means "built-in defaults"

    def classify(self, rel_path: str) -> int:
        name = Path(rel_path).name
        for tier, patterns in self.rules:
            for pattern in patterns:
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern):
                    return tier
        return self.default_tier


def parse_ctxpackrc(text: str) -> PriorityConfig:
    rules: list[tuple[int, list[str]]] = []
    default_tier = _DEFAULT_TIER

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue  # tolerate stray lines rather than crashing a run
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue

        if key == "default":
            try:
                default_tier = int(value)
            except ValueError:
                pass
            continue

        try:
            tier = int(key)
        except ValueError:
            continue  # unrecognized key, ignore rather than fail the run

        patterns = value.split()
        if patterns:
            rules.append((tier, patterns))

    if not rules:
        rules = list(_DEFAULT_RULES)

    return PriorityConfig(rules=rules, default_tier=default_tier)


def load_priority_config(
    root: Path,
    explicit_path: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> PriorityConfig:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.append(root / CONFIG_FILENAME)
    candidates.append((cwd or Path.cwd()) / CONFIG_FILENAME)

    for candidate in candidates:
        try:
            if candidate.is_file():
                cfg = parse_ctxpackrc(candidate.read_text(encoding="utf-8"))
                cfg.source_path = candidate
                return cfg
        except OSError:
            continue

    return PriorityConfig()
