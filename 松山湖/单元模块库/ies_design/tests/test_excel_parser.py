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


def test_parser_accepts_common_chinese_field_aliases():
    import openpyxl

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "alias.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "01_场景信息"
        ws.append(["字段", "值"])
        ws.append(["场景编号", "alias_case"])
        ws.append(["场景名称", "别名场景"])
        ws.append(["场景类型", "highway_transport_green_energy"])
        ws.append(["币种", "CNY"])
        for sheet in ExcelScenarioParser.REQUIRED_SHEETS[1:]:
            wb.create_sheet(sheet)
        wb["02_场景能源配置"].append(["条目ID", "类型分组", "是否启用", "是否必需"])
        wb["02_场景能源配置"].append(["electricity", "demand", "是", "是"])
        wb["06_候选设备配置"].append(["设备编号", "设备库编号", "是否启用", "容量上限"])
        wb["06_候选设备配置"].append(["pv", "pv_standard", "是", 100])
        wb["07_价格与排放参数"].append(["参数ID", "能源载体", "参数类型", "数值", "单位"])
        wb["07_价格与排放参数"].append(["ele_price", "electricity", "price", 0.7, "CNY_per_kWh"])
        wb["04_用户负荷需求曲线"].append(["需求ID", "数值"])
        wb["05_能源输入与资源曲线"].append(["输入ID", "数值"])
        wb["08_资料来源与缺口"].append(["data_item", "status"])
        wb.save(path)

        parsed = ExcelScenarioParser.parse(path)

    assert parsed.scenario["scenario"]["id"] == "alias_case"
    assert parsed.scenario["scenario"]["name"] == "别名场景"
    assert parsed.scenario["devices"]["pv"]["library_id"] == "pv_standard"
    assert parsed.scenario["prices"]["electricity"]["value"] == 0.7


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
