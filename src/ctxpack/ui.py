"""Terminal UX: colors, logging, and progress/summary rendering.

Uses `rich` when it's installed for a polished progress bar and summary
table. Falls back to a dependency-free ANSI implementation otherwise, so the
tool never hard-requires `rich` to run.
"""

from __future__ import annotations

import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.progress import (
        Progress, BarColumn, TextColumn, TimeElapsedColumn, MofNCompleteColumn,
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"


def log(msg: str, color: str = Ansi.CYAN) -> None:
    print(f"{color}[pack_engine]{Ansi.RESET} {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"{Ansi.YELLOW}[pack_engine][warn]{Ansi.RESET} {msg}", file=sys.stderr)


def alert(msg: str) -> None:
    print(f"{Ansi.RED}[pack_engine][secret-guard]{Ansi.RESET} {msg}", file=sys.stderr)


class ProgressReporter:
    """Thin wrapper that presents the same interface whether or not `rich`
    is installed. Usage:

        with ProgressReporter(total=N) as p:
            for ... :
                p.advance()
    """

    def __init__(self, total: int, description: str = "Reading files"):
        self.total = total
        self.description = description
        self._rich_progress: Optional["Progress"] = None
        self._rich_task = None
        self._done = 0

    def __enter__(self) -> "ProgressReporter":
        if RICH_AVAILABLE and self.total > 0:
            self._rich_progress = Progress(
                TextColumn("[cyan][pack_engine][/cyan] {task.description}"),
                BarColumn(bar_width=30, complete_style="green", finished_style="green"),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=Console(stderr=True),
                transient=False,
            )
            self._rich_progress.__enter__()
            self._rich_task = self._rich_progress.add_task(self.description, total=self.total)
        return self

    def advance(self, n: int = 1) -> None:
        self._done += n
        if self._rich_progress is not None:
            self._rich_progress.update(self._rich_task, advance=n)
        else:
            self._render_plain()

    def _render_plain(self, width: int = 30) -> None:
        frac = self._done / self.total if self.total else 1.0
        filled = int(width * frac)
        bar = "█" * filled + "░" * (width - filled)
        print(
            f"\r{Ansi.CYAN}[pack_engine]{Ansi.RESET} {self.description} "
            f"[{Ansi.GREEN}{bar}{Ansi.RESET}] {self._done}/{self.total}",
            end="",
            file=sys.stderr,
            flush=True,
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._rich_progress is not None:
            self._rich_progress.__exit__(exc_type, exc, tb)
        else:
            print(file=sys.stderr)  # newline after the plain progress bar


def render_budget_bar(used: int, budget: int, width: int = 30) -> str:
    frac = min(1.0, used / budget) if budget else 0.0
    filled = int(width * frac)
    color = Ansi.GREEN if frac < 0.8 else (Ansi.YELLOW if frac < 1.0 else Ansi.RED)
    bar = "█" * filled + "░" * (width - filled)
    pct = frac * 100
    return f"[{color}{bar}{Ansi.RESET}] {used:,}/{budget:,} tokens ({pct:.1f}%)"


def print_summary(
    *,
    total_files: int,
    included: int,
    skipped: int,
    dropped_for_budget: int,
    total_tokens: int,
    budget: int,
    elapsed: float,
    dependency_boosted: int = 0,
) -> None:
    """Render the end-of-run summary. Uses a rich Table when available,
    otherwise falls back to plain aligned text."""

    if RICH_AVAILABLE:
        console = Console(stderr=True)
        table = Table(title="ctx-pack summary", show_header=False, box=None, padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column()
        table.add_row("Files scanned", str(total_files))
        table.add_row("Included", f"[green]{included}[/green]")
        table.add_row("Skipped", f"[yellow]{skipped}[/yellow]" if skipped else "0")
        if budget > 0:
            table.add_row("Dropped for budget", f"[red]{dropped_for_budget}[/red]" if dropped_for_budget else "0")
        if dependency_boosted:
            table.add_row("Priority-boosted (deps)", str(dependency_boosted))
        table.add_row("Total tokens", f"{total_tokens:,}" + (f" / {budget:,}" if budget > 0 else ""))
        table.add_row("Elapsed", f"{elapsed:.2f}s")
        console.print(Panel(table, expand=False, border_style="cyan"))
        if budget > 0:
            frac = min(1.0, total_tokens / budget) if budget else 0.0
            bar_style = "green" if frac < 0.8 else ("yellow" if frac < 1.0 else "red")
            console.print(
                Text(f"Budget usage: {total_tokens:,}/{budget:,} tokens ({frac*100:.1f}%)", style=bar_style)
            )
    else:
        log(f"Read {total_files} file(s) in {elapsed:.2f}s "
            f"({included} included, {skipped} skipped, {dropped_for_budget} dropped for budget)")
        if dependency_boosted:
            log(f"{dependency_boosted} file(s) priority-boosted as direct dependencies")
        if budget > 0:
            log(render_budget_bar(total_tokens, budget), color=Ansi.MAGENTA)
        else:
            log(f"Total tokens (no budget set): {total_tokens:,}")
