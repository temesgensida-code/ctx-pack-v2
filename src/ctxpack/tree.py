"""ASCII directory tree rendering for the Markdown header section."""

from __future__ import annotations

from pathlib import Path


def build_ascii_tree(rel_paths: list[str]) -> str:
    tree: dict = {}
    for rel in rel_paths:
        parts = Path(rel).parts
        node = tree
        for part in parts:
            node = node.setdefault(part, {})

    lines: list[str] = ["."]

    def _walk(node: dict, prefix: str = "") -> None:
        entries = sorted(node.items(), key=lambda kv: kv[0].lower())
        for i, (name, child) in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}")
            if child:
                extension = "    " if is_last else "│   "
                _walk(child, prefix + extension)

    _walk(tree)
    return "\n".join(lines)
