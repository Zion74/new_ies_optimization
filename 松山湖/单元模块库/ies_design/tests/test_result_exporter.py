import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from schema_validator import ValidationResult
from result_exporter import ResultExporter


def write_pareto(path: Path):
    path.parent.mkdir(parents=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Solution_ID", "Economic_Cost", "Matching_Index", "PV", "GT", "EC"])
        writer.writerow([0, 100.0, 30.0, 10.0, 20.0, 30.0])
        writer.writerow([1, 80.0, 50.0, 11.0, 21.0, 31.0])
        writer.writerow([2, 999999999.0, 1.0, 12.0, 22.0, 32.0])


def test_exports_standard_design_files_and_filters_infeasible_recommendations():
    with tempfile.TemporaryDirectory() as tmp:
        result_dir = Path(tmp)
        write_pareto(result_dir / "Euclidean" / "Pareto_Euclidean.csv")
        resolved = {"scenario": {"id": "demo", "name": "Demo", "currency": "CNY"}}

        validation = ValidationResult(warnings=["demo warning"])

        outputs = ResultExporter.export(result_dir, resolved, validation=validation)

        assert outputs["pareto_solutions"].exists()
        assert outputs["design_summary"].exists()
        assert outputs["design_summary_wide"].exists()
        assert outputs["design_report"].exists()
        assert outputs["resolved_scenario"].exists()
        assert outputs["validation_report"].exists()

        wide = outputs["design_summary_wide"].read_text(encoding="utf-8")
        assert "min_cost" in wide
        assert "min_matching" in wide
        assert "999999999" not in wide
        assert "PV" in wide

        long_table = outputs["design_summary"].read_text(encoding="utf-8")
        assert "device_capacity" in long_table
        assert "economic_cost" in long_table

        resolved_json = outputs["resolved_scenario"].read_text(encoding="utf-8")
        assert '"id": "demo"' in resolved_json

        validation_report = outputs["validation_report"].read_text(encoding="utf-8")
        assert "demo warning" in validation_report


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
