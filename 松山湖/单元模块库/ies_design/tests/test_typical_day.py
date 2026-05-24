import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from typical_day import TypicalDayGenerator


def read_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_monthly_template_generates_12_weighted_days():
    with tempfile.TemporaryDirectory() as tmp:
        outputs = TypicalDayGenerator.generate_monthly_template(Path(tmp))

        rows = read_rows(outputs["typical_days"])

        assert len(rows) == 12
        assert rows[0]["typicalDayId"] == "16"
        assert rows[0]["weight"] == "31"
        assert sum(int(row["weight"]) for row in rows) == 365
        assert outputs["report"].read_text(encoding="utf-8").startswith("# 典型日生成报告")


def test_read_user_selected_keeps_current_backend_columns():
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "typical.csv"
        source.write_text("typicalDayId,weight,days\n1,2,\"1,2\"\n", encoding="utf-8")

        rows = TypicalDayGenerator.read_user_selected(source)

        assert rows == [{"typicalDayId": 1, "weight": 2, "days": "1,2"}]


def test_cluster_from_8760_generates_requested_number_of_medoid_days():
    with tempfile.TemporaryDirectory() as tmp:
        data_file = Path(tmp) / "tiny_8760.csv"
        with data_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["ele_load(kW)", "heat_load(kW)"])
            for day in range(365):
                for hour in range(24):
                    writer.writerow([day % 7 + hour / 24, day % 3])

        outputs = TypicalDayGenerator.cluster_from_8760(
            data_file,
            Path(tmp) / "clustered",
            n_clusters=14,
            columns=["ele_load(kW)", "heat_load(kW)"],
        )
        rows = read_rows(outputs["typical_days"])

        assert len(rows) == 14
        assert sum(int(row["weight"]) for row in rows) == 365
        assert all(1 <= int(row["typicalDayId"]) <= 365 for row in rows)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
