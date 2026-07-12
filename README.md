# ctx-pack

A dual-layer (Bash + Python) CLI that scans a codebase, filters out noise,
audits for secrets, token-counts everything, and packs it into a single
LLM-optimized Markdown file — so you stop hand-picking files or blowing past
context limits when working with Claude/ChatGPT on a real repo.

## Architecture

```
ctx-pack/
├── bin/
│   └── ctx-pack               # Bash entry point: args, .gitignore ingestion, file discovery
├── src/
│   ├── pack_engine.py          # Thin backward-compatible shim -> ctxpack.engine
│   ├── ctxpack/                 # The actual engine, split into testable modules
│   │   ├── engine.py             # Async orchestration + CLI entry point
│   │   ├── ui.py                  # Logging, rich progress bar / summary (with plain fallback)
│   │   ├── tokens.py              # tiktoken-backed counting with offline heuristic fallback
│   │   ├── binary_guard.py        # Binary file detection
│   │   ├── secret_guard.py        # Regex secret detection + masking
│   │   ├── priority.py            # Priority tiers + .ctxpackrc loading
│   │   ├── dependency_graph.py    # Import-graph parsing + priority propagation
│   │   ├── budget.py              # Greedy token-budget fitting
│   │   ├── tree.py                # ASCII directory tree rendering
│   │   ├── render.py              # Final Markdown assembly
│   │   └── models.py              # Shared FileRecord dataclass
│   └── requirements.txt
├── tests/                    # pytest suite (66 tests: unit + integration)
├── .ctxpackrc.example         # Sample configurable priority rules
├── docs/
└── README.md
```

**Separation of concerns:**
- **Bash** owns everything OS-level and cheap: argument parsing, `.gitignore`
  parsing, `find`-based traversal and filtering. It never opens a file's
  contents — it only decides which paths are candidates, then streams them
  NUL-delimited over stdin to Python.
- **Python** owns everything that needs real logic: concurrent I/O
  (`asyncio` + `aiofiles`), binary/size/encoding safety checks, the secret
  guard, token budgeting/ranking, and Markdown rendering.

## Install

```bash
git clone <repo> ctx-pack
cd ctx-pack
pip install -r src/requirements.txt
chmod +x bin/ctx-pack
ln -s "$(pwd)/bin/ctx-pack" /usr/local/bin/ctx-pack   # optional, put it on PATH
```

## Usage

```bash
ctx-pack -d ./my-project -o context.md -b 30000
ctx-pack --exclude "*.lock" --exclude "dist/*" -b 50000
ctx-pack -d . --no-gitignore --include-hidden -v

# Pack only what changed, e.g. for a pre-PR review pass
git diff --name-only main... | ctx-pack --stdin-only -o review.md -b 20000
git diff --name-only --cached | ctx-pack --stdin-only -b 15000
```

| Flag | Description | Default |
|---|---|---|
| `-d, --dir` | Target directory to scan | `.` |
| `-o, --output` | Output markdown file | `ctx-pack.md` |
| `-b, --budget` | Token budget (0 = unlimited) | `0` |
| `--exclude` | Extra glob pattern to exclude (repeatable) | — |
| `--no-gitignore` | Don't honor `.gitignore` files | off |
| `--include-hidden` | Include dotfiles/dotdirs | off |
| `--stdin-only` | Read the file list from stdin instead of scanning `-d` | off |
| `--config FILE` | Explicit path to a `.ctxpackrc` priority-rules file | — |
| `-v, --verbose` | Verbose logging | off |

## Safety features

- **Secret guard**: regex-based scan for AWS keys, generic API keys/tokens,
  private key blocks, Slack tokens, JWTs, and password assignments. Matches
  are masked (`[REDACTED:...]`) and logged to stderr — never silently
  dropped, never silently leaked.
- **`.env` awareness**: files matching `.env*` are flagged explicitly even
  though their contents still go through the same masking pass.
- **Binary/size/encoding guards**: binary files are detected via a
  null-byte + non-text-ratio heuristic and skipped; files over 2 MB are
  skipped; non-UTF-8 files fall back to latin-1 with a warning, or are
  skipped if unreadable. All skips are reported in the final Markdown, never
  silently dropped.

## Token budgeting

If `tiktoken` can reach the network for its `cl100k_base` ranking file, exact
GPT-style token counts are used. Otherwise the engine falls back to a
`len(text) // 4` heuristic automatically — no crash, just a warning, and the
output notes which backend was used.

When a budget is set, files are greedily packed in priority order
(source code → config → docs → data/logs), smallest-first within a tier, and
anything that doesn't fit is listed in an "Omitted Due to Token Budget"
table rather than silently vanishing.

## Configurable priority rules (`.ctxpackrc`)

Drop a `.ctxpackrc` at your project root (or pass `--config path/to/file`)
to override which extensions get packed first when a budget is tight. See
`.ctxpackrc.example` for the format:

```
0: *.py *.rs *.go *.ts *.tsx *.js *.jsx
1: *.json *.yml *.yaml *.toml
2: *.md *.rst *.txt
3: *.lock *.log *.csv *.tsv
default: 1
```

Lower tier number = packed earlier. First matching pattern wins.

## Import-graph-aware ranking

Independent of `.ctxpackrc` tiers, ctx-pack does a lightweight best-effort
parse of `import`/`from ... import`/`require()` statements (Python and
JS/TS) across the candidate files and builds a local dependency graph. If a
tier-0 source file imports a file that would otherwise land in a lower
priority tier, that dependency's *effective* priority is pulled up to match
— so a small `constants.py` imported by your main module gets packed
alongside it instead of being bumped for an unrelated file at the same
nominal tier. The run summary reports how many files were boosted this way.

## `--stdin-only`: pack an arbitrary file list

Instead of scanning a directory, pipe an explicit file list in — handy for
packing just what changed:

```bash
git diff --name-only main... | ctx-pack --stdin-only -o review.md -b 20000
```

Paths are still resolved against `-d`/`--dir` and run through the same
exclude rules, so a stray `node_modules/` entry in the list still gets
filtered out.

## Rich terminal UI

If [`rich`](https://github.com/Textualize/rich) is installed, ctx-pack uses
it for a live progress bar and a boxed summary panel (files scanned,
included/skipped/dropped counts, dependency-boost count, token usage). If
`rich` isn't available, everything falls back automatically to a
dependency-free ANSI progress bar — the tool never hard-requires it.

## Tests

```bash
pip install -r src/requirements.txt
pytest
```

66 tests across 6 files: secret-pattern coverage (one test per pattern type
plus false-positive checks), binary detection edge cases, budget
boundary/tie-breaking behavior, `.ctxpackrc` parsing, dependency-graph
propagation (including cyclic-import safety), and full subprocess-level
integration tests that exercise the real bash → Python pipeline end to end.

## Roadmap (round three)

- [ ] AST-based import resolution instead of regex, for fewer edge-case misses
- [ ] Config discovery up the directory tree (like `.eslintrc` resolution)
- [ ] `--json` output mode for piping into other tooling
- [ ] Parallel `.gitignore` ingestion for very large monorepos
