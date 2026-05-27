from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from generic_backend_planner import GenericBackendPlanner
from json_schema_validator import JsonSchemaValidator


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "runnable"
    backend: str = ""
    unsupported_devices: list[str] = field(default_factory=list)
    future_supported_devices: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def runnable(self) -> bool:
        return self.ok and self.status == "runnable"


class SchemaValidator:
    """Lightweight user-facing validation for resolved scenarios."""

    @staticmethod
    def validate(resolved: dict[str, Any], project_root: str | Path | None = None) -> ValidationResult:
        project_root = Path(project_root) if project_root else Path.cwd()
        result = ValidationResult()

        for error in JsonSchemaValidator.validate(resolved):
            result.errors.append(error)

        scenario = resolved.get("scenario", {})
        if not scenario.get("id"):
            result.errors.append("scenario.id is required")
        if not scenario.get("name"):
            result.errors.append("scenario.name is required")

        template_id = resolved.get("system", {}).get("template")
        if not template_id:
            result.errors.append("system.template is required")
        elif not resolved.get("system_template"):
            result.errors.append(f"system.template '{template_id}' is not defined in system_templates.yaml")

        data = resolved.get("data", {})
        load_file = data.get("load_file")
        if not load_file:
            result.errors.append("data.load_file is required")
        else:
            path = _resolve_input_path(load_file, resolved, project_root)
            if not path.exists():
                result.warnings.append(f"data.load_file does not exist yet: {path}")

        typical = data.get("typical_day_file") or resolved.get("typical_day", {}).get("file")
        if not typical:
            result.errors.append("typical day file is required for current CCHP adapter")
        else:
            path = _resolve_input_path(typical, resolved, project_root)
            if not path.exists():
                result.warnings.append(f"typical_day_file does not exist yet: {path}")

        library_devices = resolved.get("device_library", {}).get("devices", {})
        backend = resolved.get("system_template", {}).get("supported_backend")
        result.backend = backend or ""
        generic_plan = GenericBackendPlanner.plan(resolved) if backend == "future_generic" else None
        missing_generic_mappings = set(generic_plan.get("missing_mappings", []) if generic_plan else [])
        for instance_id, device in resolved.get("devices", {}).items():
            library_id = device.get("library_id")
            if library_id not in library_devices:
                result.errors.append(f"device {instance_id} references unknown library_id: {library_id}")
            if device.get("enabled") is True:
                impl = device.get("implementation", {})
                if backend == "current_cchp" and impl.get("backend") != "current_cchp":
                    result.unsupported_devices.append(instance_id)
                    result.errors.append(
                        f"device {instance_id} is enabled but backend {backend} does not support {library_id}"
                    )
                elif backend == "future_generic":
                    if instance_id in missing_generic_mappings:
                        result.unsupported_devices.append(instance_id)
                        result.errors.append(
                            f"device {instance_id} has no generic component mapping for {device.get('abstract_type')}"
                        )
                    else:
                        result.future_supported_devices.append(instance_id)
                has_power_bound = _has_power_capacity_bound(device)
                has_energy_bound = _has_energy_capacity_bound(device)
                if not has_power_bound and not has_energy_bound:
                    result.warnings.append(f"enabled device {instance_id} has no capacity/power upper bound")
                elif not has_power_bound and has_energy_bound:
                    result.warnings.append(
                        f"enabled storage device {instance_id} has energy capacity upper bound but no power upper bound"
                    )

        prices = resolved.get("prices", {})
        if not prices.get("electricity"):
            result.errors.append("prices.electricity is required")
        if any(d.get("enabled") for d in resolved.get("devices", {}).values() if "natural_gas" in d.get("input_carriers", [])):
            if not prices.get("gas"):
                result.errors.append("prices.gas is required when natural_gas devices are enabled")

        if result.errors:
            result.status = "blocked"
        elif backend == "future_generic":
            result.status = "future_supported"
            result.warnings.append("scenario maps to the future_generic backend but cannot be optimized by the current solver yet")
        else:
            result.status = "runnable"

        return result


def _resolve_input_path(value: str | Path, resolved: dict[str, Any], project_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    source_path = resolved.get("_meta", {}).get("source_path")
    if source_path:
        candidate = Path(source_path).parent / path
        if candidate.exists():
            return candidate
    return project_root / path


def _has_power_capacity_bound(device: dict[str, Any]) -> bool:
    return any(device.get(key) not in (None, "", 0) for key in ["capacity_ub_kw", "power_ub_kw", "fixed_capacity_kw"])


def _has_energy_capacity_bound(device: dict[str, Any]) -> bool:
    return any(device.get(key) not in (None, "", 0) for key in ["capacity_ub_kwh", "energy_capacity_ub_kwh", "energy_ub_kwh", "fixed_capacity_kwh"])
