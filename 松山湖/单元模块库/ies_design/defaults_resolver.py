from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from simple_yaml import load_yaml


class DefaultsResolver:
    """Merge scenario YAML with default catalogs and device metadata."""

    def __init__(self, defaults_dir: str | Path):
        self.defaults_dir = Path(defaults_dir)
        self.device_library = load_yaml(self.defaults_dir / "device_library.yaml")
        self.system_templates = load_yaml(self.defaults_dir / "system_templates.yaml")
        self.scenario_catalog = load_yaml(self.defaults_dir / "scenario_catalog.yaml")
        self.component_mapping = load_yaml(self.defaults_dir / "component_mapping.yaml")
        self.optimization_defaults = load_yaml(self.defaults_dir / "optimization_defaults.yaml")

    def resolve(self, scenario: dict[str, Any]) -> dict[str, Any]:
        resolved = copy.deepcopy(scenario)
        resolved["device_library"] = self.device_library
        resolved["component_mapping"] = self.component_mapping

        self._apply_scenario_type_defaults(resolved)
        self._apply_system_template_defaults(resolved)
        self._apply_optimization_defaults(resolved)
        self._resolve_devices(resolved)
        return resolved

    def _apply_scenario_type_defaults(self, resolved: dict[str, Any]) -> None:
        scenario_type = resolved.get("scenario", {}).get("scenario_type")
        catalog = self.scenario_catalog.get("scenario_types", {})
        if scenario_type and scenario_type in catalog:
            resolved["scenario_type_defaults"] = copy.deepcopy(catalog[scenario_type])

    def _apply_system_template_defaults(self, resolved: dict[str, Any]) -> None:
        template_id = resolved.get("system", {}).get("template")
        templates = self.system_templates.get("templates", {})
        if not template_id or template_id not in templates:
            return
        template = self._expand_template(template_id, templates)
        resolved["system_template"] = template

        carriers = copy.deepcopy(template.get("carriers", {}))
        user_carriers = resolved.get("energy_carriers", {})
        for key, value in user_carriers.items():
            carriers[key] = value
        resolved["energy_carriers"] = carriers

    def _expand_template(self, template_id: str, templates: dict[str, Any]) -> dict[str, Any]:
        template = copy.deepcopy(templates[template_id])
        parent_id = template.get("extends")
        if not parent_id:
            return template
        parent = self._expand_template(parent_id, templates)
        merged = _deep_merge(parent, template)
        default_devices = list(parent.get("default_devices", []))
        default_devices.extend(template.get("additional_devices", []))
        if default_devices:
            merged["default_devices"] = default_devices
        return merged

    def _apply_optimization_defaults(self, resolved: dict[str, Any]) -> None:
        optimization = copy.deepcopy(self.optimization_defaults.get("defaults", {}))
        user_optimization = resolved.get("optimization", {})
        mode = user_optimization.get("mode") or "test"
        mode_defaults = copy.deepcopy(self.optimization_defaults.get("modes", {}).get(mode, {}))
        optimization.update(mode_defaults)
        optimization.update(user_optimization)
        resolved["optimization"] = optimization

    def _resolve_devices(self, resolved: dict[str, Any]) -> None:
        devices = resolved.get("devices", {})
        library_devices = self.device_library.get("devices", {})
        resolved_devices: dict[str, Any] = {}
        for instance_id, config in devices.items():
            library_id = config.get("library_id")
            base = copy.deepcopy(library_devices.get(library_id, {}))
            merged = _deep_merge(base, config)
            merged["instance_id"] = instance_id
            merged["library_id"] = library_id
            overrides = merged.pop("overrides", {}) or {}
            if overrides:
                _apply_overrides(merged, overrides)
                merged["user_overrides"] = overrides
            resolved_devices[instance_id] = merged
        resolved["devices"] = resolved_devices


def _apply_overrides(device: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if key in {"invest_coeff", "invest_power_coeff", "invest_capacity_coeff"}:
            device.setdefault("economics", {})[key] = value
        elif key in {"eta_e", "eta_h", "cop", "charge_efficiency", "discharge_efficiency", "loss_rate"}:
            device.setdefault("parameters", {})[key] = value
        else:
            device[key] = value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result
