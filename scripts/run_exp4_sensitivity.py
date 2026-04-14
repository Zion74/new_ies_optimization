#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Convenience wrapper for exp4-style parameter sensitivity analysis.

Exp4 in the paper corresponds to:
    - case: songshan_lake
    - carnot: enabled
    - methods: std + euclidean
    - inherit_population: enabled (default in custom mode)

Example
-------
uv run python scripts/run_exp4_sensitivity.py --workers 28
"""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_parameter_sensitivity


def main() -> None:
    forwarded = sys.argv[1:]
    sys.argv = [
        "run_parameter_sensitivity.py",
        "--mode",
        "custom",
        "--case",
        "songshan_lake",
        "--methods",
        "std",
        "euclidean",
        "--carnot",
        *forwarded,
    ]
    run_parameter_sensitivity.main()


if __name__ == "__main__":
    main()
