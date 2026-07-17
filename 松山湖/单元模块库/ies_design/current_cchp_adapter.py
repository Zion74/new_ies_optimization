from __future__ import annotations

from pathlib import Path
from typing import Any


class CurrentCCHPAdapter:
    """Convert a resolved scenario to the existing case_config dict shape."""

    DEVICE_ORDER = [
        "pv",
        "wind",
        "chp",
        "electric_heat_pump",
        "electric_chiller",
        "absorption_chiller",
        "electric_storage",
        "heat_storage",
        "cold_storage",
    ]

    @classmethod
    def to_case_config(cls, resolved: dict[str, Any], project_root: str | Path | None = None) -> dict[str, Any]:
        project_root = Path(project_root) if project_root else Path(__file__).resolve().parents[3]
        scenario = resolved.get("scenario", {})
        data = resolved.get("data", {})
        devices = resolved.get("devices", {})
        prices = resolved.get("prices", {})
        thermo = resolved.get("thermodynamics", {})
        carnot = resolved.get("carnot_battery", {})

        config: dict[str, Any] = {
            "name": scenario.get("id", "scenario"),
            "description": scenario.get("description", scenario.get("name", "")),
            "currency": _currency_symbol(scenario.get("currency", "")),
            "data_file": str(_resolve_project_path(project_root, data.get("load_file"))),
            "typical_day_file": str(_resolve_project_path(project_root, data.get("typical_day_file") or resolved.get("typical_day", {}).get("file"))),
            "ele_price": _price_to_24h(prices.get("electricity", {})),
            "gas_price": _price_to_24h(prices.get("gas", {})),
            "capacity_charge": prices.get("capacity_charge", {}).get("value", 0) or 0,
            "var_ub": [cls._device_capacity_ub(devices.get(device_id, {})) for device_id in cls.DEVICE_ORDER],
            "invest_coeff": [cls._device_invest_coeff(devices.get(device_id, {})) for device_id in cls.DEVICE_ORDER],
            "storage_fixed_cost": resolved.get("storage_fixed_cost", _default_storage_fixed_cost(scenario.get("id"))),
            "gt_eta_e": _param(devices.get("chp", {}), "eta_e", 0.35),
            "gt_eta_h": _param(devices.get("chp", {}), "eta_h", 0.45),
            "ac_cop": _param(devices.get("absorption_chiller", {}), "cop", 0.75),
            "ac_heat_ratio": _param(devices.get("absorption_chiller", {}), "heat_ratio", 0.983),
            "ac_ele_ratio": _param(devices.get("absorption_chiller", {}), "ele_ratio", 0.017),
            "ehp_cop": _param(devices.get("electric_heat_pump", {}), "cop", 4.0),
            "ec_cop": _param(devices.get("electric_chiller", {}), "cop", 3.5),
            "es_charge_eff": _param(devices.get("electric_storage", {}), "charge_efficiency", 0.95),
            "es_discharge_eff": _param(devices.get("electric_storage", {}), "discharge_efficiency", 0.90),
            "es_loss_rate": _param(devices.get("electric_storage", {}), "loss_rate", 0.000125),
            "hs_cs_charge_eff": _param(devices.get("heat_storage", {}), "charge_efficiency", 0.90),
            "hs_cs_discharge_eff": _param(devices.get("heat_storage", {}), "discharge_efficiency", 0.90),
            "hs_cs_loss_rate": _param(devices.get("heat_storage", {}), "loss_rate", 0.001),
            "T0": thermo.get("T0", 298.15),
            "T_heat": thermo.get("T_heat", 343.15),
            "T_cool": thermo.get("T_cool", 280.15),
            "enable_carnot_battery": bool(carnot.get("enabled", False)),
            "cb_power_ub": carnot.get("power_ub_kw", 0) or 0,
            "cb_capacity_ub": carnot.get("capacity_ub_kwh", 0) or 0,
            "cb_rte": carnot.get("round_trip_efficiency", 0.60),
            "cb_loss_rate": carnot.get("loss_rate", 0.002),
            "cb_invest_power": carnot.get("invest_power_coeff", 0),
            "cb_invest_capacity": carnot.get("invest_capacity_coeff", 0),
        }
        _apply_carnot_lambda(config)
        return config

    @staticmethod
    def _device_capacity_ub(device: dict[str, Any]) -> float:
        if not device or not device.get("enabled", False):
            return 0
        return (
            device.get("capacity_ub_kw")
            or device.get("power_ub_kw")
            or device.get("fixed_capacity_kw")
            or device.get("capacity", {}).get("upper_bound")
            or 0
        )

    @staticmethod
    def _device_invest_coeff(device: dict[str, Any]) -> float:
        if not device or not device.get("enabled", False):
            return 0
        return device.get("economics", {}).get("invest_coeff", 0) or 0


def _price_to_24h(price: dict[str, Any]) -> list[float]:
    if not price:
        return [0.0] * 24
    price_type = price.get("type", "flat")
    if price_type == "time_of_use":
        values = price.get("values", [])
        if len(values) != 24:
            raise ValueError("time_of_use price must provide 24 values")
        return list(values)
    return [float(price.get("value", 0) or 0)] * 24


def _param(device: dict[str, Any], name: str, default: float) -> float:
    return device.get("parameters", {}).get(name, default)


def _resolve_project_path(project_root: Path, maybe_path: str | None) -> Path:
    if not maybe_path:
        return project_root
    path = Path(maybe_path)
    if path.is_absolute():
        return path
    return project_root / path


def _currency_symbol(currency: str) -> str:
    mapping = {"CNY": "¥", "RMB": "¥", "EUR": "€", "EURO": "€", "USD": "$"}
    return mapping.get(str(currency).upper(), currency)


def _default_storage_fixed_cost(scenario_id: str | None) -> float:
    if scenario_id == "songshan_lake":
        return 3600
    return 520


def _apply_carnot_lambda(config: dict[str, Any]) -> None:
    t0 = config["T0"]
    t_heat = config["T_heat"]
    t_cool = config["T_cool"]
    config["lambda_e"] = 1.0
    config["lambda_h"] = 1.0 - t0 / t_heat
    config["lambda_c"] = t0 / t_cool - 1.0
