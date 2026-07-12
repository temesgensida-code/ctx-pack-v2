"""Greedy token-budget fitting.

Ranking key is (effective_priority, tokens) — effective_priority already
folds in the dependency-graph boost (see dependency_graph.py), so this
module stays a plain greedy-fit algorithm and doesn't need to know anything
about imports itself.
"""

from __future__ import annotations

from .models import FileRecord


def fit_to_budget(
    records: list[FileRecord], budget: int
) -> tuple[list[FileRecord], list[FileRecord]]:
    """Greedily include files by (effective_priority asc, tokens asc) until
    the budget is exhausted. Returns (included, dropped_for_budget), both
    restricted to files that were readable in the first place (r.ok)."""
    ok_records = [r for r in records if r.ok]

    if budget <= 0:
        for r in ok_records:
            r.included = True
        return ok_records, []

    ranked = sorted(ok_records, key=lambda r: (r.effective_priority, r.tokens))
    included: list[FileRecord] = []
    dropped: list[FileRecord] = []
    running_total = 0

    for r in ranked:
        if running_total + r.tokens <= budget:
            r.included = True
            included.append(r)
            running_total += r.tokens
        else:
            dropped.append(r)

    # Preserve original discovery order for the final render; budget logic
    # only decided *membership*, not display order.
    included_set = {id(r) for r in included}
    ordered_included = [r for r in ok_records if id(r) in included_set]
    return ordered_included, dropped
