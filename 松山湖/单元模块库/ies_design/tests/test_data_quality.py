import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_quality import DataQualityReporter

TOBACCO_DIR = ROOT / "scenarios" / "tobacco_factory"


def test_tobacco_profiles_pass_monthly_24h_completeness():
    report = DataQualityReporter.check_monthly_typical_profiles(
        TOBACCO_DIR / "typical_profiles.csv",
        required_profile_types=["electricity", "cooling", "steam"],
    )

    assert report["status"] == "ok"
    assert report["expected_rows"] == 864
    assert report["actual_rows"] == 864
    assert report["errors"] == []


def test_duplicate_month_hour_type_is_reported():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["month", "hour", "profile_type", "value", "unit"])
            writer.writeheader()
            writer.writerow({"month": 1, "hour": 0, "profile_type": "electricity", "value": 1, "unit": "kW"})
            writer.writerow({"month": 1, "hour": 0, "profile_type": "electricity", "value": 2, "unit": "kW"})

        report = DataQualityReporter.check_monthly_typical_profiles(path, ["electricity"])

    assert report["status"] == "blocked"
    assert any("duplicate" in item for item in report["errors"])


def test_non_numeric_value_is_reported():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bad.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["month", "hour", "profile_type", "value", "unit"])
            writer.writeheader()
            writer.writerow({"month": 1, "hour": 0, "profile_type": "electricity", "value": "abc", "unit": "kW"})

        report = DataQualityReporter.check_monthly_typical_profiles(path, ["electricity"])

    assert report["status"] == "blocked"
    assert any("non-numeric" in item for item in report["errors"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
