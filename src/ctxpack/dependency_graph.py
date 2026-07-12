"""Best-effort import-graph extraction + priority propagation.

The goal isn't a full import resolver (no venv/node_modules resolution,
no sys.path awareness) — it's a cheap, best-effort signal: "this file is a
direct dependency of a file we already decided matters, so pack it at the
same priority instead of wherever its own extension would otherwise land
it." A README that happens to be imported by nothing stays at its own tier;
a small `constants.py` imported by five tier-0 modules gets promoted to
tier 0 alongside them.

Supported so far: Python (`import x`, `from x import y`) and
JavaScript/TypeScript (`import ... from '...'`, `require('...')`). Both are
regex-based on purpose — an AST parser per language is more precise but far
more code for a "which files does this pull in" signal that's inherently
approximate anyway.
"""

from __future__ import annotations

import re
from pathlib import Path

_PY_IMPORT = re.compile(r"^\s*import\s+([\w\.]+)", re.MULTILINE)
_PY_FROM_IMPORT = re.compile(r"^\s*from\s+([\w\.]+)\s+import", re.MULTILINE)
_JS_IMPORT = re.compile(r"""import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""")
_JS_REQUIRE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")

_JS_EXTS = (".js", ".jsx", ".ts", ".tsx")


def _extract_refs(rel_path: str, text: str) -> list[str]:
    suffix = Path(rel_path).suffix.lower()
    refs: list[str] = []

    if suffix == ".py":
        refs.extend(_PY_IMPORT.findall(text))
        refs.extend(_PY_FROM_IMPORT.findall(text))
    elif suffix in _JS_EXTS:
        refs.extend(_JS_IMPORT.findall(text))
        refs.extend(_JS_REQUIRE.findall(text))

    return refs


def _resolve_python_ref(ref: str, candidates: set[str]) -> list[str]:
    # "pkg.module" -> "pkg/module.py" or "pkg/module/__init__.py"
    as_path = ref.replace(".", "/")
    matches = []
    for suffix in (".py",):
        candidate = f"{as_path}{suffix}"
        if candidate in candidates:
            matches.append(candidate)
        init_candidate = f"{as_path}/__init__.py"
        if init_candidate in candidates:
            matches.append(init_candidate)
    return matches


def _resolve_js_ref(ref: str, importer_rel: str, candidates: set[str]) -> list[str]:
    if not ref.startswith("."):
        return []  # skip node_modules / bare package imports, out of scope

    importer_dir = Path(importer_rel).parent
    base = (importer_dir / ref).as_posix()
    # normalize "./" and "../" segments
    base = str(Path(base))
    matches = []
    candidates_to_try = [base] + [f"{base}{ext}" for ext in _JS_EXTS] + \
        [f"{base}/index{ext}" for ext in _JS_EXTS]
    for candidate in candidates_to_try:
        normalized = candidate.replace("\\", "/").lstrip("./")
        if normalized in candidates:
            matches.append(normalized)
    return matches


def build_dependency_graph(
    contents: dict[str, str],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """contents: rel_path -> file text (only files that were actually read).

    Returns (dependencies, dependents):
      dependencies[file] = set of files that `file` imports
      dependents[file]   = set of files that import `file`
    """
    candidates = set(contents.keys())
    dependencies: dict[str, set[str]] = {rel: set() for rel in candidates}
    dependents: dict[str, set[str]] = {rel: set() for rel in candidates}

    for rel_path, text in contents.items():
        suffix = Path(rel_path).suffix.lower()
        for ref in _extract_refs(rel_path, text):
            if suffix == ".py":
                resolved = _resolve_python_ref(ref, candidates)
            elif suffix in _JS_EXTS:
                resolved = _resolve_js_ref(ref, rel_path, candidates)
            else:
                resolved = []

            for target in resolved:
                if target == rel_path:
                    continue
                dependencies[rel_path].add(target)
                dependents[target].add(rel_path)

    return dependencies, dependents


def propagate_priority(
    base_tiers: dict[str, int],
    dependencies: dict[str, set[str]],
) -> tuple[dict[str, int], int]:
    """A dependency's effective tier is pulled up to match the best
    (numerically lowest) tier of anything that imports it, transitively.

    Returns (effective_tiers, boosted_count).
    """
    effective = dict(base_tiers)
    changed = True
    # Fixed-point relaxation; bounded by node count so pathological/cyclic
    # import graphs can't spin forever.
    max_iterations = max(1, len(base_tiers))
    iterations = 0

    while changed and iterations < max_iterations:
        changed = False
        iterations += 1
        for importer, deps in dependencies.items():
            importer_tier = effective.get(importer)
            if importer_tier is None:
                continue
            for dep in deps:
                if dep not in effective:
                    continue
                if importer_tier < effective[dep]:
                    effective[dep] = importer_tier
                    changed = True

    boosted = sum(1 for k in effective if effective[k] < base_tiers.get(k, effective[k]))
    return effective, boosted
