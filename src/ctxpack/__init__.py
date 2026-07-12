"""ctxpack — the processing engine behind ctx-pack.

Split into small, independently testable modules:

  ui               terminal output: colors, logging, progress bars (rich or plain fallback)
  tokens           token counting (tiktoken with heuristic fallback)
  binary_guard     binary-file detection
  secret_guard     regex-based secret detection + masking
  priority         file priority tiers, .ctxpackrc loading
  dependency_graph import-graph parsing + priority propagation
  budget           greedy budget-fitting over ranked files
  tree             ASCII directory tree rendering
  render           final Markdown document assembly
  engine           async orchestration + CLI entry point
"""

__version__ = "0.2.0"
