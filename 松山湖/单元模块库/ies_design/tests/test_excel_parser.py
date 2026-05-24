import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from excel_parser import ExcelScenarioParser
from scenario_loader import ScenarioLoader


TEMPLATE = PROJECT_ROOT / "松山湖" / "单元模块库" / "课题组场景整理模板.xlsx"


def test_empty_template_parses_with_user_friendly_warnings():
    parsed = ExcelScenarioParser.parse(TEMPLATE)

    assert parsed.scenario["scenario"]["currency"] == "CNY"
    assert "electricity" in parsed.scenario["energy_carriers"]["demands"]
    assert parsed.warnings
    assert any("scenario_id" in warning for warning in parsed.warnings)


def test_export_writes_standard_intermediate_files():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        parsed = ExcelScenarioParser.parse(TEMPLATE)

        outputs = parsed.export(out_dir)

        assert outputs["scenario_yaml"].exists()
        assert outputs["typical_profiles"].exists()
        assert outputs["input_resource_profiles"].exists()
        assert outputs["data_gaps"].exists()

        scenario = ScenarioLoader.load(outputs["scenario_yaml"])
        assert scenario["scenario"]["currency"] == "CNY"
        assert scenario["energy_carriers"]["demands"] == ["electricity"]

        with outputs["data_gaps"].open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert "data_item" in rows[0]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
