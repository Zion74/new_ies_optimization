from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable


_CLOUD_ENV_MARKERS = (
    "OPENBAYES_TASK_ID",
    "OPENBAYES_JOB_ID",
    "OPENBAYES_PROJECT_ID",
    "JUPYTERHUB_SERVICE_PREFIX",
    "JUPYTERHUB_API_TOKEN",
    "KAGGLE_KERNEL_RUN_TYPE",
    "COLAB_GPU",
)

_SOLVER_DISPLAY_NAMES = {
    "gurobi_direct": "Gurobi",
    "highs": "HiGHS",
    "glpk": "GLPK",
}


def _path_text(path: Path) -> str:
    return str(path).replace("\\", "/").lower()


def is_cloud_environment() -> bool:
    forced = os.environ.get("IES_RUNTIME_ENV", "").strip().lower()
    if forced in {"cloud", "server", "remote"}:
        return True
    if forced in {"local", "desktop"}:
        return False

    if any(os.environ.get(key) for key in _CLOUD_ENV_MARKERS):
        return True

    home_text = _path_text(Path.home())
    cwd_text = _path_text(Path.cwd())
    return home_text.startswith("/openbayes") or cwd_text.startswith("/openbayes")


def _candidate_gurobi_license_paths() -> list[Path]:
    repo_root = Path(__file__).resolve().parent
    home = Path.home()
    candidates = [
        home / "gurobi.lic",
        repo_root / "gurobi.lic",
    ]
    if os.name == "nt":
        userprofile = Path(os.environ.get("USERPROFILE", str(home)))
        candidates.extend(
            [
                userprofile / "gurobi.lic",
                Path("C:/gurobi/gurobi.lic"),
            ]
        )

    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        text = str(path)
        if text not in seen:
            seen.add(text)
            unique.append(path)
    return unique


def configure_gurobi_license() -> str | None:
    custom_path = os.environ.get("IES_GUROBI_LICENSE_FILE", "").strip()
    if custom_path:
        os.environ["GRB_LICENSE_FILE"] = custom_path
        return custom_path

    current_path = os.environ.get("GRB_LICENSE_FILE", "").strip()
    if current_path:
        return current_path

    for candidate in _candidate_gurobi_license_paths():
        if candidate.exists():
            os.environ["GRB_LICENSE_FILE"] = str(candidate)
            return str(candidate)

    return None


def has_gurobi_credentials() -> bool:
    if configure_gurobi_license():
        return True

    for key in ("GRB_WLSACCESSID", "GRB_WLSSECRET", "GRB_LICENSEID"):
        if os.environ.get(key, "").strip():
            return True
    return False


def preferred_solver_order() -> list[str]:
    if is_cloud_environment():
        return ["highs", "glpk"]
    if has_gurobi_credentials():
        return ["gurobi_direct", "highs", "glpk"]
    return ["highs", "glpk"]


def _pyomo_solver_available(name: str) -> bool:
    try:
        from pyomo.opt import SolverFactory

        return bool(SolverFactory(name).available(False))
    except Exception:
        return False


def is_solver_available(name: str) -> bool:
    if name == "gurobi_direct":
        return has_gurobi_credentials() and _pyomo_solver_available(name)
    if name == "highs":
        try:
            import highspy  # noqa: F401
        except Exception:
            return False
        return True
    if name == "glpk":
        return shutil.which("glpsol") is not None or _pyomo_solver_available(name)
    return _pyomo_solver_available(name)


def available_solver_names(names: Iterable[str] | None = None) -> list[str]:
    names = list(names or _SOLVER_DISPLAY_NAMES.keys())
    return [name for name in names if is_solver_available(name)]


def solver_display_name(name: str) -> str:
    return _SOLVER_DISPLAY_NAMES.get(name, name)


def iter_solver_display_names(names: Iterable[str]) -> str:
    return " -> ".join(solver_display_name(name) for name in names)
