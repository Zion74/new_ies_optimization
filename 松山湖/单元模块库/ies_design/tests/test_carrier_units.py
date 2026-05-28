import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carrier_units import CarrierUnitRegistry, UnitConversionError


def test_steam_t_per_hour_converts_to_kw_th():
    registry = CarrierUnitRegistry.default()

    value = registry.convert_power(1.0, carrier="steam", from_unit="t/h")

    assert round(value, 1) == 627.8


def test_steam_kg_per_hour_converts_to_kw_th():
    registry = CarrierUnitRegistry.default()

    value = registry.convert_power(1000.0, carrier="steam", from_unit="kg/h")

    assert round(value, 1) == 627.8


def test_natural_gas_nm3_per_hour_converts_to_kw_fuel():
    registry = CarrierUnitRegistry.default()

    value = registry.convert_power(1.0, carrier="natural_gas", from_unit="Nm3/h")

    assert round(value, 2) == 9.97


def test_direct_kw_carriers_are_unchanged():
    registry = CarrierUnitRegistry.default()

    assert registry.convert_power(123.4, carrier="electricity", from_unit="kW") == 123.4
    assert registry.convert_power(55.0, carrier="cooling", from_unit="kW") == 55.0


def test_missing_conversion_raises_clear_error():
    registry = CarrierUnitRegistry.default()

    try:
        registry.convert_power(1.0, carrier="hydrogen", from_unit="kg/h")
    except UnitConversionError as exc:
        assert "hydrogen" in str(exc)
        assert "kg/h" in str(exc)
    else:
        raise AssertionError("expected UnitConversionError")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
