import sys
import tempfile
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from cchp_gasolution import generate_comparison_report


class FakeBestIndi:
    sizes = 1
    ObjV = np.array([[1234.5, 6.7]])
    Phen = np.array([[1, 2, 3, 4, 5, 6, 7, 8, 9]])


def test_comparison_report_uses_case_currency():
    results = {
        "euclidean": {
            "name": "方案C-能质耦合匹配度(本文)",
            "best_indi": FakeBestIndi(),
            "time": 1.2,
        }
    }
    with tempfile.TemporaryDirectory() as tmp:
        generate_comparison_report(results, tmp, inherit_population=False, case_config={"currency": "CNY"})
        report = (Path(tmp) / "comparison_report.md").read_text(encoding="utf-8")

    assert "最低成本(CNY)" in report
    assert "最低成本(€)" not in report


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")

