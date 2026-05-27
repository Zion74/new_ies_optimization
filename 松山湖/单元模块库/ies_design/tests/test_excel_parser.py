import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[2]
sys.path.insert(0, str(ROOT))

from excel_parser import ExcelScenarioParser
from scenario_loader import ScenarioLoader
from defaults_resolver import DefaultsResolver
from schema_validator import SchemaValidator
from generic_backend_planner import GenericBackendPlanner


TEMPLATE = PROJECT_ROOT / "松山湖" / "单元模块库" / "课题组场景整理模板.xlsx"
TOBACCO_TEMPLATE = (
    PROJECT_ROOT
    / "\u677e\u5c71\u6e56"
    / "\u5355\u5143\u6a21\u5757\u5e93"
    / "\u8bfe\u9898\u7ec4\u573a\u666f\u6574\u7406\u6a21\u677f_\u70df\u5382_\u6e05\u6d17\u7248.xlsx"
)


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

def test_tobacco_excel_uses_future_generic_template():
    parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)

    assert parsed.scenario["scenario"]["scenario_type"] == "tobacco_factory_multi_energy"
    assert parsed.scenario["system"]["template"] == "tobacco_factory_multi_energy"


def test_tobacco_excel_preserves_storage_energy_capacity_upper_bound():
    parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)

    assert parsed.scenario["devices"]["heat_storage"]["energy_capacity_ub_kwh"] == 25586.9


def test_tobacco_excel_preserves_hourly_electricity_price():
    parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)

    price = parsed.scenario["prices"]["electricity"]
    assert price["type"] == "tou_24h"
    assert len(price["values"]) == 24
    assert price["values"][0] == 0.35
    assert price["values"][17] == 1.3


def test_exported_excel_scenario_references_intermediate_data_files():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)

        outputs = parsed.export(out_dir)
        scenario = ScenarioLoader.load(outputs["scenario_yaml"])

    assert scenario["data"]["load_file"] == "typical_profiles.csv"
    assert scenario["data"]["resource_file"] == "input_resource_profiles.csv"
    assert scenario["typical_day"]["file"] == "typical_profiles.csv"


def test_exported_excel_scenario_validates_relative_files_from_scenario_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)
        outputs = parsed.export(out_dir)
        scenario = ScenarioLoader.load(outputs["scenario_yaml"])
        resolved = DefaultsResolver(ROOT / "defaults").resolve(scenario)

        result = SchemaValidator.validate(resolved, project_root=PROJECT_ROOT)

    assert not any("does not exist yet" in warning for warning in result.warnings)


def test_tobacco_component_plan_uses_storage_energy_capacity_bound():
    parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)
    resolved = DefaultsResolver(ROOT / "defaults").resolve(parsed.scenario)

    plan = GenericBackendPlanner.plan(resolved)
    heat_storage_energy = next(
        item
        for item in plan["capacity_variables"]
        if item["device_id"] == "heat_storage" and item["variable_name"] == "capacity_kwh"
    )
    heat_storage_gaps = [
        gap for gap in plan["parameter_gaps"] if gap["device_id"] == "heat_storage"
    ]

    assert heat_storage_energy["upper_bound"] == 25586.9
    assert not any(gap["field"] == "capacity.capacity_kwh" for gap in heat_storage_gaps)


def test_tobacco_validation_distinguishes_storage_energy_and_power_bounds():
    parsed = ExcelScenarioParser.parse(TOBACCO_TEMPLATE)
    resolved = DefaultsResolver(ROOT / "defaults").resolve(parsed.scenario)

    result = SchemaValidator.validate(resolved, project_root=PROJECT_ROOT)

    assert not any(
        warning == "enabled device heat_storage has no capacity/power upper bound"
        for warning in result.warnings
    )
    assert any(
        "heat_storage" in warning and "power upper bound" in warning and "energy capacity" in warning
        for warning in result.warnings
    )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
