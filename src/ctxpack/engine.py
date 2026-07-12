"""Async orchestration: read candidate files, classify, guard, rank, render.

This module is intentionally the only "glue" file — everything it calls
into (secret_guard, binary_guard, tokens, priority, dependency_graph,
budget, render) is independently unit-testable without touching asyncio or
the filesystem.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

try:
    import aiofiles
except ImportError:
    print(
        "[pack_engine] error: 'aiofiles' is required. Install with: "
        "pip install aiofiles",
        file=sys.stderr,
    )
    sys.exit(1)

from .binary_guard import looks_binary
from .budget import fit_to_budget
from .dependency_graph import build_dependency_graph, propagate_priority
from .models import FileRecord
from .priority import load_priority_config
from .render import render_markdown
from .secret_guard import mask_secrets
from .tokens import count_tokens, backend as token_backend
from .ui import ProgressReporter, log, warn, alert, print_summary

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB — beyond this, skip with a warning
CONCURRENCY_LIMIT = 64            # cap simultaneous open files


# ---------------------------------------------------------------------------
# Async file processing
# ---------------------------------------------------------------------------
async def process_file(path: Path, root: Path, sem: asyncio.Semaphore, priority_cfg) -> FileRecord:
    rel = str(path.relative_to(root))
    rec = FileRecord(abs_path=path, rel_path=rel, priority=priority_cfg.classify(rel))
    rec.effective_priority = rec.priority

    async with sem:
        try:
            size = path.stat().st_size
        except OSError as e:
            rec.skipped_reason = f"stat failed: {e}"
            return rec

        if size == 0:
            rec.skipped_reason = "empty file"
            return rec

        if size > MAX_FILE_BYTES:
            rec.skipped_reason = f"too large ({size / 1024:.0f} KB > {MAX_FILE_BYTES // 1024} KB limit)"
            return rec

        try:
            async with aiofiles.open(path, "rb") as f:
                raw = await f.read()
        except OSError as e:
            rec.skipped_reason = f"read error: {e}"
            return rec

        if looks_binary(raw[:4096]):
            rec.skipped_reason = "binary file"
            return rec

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("latin-1")
                warn(f"{rel}: decoded as latin-1 (non-UTF-8 content)")
            except Exception as e:
                rec.skipped_reason = f"encoding error: {e}"
                return rec

        if path.name.startswith(".env"):
            warn(f"{rel}: looks like an environment file — values will be masked")

        masked_text, hits = mask_secrets(text, rel)
        if hits:
            alert(f"{rel}: masked {hits} potential secret(s)")

        rec.content = masked_text
        rec.tokens = count_tokens(masked_text)
        rec.secrets_found = hits
        rec.ok = True
        return rec


async def process_all(paths: list[Path], root: Path, priority_cfg) -> list[FileRecord]:
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
    tasks = [process_file(p, root, sem, priority_cfg) for p in paths]
    records: list[FileRecord] = []

    with ProgressReporter(total=len(tasks), description="Reading files") as progress:
        for coro in asyncio.as_completed(tasks):
            rec = await coro
            records.append(rec)
            progress.advance()

    return records


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def read_stdin_paths() -> list[Path]:
    raw = sys.stdin.buffer.read()
    if not raw:
        return []
    parts = raw.split(b"\x00")
    return [Path(p.decode("utf-8", errors="replace")) for p in parts if p]


async def main_async(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = read_stdin_paths()

    if not paths:
        warn("No file paths received on stdin.")
        return 0

    priority_cfg = load_priority_config(root, explicit_path=args.config)
    if priority_cfg.source_path is not None:
        log(f"Loaded priority rules from {priority_cfg.source_path}")

    log(f"Processing {len(paths)} file(s) with up to {CONCURRENCY_LIMIT} concurrent readers...")
    start = time.monotonic()
    records = await process_all(paths, root, priority_cfg)
    elapsed = time.monotonic() - start

    skipped = [r for r in records if not r.ok]
    ok_records = [r for r in records if r.ok]

    # Dependency-graph-aware priority propagation: a file imported by a
    # higher-priority (lower tier number) file gets pulled up to match.
    contents = {r.rel_path: r.content for r in ok_records}
    dependencies, _dependents = build_dependency_graph(contents)
    base_tiers = {r.rel_path: r.priority for r in ok_records}
    effective_tiers, boosted = propagate_priority(base_tiers, dependencies)
    for r in ok_records:
        r.effective_priority = effective_tiers.get(r.rel_path, r.priority)

    included, dropped_for_budget = fit_to_budget(records, args.budget)
    total_tokens = sum(r.tokens for r in included)

    print_summary(
        total_files=len(records),
        included=len(included),
        skipped=len(skipped),
        dropped_for_budget=len(dropped_for_budget),
        total_tokens=total_tokens,
        budget=args.budget,
        elapsed=elapsed,
        dependency_boosted=boosted,
    )

    if args.budget > 0 and dropped_for_budget:
        warn(f"{len(dropped_for_budget)} file(s) did not fit in the "
             f"{args.budget:,}-token budget and were omitted (see report).")

    markdown = render_markdown(
        root_name=root.name,
        included=included,
        dropped_for_budget=dropped_for_budget,
        skipped=skipped,
        budget=args.budget,
        elapsed=elapsed,
        token_backend=token_backend(),
    )

    out_path = Path(args.output)
    async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
        await f.write(markdown)

    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ctx-pack async processing engine")
    p.add_argument("--root", required=True, help="Root directory paths are relative to")
    p.add_argument("--output", required=True, help="Markdown output file path")
    p.add_argument("--budget", type=int, default=0, help="Token budget (0 = unlimited)")
    p.add_argument("--config", default=None, help="Explicit path to a .ctxpackrc file")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    try:
        status = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        warn("Interrupted.")
        status = 130
    sys.exit(status)


if __name__ == "__main__":
    main()
