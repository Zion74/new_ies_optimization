from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonSchemaValidator:
    """Validate scenario dictionaries against the user-facing JSON Schema."""

    @staticmethod
    def validate(instance: dict[str, Any], schema_path: str | Path | None = None) -> list[str]:
        schema = _load_schema(schema_path)
        try:
            import jsonschema  # type: ignore
        except Exception:
            return _fallback_validate_required(instance, schema)

        validator = jsonschema.Draft202012Validator(schema)
        errors = []
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "<root>"
            errors.append(f"schema {location}: {error.message}")
        return errors


def _load_schema(schema_path: str | Path | None) -> dict[str, Any]:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parent / "schemas" / "scenario.schema.json"
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def _fallback_validate_required(instance: dict[str, Any], schema: dict[str, Any], prefix: str = "") -> list[str]:
    errors: list[str] = []
    for key in schema.get("required", []) or []:
        if key not in instance or instance.get(key) in (None, ""):
            errors.append(f"schema {prefix + key}: required property is missing")

    properties = schema.get("properties", {}) or {}
    for key, subschema in properties.items():
        value = instance.get(key)
        if isinstance(value, dict) and isinstance(subschema, dict):
            errors.extend(_fallback_validate_required(value, subschema, prefix=f"{prefix}{key}."))
    return errors

