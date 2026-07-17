from __future__ import annotations

from pathlib import Path
from typing import Any

from simple_yaml import load_yaml


class ScenarioLoader:
    """Load a scenario YAML file into a Python dictionary."""

    @staticmethod
    def load(path: str | Path) -> dict[str, Any]:
        path = Path(path)
        data = load_yaml(path)
        data.setdefault("_meta", {})["source_path"] = str(path)
        return data
