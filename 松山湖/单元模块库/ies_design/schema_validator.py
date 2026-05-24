from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class SchemaValidator:
    """Lightweight user-facing validation for resolved scenarios."""

    @staticmethod
    def validate(resolved: dict[str, Any], project_root: str | Path | None = None) -> ValidationResult:
        project_root = Path(project_root) if project_root else Path.cwd()
        result = ValidationResult()

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
            path = Path(load_file)
            if not path.is_absolute():
                path = project_root / path
            if not path.exists():
                result.warnings.append(f"data.load_file does not exist yet: {path}")

        typical = data.get("typical_day_file") or resolved.get("typical_day", {}).get("file")
        if not typical:
            result.errors.append("typical day file is required for current CCHP adapter")
        else:
            path = Path(typical)
            if not path.is_absolute():
                path = project_root / path
            if not path.exists():
                result.warnings.append(f"typical_day_file does not exist yet: {path}")

        library_devices = resolved.get("device_library", {}).get("devices", {})
        backend = resolved.get("system_template", {}).get("supported_backend")
        for instance_id, device in resolved.get("devices", {}).items():
            library_id = device.get("library_id")
            if library_id not in library_devices:
                result.errors.append(f"device {instance_id} references unknown library_id: {library_id}")
            if device.get("enabled") is True:
                impl = device.get("implementation", {})
                if backend == "current_cchp" and impl.get("backend") != "current_cchp":
                    result.errors.append(
                        f"device {instance_id} is enabled but backend {backend} does not support {library_id}"
                    )
                if not any(device.get(k) for k in ["capacity_ub_kw", "power_ub_kw", "fixed_capacity_kw"]):
                    result.warnings.append(f"enabled device {instance_id} has no capacity/power upper bound")

        prices = resolved.get("prices", {})
        if not prices.get("electricity"):
            result.errors.append("prices.electricity is required")
        if any(d.get("enabled") for d in resolved.get("devices", {}).values() if "natural_gas" in d.get("input_carriers", [])):
            if not prices.get("gas"):
                result.errors.append("prices.gas is required when natural_gas devices are enabled")

        return result
