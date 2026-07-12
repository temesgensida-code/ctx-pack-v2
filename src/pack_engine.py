#!/usr/bin/env python3
"""Backward-compatible entry point.

`bin/ctx-pack` invokes this file directly (`python3 src/pack_engine.py ...`).
All real logic now lives in the `ctxpack` package alongside this file, split
into small testable modules — see ctxpack/__init__.py for the map.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ctxpack.engine import main

if __name__ == "__main__":
    main()
