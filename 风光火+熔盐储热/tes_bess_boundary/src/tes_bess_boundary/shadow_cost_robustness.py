"""E0-D-21 source-free robustness envelope for omitted operating costs.

E0-D-19 provides a fuel-only TES ownership headroom interval under the same
annual PCC service.  E0-D-20 proves that four non-fuel operating-cost accounts
are not ready for formal TAC.  This module therefore does not invent project
prices.  It asks how large a signed, explicitly sensitivity-only cost effect
would have to be before the fuel-only headroom is erased.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from tes_bess_boundary.operating_cost_evidence import (
    OperatingCostAccount,
    build_e0d20_operating_cost_evidence_audit,
)


E0D19_CSV_SHA256 = (
    "4b07e91b010fa9d5aa525f196037bbf0c93bae16ac74035f6ca32292e36cf786"
)
E0D19_MANIFEST_SHA256 = (
    "c112c210aa9a86edfcb116f614c1f4a5da14f314a128e31ee329fbefd65aab63"
)
E0D19_SCHEMA = "tes_bess_boundary.e0d19_same_pcc_service.v2"
E0D21_SCHEMA = "tes_bess_boundary.e0d21_shadow_cost_robustness.v1"
_SIGN_TOLERANCE_CNY = 1e-6


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be finite")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _finite_non_negative(value: float, field_name: str) -> float:
    number = _finite(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ClosedInterval:
    """Finite closed interval used for conservative cost propagation."""

    lower: float
    upper: float

    def __post_init__(self) -> None:
        lower = _finite(self.lower, "lower")
        upper = _finite(self.upper, "upper")
        if lower > upper:
            raise ValueError("interval lower must not exceed upper")

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) / 2.0

    def add(self, other: ClosedInterval) -> ClosedInterval:
        if not isinstance(other, ClosedInterval):
            raise TypeError("other must be a ClosedInterval")
        return ClosedInterval(
            lower=self.lower + other.lower,
            upper=self.upper + other.upper,
        )

    def subtract_non_negative(self, value: float) -> ClosedInterval:
        adverse = _finite_non_negative(value, "adverse_cost_cny")
        return ClosedInterval(
            lower=self.lower - adverse,
            upper=self.upper - adverse,
        )


@dataclass(frozen=True)
class E0D21SourceRecord:
    """One hash-locked E0-D-19 window and its fuel-only headroom interval."""

    window_id: str
    hours: int
    fuel_headroom_cny: ClosedInterval
    eac_cny_per_kwh_th_year: ClosedInterval
    eac_cny_per_kw_port_year: ClosedInterval
    scientific_status: str

    def __post_init__(self) -> None:
        _non_empty(self.window_id, "window_id")
        _non_empty(self.scientific_status, "scientific_status")
        if isinstance(self.hours, bool) or not isinstance(self.hours, int):
            raise ValueError("hours must be a positive integer")
        if self.hours <= 0:
            raise ValueError("hours must be a positive integer")
        for field_name in (
            "fuel_headroom_cny",
            "eac_cny_per_kwh_th_year",
            "eac_cny_per_kw_port_year",
        ):
            interval = getattr(self, field_name)
            if not isinstance(interval, ClosedInterval):
                raise TypeError(f"{field_name} must be a ClosedInterval")
            if interval.lower < 0.0:
                raise ValueError(f"{field_name} must be non-negative")


@dataclass(frozen=True)
class E0D21Source:
    """Canonical E0-D-19 source plus the E0-D-20 readiness state."""

    records: tuple[E0D21SourceRecord, ...]
    csv_sha256: str
    manifest_sha256: str
    d20_formal_portfolio_ready: bool

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or not self.records:
            raise ValueError("records must be a non-empty immutable tuple")
        if any(not isinstance(item, E0D21SourceRecord) for item in self.records):
            raise TypeError("records must contain E0D21SourceRecord values")
        window_ids = tuple(item.window_id for item in self.records)
        if len(set(window_ids)) != len(window_ids):
            raise ValueError("source window_id values must be unique")
        for digest, field_name in (
            (self.csv_sha256, "csv_sha256"),
            (self.manifest_sha256, "manifest_sha256"),
        ):
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError(f"{field_name} must be a lowercase SHA-256")
        if not isinstance(self.d20_formal_portfolio_ready, bool):
            raise TypeError("d20_formal_portfolio_ready must be boolean")
        if self.d20_formal_portfolio_ready:
            raise ValueError(
                "E0-D-21 shadow costs are invalid after a formal portfolio is ready"
            )

    @property
    def formal_tac_ready(self) -> bool:
        return False


@dataclass(frozen=True)
class ShadowCostContribution:
    """Signed account effect on TES ownership headroom, never a formal value."""

    account: OperatingCostAccount
    headroom_effect_lower_cny: float
    headroom_effect_upper_cny: float
    source_identity: str
    note: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, OperatingCostAccount):
            raise TypeError("account must be an OperatingCostAccount")
        _non_empty(self.source_identity, "source_identity")
        _non_empty(self.note, "note")
        ClosedInterval(
            self.headroom_effect_lower_cny,
            self.headroom_effect_upper_cny,
        )

    @property
    def headroom_effect_cny(self) -> ClosedInterval:
        return ClosedInterval(
            self.headroom_effect_lower_cny,
            self.headroom_effect_upper_cny,
        )

    @property
    def allowed_use(self) -> str:
        return "sensitivity_only"


@dataclass(frozen=True)
class ShadowCostScenario:
    """Complete four-account sensitivity vector in comparator-minus-candidate sign."""

    scenario_id: str
    contributions: tuple[ShadowCostContribution, ...]

    def __post_init__(self) -> None:
        _non_empty(self.scenario_id, "scenario_id")
        if not isinstance(self.contributions, tuple) or any(
            not isinstance(item, ShadowCostContribution)
            for item in self.contributions
        ):
            raise TypeError("contributions must be an immutable canonical tuple")
        accounts = tuple(item.account for item in self.contributions)
        if len(accounts) != len(OperatingCostAccount) or set(accounts) != set(
            OperatingCostAccount
        ):
            raise ValueError("every operating-cost account must appear exactly once")

    @property
    def total_headroom_effect_cny(self) -> ClosedInterval:
        return ClosedInterval(
            lower=math.fsum(
                item.headroom_effect_lower_cny for item in self.contributions
            ),
            upper=math.fsum(
                item.headroom_effect_upper_cny for item in self.contributions
            ),
        )

    @property
    def allowed_use(self) -> str:
        return "sensitivity_only"

    @property
    def formal_tac_eligible(self) -> bool:
        return False


class RobustnessStatus(str, Enum):
    """Sign of the adjusted TES ownership headroom interval."""

    ROBUSTLY_POSITIVE = "robustly_positive"
    INDETERMINATE_INCLUDING_BREAK_EVEN = (
        "indeterminate_including_break_even"
    )
    EXACT_BREAK_EVEN = "exact_break_even"
    ROBUSTLY_NEGATIVE = "robustly_negative"


def classify_headroom(interval: ClosedInterval) -> RobustnessStatus:
    if not isinstance(interval, ClosedInterval):
        raise TypeError("interval must be a ClosedInterval")
    if interval.lower > _SIGN_TOLERANCE_CNY:
        return RobustnessStatus.ROBUSTLY_POSITIVE
    if interval.upper < -_SIGN_TOLERANCE_CNY:
        return RobustnessStatus.ROBUSTLY_NEGATIVE
    if abs(interval.lower) <= _SIGN_TOLERANCE_CNY and abs(
        interval.upper
    ) <= _SIGN_TOLERANCE_CNY:
        return RobustnessStatus.EXACT_BREAK_EVEN
    return RobustnessStatus.INDETERMINATE_INCLUDING_BREAK_EVEN


@dataclass(frozen=True)
class ShadowCostApplication:
    """One interval-propagated result with a non-negotiable claim boundary."""

    window_id: str
    scenario_id: str
    fuel_headroom_cny: ClosedInterval
    shadow_headroom_effect_cny: ClosedInterval
    adjusted_headroom_cny: ClosedInterval
    status: RobustnessStatus

    def __post_init__(self) -> None:
        _non_empty(self.window_id, "window_id")
        _non_empty(self.scenario_id, "scenario_id")
        for field_name in (
            "fuel_headroom_cny",
            "shadow_headroom_effect_cny",
            "adjusted_headroom_cny",
        ):
            if not isinstance(getattr(self, field_name), ClosedInterval):
                raise TypeError(f"{field_name} must be a ClosedInterval")
        if not isinstance(self.status, RobustnessStatus):
            raise TypeError("status must be a RobustnessStatus")

    @property
    def formal_tac(self) -> bool:
        return False

    @property
    def claim_scope(self) -> str:
        return "shadow_cost_sensitivity_only"


def load_e0d21_source(input_dir: str | Path) -> E0D21Source:
    """Load and validate the canonical E0-D-19 interval without re-solving."""

    root = Path(input_dir)
    csv_path = root / "e0d19_same_pcc_service.csv"
    manifest_path = root / "manifest.json"
    if _sha256(csv_path) != E0D19_CSV_SHA256:
        raise ValueError("E0-D-19 CSV hash does not match the D21 source lock")
    if _sha256(manifest_path) != E0D19_MANIFEST_SHA256:
        raise ValueError("E0-D-19 manifest hash does not match the D21 source lock")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != E0D19_SCHEMA:
        raise ValueError("E0-D-19 manifest schema is not compatible with D21")
    if manifest.get("output", {}).get("csv_sha256") != E0D19_CSV_SHA256:
        raise ValueError("E0-D-19 manifest lost its canonical CSV identity")
    omitted = tuple(manifest.get("case", {}).get("omitted_non_tes_cost_terms", ()))
    if set(omitted) != {account.value for account in OperatingCostAccount}:
        raise ValueError("E0-D-19 source does not expose exactly the four D20 accounts")

    records: list[E0D21SourceRecord] = []
    with csv_path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["claim_scope"] != "exploratory_threshold_only":
                raise ValueError("D21 source must remain an exploratory threshold")
            if row["formal_tes_portfolio_ready"].strip().lower() != "false":
                raise ValueError("D21 rejects a source with formal TES readiness")
            if row["non_tes_cost_scope_complete"].strip().lower() != "false":
                raise ValueError("D21 requires an explicitly incomplete non-TES scope")
            records.append(
                E0D21SourceRecord(
                    window_id=row["window_id"],
                    hours=int(row["hours"]),
                    fuel_headroom_cny=ClosedInterval(
                        float(row["tes_ownership_eac_lower_bound_cny_per_year"]),
                        float(row["tes_ownership_eac_upper_bound_cny_per_year"]),
                    ),
                    eac_cny_per_kwh_th_year=ClosedInterval(
                        float(row["eac_lower_cny_per_kwh_th_year"]),
                        float(row["eac_upper_cny_per_kwh_th_year"]),
                    ),
                    eac_cny_per_kw_port_year=ClosedInterval(
                        float(row["eac_lower_cny_per_kw_port_year"]),
                        float(row["eac_upper_cny_per_kw_port_year"]),
                    ),
                    scientific_status=row["scientific_status"],
                )
            )
    audit = build_e0d20_operating_cost_evidence_audit()
    return E0D21Source(
        records=tuple(records),
        csv_sha256=E0D19_CSV_SHA256,
        manifest_sha256=E0D19_MANIFEST_SHA256,
        d20_formal_portfolio_ready=audit.formal_portfolio_ready,
    )


def build_single_account_adverse_scenario(
    *,
    scenario_id: str,
    account: OperatingCostAccount,
    adverse_cost_cny: float,
) -> ShadowCostScenario:
    """Stress one account while holding the other three at zero."""

    if not isinstance(account, OperatingCostAccount):
        raise TypeError("account must be an OperatingCostAccount")
    adverse = _finite_non_negative(adverse_cost_cny, "adverse_cost_cny")
    return ShadowCostScenario(
        scenario_id=scenario_id,
        contributions=tuple(
            ShadowCostContribution(
                account=item,
                headroom_effect_lower_cny=(-adverse if item is account else 0.0),
                headroom_effect_upper_cny=(-adverse if item is account else 0.0),
                source_identity="author_single_account_break_even_stress",
                note=(
                    "selected account alone carries the adverse burden"
                    if item is account
                    else "held at zero for one-account threshold isolation"
                ),
            )
            for item in OperatingCostAccount
        ),
    )


def apply_shadow_cost_scenario(
    source: E0D21SourceRecord,
    scenario: ShadowCostScenario,
) -> ShadowCostApplication:
    """Add signed account effects to the fuel-only headroom interval."""

    if not isinstance(source, E0D21SourceRecord):
        raise TypeError("source must be an E0D21SourceRecord")
    if not isinstance(scenario, ShadowCostScenario):
        raise TypeError("scenario must be a ShadowCostScenario")
    effect = scenario.total_headroom_effect_cny
    adjusted = source.fuel_headroom_cny.add(effect)
    return ShadowCostApplication(
        window_id=source.window_id,
        scenario_id=scenario.scenario_id,
        fuel_headroom_cny=source.fuel_headroom_cny,
        shadow_headroom_effect_cny=effect,
        adjusted_headroom_cny=adjusted,
        status=classify_headroom(adjusted),
    )


def apply_unallocated_adverse_stress(
    source: E0D21SourceRecord,
    *,
    adverse_cost_cny: float,
    stress_id: str = "unallocated_adverse_portfolio_stress",
) -> ShadowCostApplication:
    """Apply a combined adverse cost without pretending to allocate accounts."""

    if not isinstance(source, E0D21SourceRecord):
        raise TypeError("source must be an E0D21SourceRecord")
    _non_empty(stress_id, "stress_id")
    adverse = _finite_non_negative(adverse_cost_cny, "adverse_cost_cny")
    effect = ClosedInterval(-adverse, -adverse)
    adjusted = source.fuel_headroom_cny.subtract_non_negative(adverse)
    return ShadowCostApplication(
        window_id=source.window_id,
        scenario_id=stress_id,
        fuel_headroom_cny=source.fuel_headroom_cny,
        shadow_headroom_effect_cny=effect,
        adjusted_headroom_cny=adjusted,
        status=classify_headroom(adjusted),
    )


def _threshold_rows(source: E0D21Source) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    scopes: tuple[tuple[str, str], ...] = (("combined_portfolio", ""),) + tuple(
        ("single_account_only", account.value) for account in OperatingCostAccount
    )
    for record in source.records:
        for scope, account in scopes:
            rows.append(
                {
                    "window_id": record.window_id,
                    "hours": record.hours,
                    "threshold_scope": scope,
                    "account": account,
                    "adverse_break_even_lower_cny_per_year": (
                        f"{record.fuel_headroom_cny.lower:.6f}"
                    ),
                    "adverse_break_even_upper_cny_per_year": (
                        f"{record.fuel_headroom_cny.upper:.6f}"
                    ),
                    "threshold_lower_cny_per_kwh_th_year": (
                        f"{record.eac_cny_per_kwh_th_year.lower:.6f}"
                    ),
                    "threshold_upper_cny_per_kwh_th_year": (
                        f"{record.eac_cny_per_kwh_th_year.upper:.6f}"
                    ),
                    "threshold_lower_cny_per_kw_port_year": (
                        f"{record.eac_cny_per_kw_port_year.lower:.6f}"
                    ),
                    "threshold_upper_cny_per_kw_port_year": (
                        f"{record.eac_cny_per_kw_port_year.upper:.6f}"
                    ),
                    "allowed_use": "sensitivity_only",
                    "formal_tac": False,
                    "interpretation": (
                        "combined unallocated adverse non-fuel burden"
                        if not account
                        else "selected account alone; all other omitted accounts zero"
                    ),
                }
            )
    return rows


def _canonical_stress_levels(
    interval: ClosedInterval,
) -> tuple[tuple[str, float], ...]:
    if math.isclose(
        interval.lower,
        interval.upper,
        rel_tol=0.0,
        abs_tol=_SIGN_TOLERANCE_CNY,
    ):
        return (
            ("zero_adverse", 0.0),
            ("half_exact_threshold", 0.5 * interval.lower),
            ("exact_threshold", interval.lower),
            ("one25_upper_threshold", 1.25 * interval.upper),
        )
    return (
        ("zero_adverse", 0.0),
        ("half_lower_threshold", 0.5 * interval.lower),
        ("lower_threshold", interval.lower),
        ("interval_midpoint", interval.midpoint),
        ("upper_threshold", interval.upper),
        ("one25_upper_threshold", 1.25 * interval.upper),
    )


def _stress_rows(source: E0D21Source) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in source.records:
        for stress_id, adverse in _canonical_stress_levels(
            record.fuel_headroom_cny
        ):
            result = apply_unallocated_adverse_stress(
                record,
                adverse_cost_cny=adverse,
                stress_id=stress_id,
            )
            rows.append(
                {
                    "window_id": record.window_id,
                    "hours": record.hours,
                    "stress_id": stress_id,
                    "adverse_nonfuel_cost_cny_per_year": f"{adverse:.6f}",
                    "fuel_headroom_lower_cny_per_year": (
                        f"{record.fuel_headroom_cny.lower:.6f}"
                    ),
                    "fuel_headroom_upper_cny_per_year": (
                        f"{record.fuel_headroom_cny.upper:.6f}"
                    ),
                    "adjusted_headroom_lower_cny_per_year": (
                        f"{result.adjusted_headroom_cny.lower:.6f}"
                    ),
                    "adjusted_headroom_upper_cny_per_year": (
                        f"{result.adjusted_headroom_cny.upper:.6f}"
                    ),
                    "robustness_status": result.status.value,
                    "account_allocation": "unallocated",
                    "allowed_use": "sensitivity_only",
                    "formal_tac": False,
                }
            )
    return rows


@dataclass(frozen=True)
class E0D21Export:
    thresholds_path: Path
    stress_path: Path
    manifest_path: Path
    canonical_sha256: dict[str, str]


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("canonical CSV rows must not be empty")
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=tuple(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_e0d21_shadow_cost_robustness(
    input_dir: str | Path,
    output_dir: str | Path,
) -> E0D21Export:
    """Write deterministic thresholds, stress examples, and a claim manifest."""

    source = load_e0d21_source(input_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    thresholds_path = destination / "e0d21_shadow_cost_thresholds.csv"
    stress_path = destination / "e0d21_shadow_cost_stress.csv"
    manifest_path = destination / "manifest.json"
    threshold_rows = _threshold_rows(source)
    stress_rows = _stress_rows(source)
    _write_csv(thresholds_path, threshold_rows)
    _write_csv(stress_path, stress_rows)
    output_hashes = {
        thresholds_path.name: _sha256(thresholds_path),
        stress_path.name: _sha256(stress_path),
    }
    manifest = {
        "schema": E0D21_SCHEMA,
        "source": {
            "e0d19_same_pcc_service.csv": {
                "sha256": source.csv_sha256,
            },
            "manifest.json": {
                "sha256": source.manifest_sha256,
                "schema": E0D19_SCHEMA,
            },
        },
        "canonical_files": {
            thresholds_path.name: {
                "sha256": output_hashes[thresholds_path.name],
                "rows": len(threshold_rows),
            },
            stress_path.name: {
                "sha256": output_hashes[stress_path.name],
                "rows": len(stress_rows),
            },
        },
        "interval_contract": {
            "fuel_headroom": "B=[L,U] from E0-D-19",
            "signed_account_effect": (
                "positive increases TES ownership headroom; negative decreases it"
            ),
            "adjusted_headroom": "B_shadow=[L+sum(s_lower),U+sum(s_upper)]",
            "unallocated_adverse_stress": "B_adverse=[L-A,U-A] for A>=0",
            "robustly_positive": "adjusted lower bound > 0",
            "robustly_negative": "adjusted upper bound < 0",
        },
        "scientific_boundary": {
            "allowed_use": "sensitivity_only",
            "formal_tac": False,
            "d20_formal_portfolio_ready": source.d20_formal_portfolio_ready,
            "account_values_are_estimates": False,
            "account_threshold_assumption": (
                "single-account rows hold all other omitted accounts at zero"
            ),
            "claim": (
                "minimum adverse omitted-cost budget needed to erase the "
                "fuel-only TES ownership headroom; not a project cost estimate"
            ),
        },
    }
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
    output_hashes[manifest_path.name] = _sha256(manifest_path)
    return E0D21Export(
        thresholds_path=thresholds_path,
        stress_path=stress_path,
        manifest_path=manifest_path,
        canonical_sha256=output_hashes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write the E0-D-21 shadow-cost robustness envelope."
    )
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    export = write_e0d21_shadow_cost_robustness(args.input_dir, args.output)
    for path in (
        export.thresholds_path,
        export.stress_path,
        export.manifest_path,
    ):
        print(f"{path.name} {export.canonical_sha256[path.name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
