#!/usr/bin/env python3
"""
Accuracy of a map_buildings.py run against Soroka & Duren's hand-labelled
Delmarva poultry houses (see geo_anom/task1/evaluate.py for method/caveats).

    python3 scripts/evaluate_run.py data/processed/task1/run_2026-10-07

Writes <run_dir>/accuracy.json and prints it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geo_anom.task1.evaluate import evaluate_run  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("run_dir", type=Path)
args = ap.parse_args()
res = evaluate_run(args.run_dir)
(args.run_dir / "accuracy.json").write_text(json.dumps(res, indent=2))
print(json.dumps(res, indent=2))
