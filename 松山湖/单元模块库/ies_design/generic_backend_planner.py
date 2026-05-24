from __future__ import annotations

from typing import Any


class GenericBackendPlanner:
    """Build a lightweight component plan for future generic backends."""

    @staticmethod
    def plan(resolved: dict[str, Any]) -> dict[str, Any]:
        carriers = resolved.get("energy_carriers", {})
        buses = set()
        for group in ("demands", "inputs", "resources"):
            buses.update(carriers.get(group, []) or [])

        mappings = resolved.get("component_mapping", {}).get("component_mappings", {})
        components: list[dict[str, Any]] = []
        missing_mappings: list[str] = []

        for instance_id, device in resolved.get("devices", {}).items():
            if not device.get("enabled", False):
                continue

            input_carriers = list(device.get("input_carriers", []) or [])
            output_carriers = list(device.get("output_carriers", []) or [])
            buses.update(input_carriers)
            buses.update(output_carriers)

            abstract_type = device.get("abstract_type")
            mapping = mappings.get(abstract_type)
            if not mapping:
                missing_mappings.append(instance_id)

            components.append({
                "instance_id": instance_id,
                "library_id": device.get("library_id"),
                "name": device.get("name", instance_id),
                "abstract_type": abstract_type,
                "component_type": mapping.get("component") if mapping else None,
                "input_carriers": input_carriers,
                "output_carriers": output_carriers,
                "mapping_found": mapping is not None,
            })

        return {
            "backend": "future_generic",
            "buses": sorted(bus for bus in buses if bus),
            "components": components,
            "missing_mappings": missing_mappings,
            "runnable": False,
        }

