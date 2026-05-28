from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class UnitConversionError(ValueError):
    """Raised when a carrier value cannot be converted to solver units."""


@dataclass(frozen=True)
class CarrierUnitRule:
    carrier: str
    internal_power_unit: str
    direct_power_units: tuple[str, ...]
    factors_to_internal_power: dict[str, float]
    note: str = ""


class CarrierUnitRegistry:
    """Convert user-facing carrier units into linear Energy Hub solver units."""

    def __init__(self, rules: dict[str, CarrierUnitRule]):
        self.rules = rules

    @classmethod
    def default(cls) -> "CarrierUnitRegistry":
        return cls({
            "electricity": CarrierUnitRule("electricity", "kW", ("kW",), {}),
            "heat": CarrierUnitRule("heat", "kW", ("kW", "kW_th"), {}),
            "cooling": CarrierUnitRule("cooling", "kW", ("kW",), {}),
            # Approximate low-pressure steam enthalpy conversion for acceptance modeling.
            "steam": CarrierUnitRule(
                "steam",
                "kW_th",
                ("kW", "kW_th"),
                {"t/h": 627.8, "kg/h": 0.6278},
                note="Default acceptance conversion: 1 t/h steam = 627.8 kW_th.",
            ),
            # Lower heating value approximation for natural gas.
            "natural_gas": CarrierUnitRule(
                "natural_gas",
                "kW_fuel",
                ("kW", "kWh/h", "kW_fuel"),
                {"Nm3/h": 9.97},
                note="Default acceptance conversion: 1 Nm3/h natural gas = 9.97 kW_fuel.",
            ),
            "waste_heat": CarrierUnitRule("waste_heat", "kW", ("kW", "kW_th"), {}),
            "solar_resource": CarrierUnitRule("solar_resource", "W/m2", ("W/m2",), {}),
            "temperature": CarrierUnitRule("temperature", "degC", ("degC", "C"), {}),
        })

    def convert_power(self, value: Any, carrier: str, from_unit: str | None) -> float:
        number = _float(value)
        unit = (from_unit or "").strip()
        rule = self.rules.get(carrier)
        if not rule:
            raise UnitConversionError(f"no unit rule for carrier {carrier} from {unit or '<missing>'}")
        if unit in rule.direct_power_units or unit == rule.internal_power_unit:
            return number
        if unit in rule.factors_to_internal_power:
            return number * rule.factors_to_internal_power[unit]
        raise UnitConversionError(
            f"cannot convert {carrier} from {unit or '<missing>'} to {rule.internal_power_unit}"
        )

    def internal_power_unit(self, carrier: str) -> str:
        rule = self.rules.get(carrier)
        return rule.internal_power_unit if rule else ""

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "carrier": rule.carrier,
                "internal_power_unit": rule.internal_power_unit,
                "direct_power_units": list(rule.direct_power_units),
                "factors_to_internal_power": dict(rule.factors_to_internal_power),
                "note": rule.note,
            }
            for rule in self.rules.values()
        ]


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise UnitConversionError(f"invalid numeric value {value!r}") from exc
