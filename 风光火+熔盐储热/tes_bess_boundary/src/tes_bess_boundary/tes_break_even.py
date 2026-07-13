"""Price-independent TES value and break-even annual-cost accounting.

The E0-D-16 seam deliberately does not invent TES component prices.  It
compares two annual outcomes under one service contract, removes every TES
ownership-cost term from the candidate, and reports the maximum whole-system
TES equivalent annual cost (EAC) that could be paid without losing to the
comparator.  Capacity-normalized outputs are views of that one system ceiling;
they are never component-cost allocations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from tes_bess_boundary.formal_tes_costs import TESFormalCostReadinessAudit
from tes_bess_boundary.model import Architecture
from tes_bess_boundary.tes_cost_mapping import (
    TESCapacityBasis,
    TESCapacityLedger,
)


EXPECTED_ANNUAL_HOURS = 8_784.0
_ABS_TOL = 1e-8
_NORMALIZATION_BASES = (
    TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH,
    TESCapacityBasis.ELECTRIC_HEATER_INPUT_KW_EL,
    TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL,
    TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH,
)


def _non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def _non_negative(value: object, field_name: str) -> float:
    number = _finite(value, field_name)
    if number < 0.0:
        raise ValueError(f"{field_name} must be non-negative")
    return number


@dataclass(frozen=True)
class AnnualPhysicalOutcome:
    """Annual physical performance before assigning any TES ownership price."""

    weighted_hours: float
    fuel_tce: float
    curtailment_mwh: float
    renewable_available_mwh: float
    pcc_export_mwh: float
    tes_auxiliary_mwh_e: float = 0.0
    heat_shortfall_mwh_th: float = 0.0

    def __post_init__(self) -> None:
        values = {
            "weighted_hours": self.weighted_hours,
            "fuel_tce": self.fuel_tce,
            "curtailment_mwh": self.curtailment_mwh,
            "renewable_available_mwh": self.renewable_available_mwh,
            "pcc_export_mwh": self.pcc_export_mwh,
            "tes_auxiliary_mwh_e": self.tes_auxiliary_mwh_e,
            "heat_shortfall_mwh_th": self.heat_shortfall_mwh_th,
        }
        checked = {
            name: _non_negative(value, name) for name, value in values.items()
        }
        if not math.isclose(
            checked["weighted_hours"],
            EXPECTED_ANNUAL_HOURS,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("annual physical outcomes must represent 8784 hours")
        if checked["renewable_available_mwh"] <= 0.0:
            raise ValueError("renewable_available_mwh must be positive")
        if (
            checked["curtailment_mwh"]
            > checked["renewable_available_mwh"] + _ABS_TOL
        ):
            raise ValueError("curtailment cannot exceed available renewable energy")

    @property
    def curtailment_rate(self) -> float:
        return self.curtailment_mwh / self.renewable_available_mwh


@dataclass(frozen=True)
class KnownAnnualCostScope:
    """Comparable known costs, explicitly excluding TES ownership when required."""

    scope_id: str
    operating_cost_cny: float
    known_fixed_cost_cny: float
    currency: str = "CNY"
    price_base_year: int = 2024
    includes_artificial_penalties: bool = False
    includes_tes_ownership_cost: bool = False
    non_tes_scope_complete: bool = False

    def __post_init__(self) -> None:
        _non_empty(self.scope_id, "scope_id")
        _finite(self.operating_cost_cny, "operating_cost_cny")
        _non_negative(self.known_fixed_cost_cny, "known_fixed_cost_cny")
        if self.currency != "CNY" or self.price_base_year != 2024:
            raise ValueError("E0-D-16 known costs must use constant 2024 CNY")
        for field_name in (
            "includes_artificial_penalties",
            "includes_tes_ownership_cost",
            "non_tes_scope_complete",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")

    @property
    def known_total_cost_cny(self) -> float:
        return self.operating_cost_cny + self.known_fixed_cost_cny


@dataclass(frozen=True)
class ComparableAnnualOutcome:
    """One optimal architecture outcome on a fully disclosed comparison seam."""

    outcome_id: str
    scenario_id: str
    service_id: str
    horizon_id: str
    architecture: Architecture
    service_curtailment_ceiling_mwh: float
    physical: AnnualPhysicalOutcome
    known_cost: KnownAnnualCostScope
    solver_termination: str = "optimal"
    mip_gap: float | None = None
    tes_capacity_ledger: TESCapacityLedger | None = None

    def __post_init__(self) -> None:
        for field_name in ("outcome_id", "scenario_id", "service_id", "horizon_id"):
            _non_empty(getattr(self, field_name), field_name)
        if not isinstance(self.architecture, Architecture):
            raise ValueError("architecture must be selected with Architecture")
        if not isinstance(self.physical, AnnualPhysicalOutcome):
            raise ValueError("physical must be an AnnualPhysicalOutcome")
        if not isinstance(self.known_cost, KnownAnnualCostScope):
            raise ValueError("known_cost must be a KnownAnnualCostScope")
        ceiling = _non_negative(
            self.service_curtailment_ceiling_mwh,
            "service_curtailment_ceiling_mwh",
        )
        if ceiling > self.physical.renewable_available_mwh + _ABS_TOL:
            raise ValueError("service curtailment ceiling exceeds renewable availability")
        if self.physical.curtailment_mwh > ceiling + _ABS_TOL:
            raise ValueError("outcome violates its registered curtailment service")
        _non_empty(self.solver_termination, "solver_termination")
        if self.mip_gap is not None:
            _non_negative(self.mip_gap, "mip_gap")

        includes_tes = self.architecture in (Architecture.TES, Architecture.HYBRID)
        if includes_tes and not isinstance(self.tes_capacity_ledger, TESCapacityLedger):
            raise ValueError("TES and Hybrid outcomes require a canonical TES capacity ledger")
        if not includes_tes and self.tes_capacity_ledger is not None:
            raise ValueError("non-TES outcomes must not carry a TES capacity ledger")
        if includes_tes:
            assert self.tes_capacity_ledger is not None
            if (
                self.tes_capacity_ledger.quantity(
                    TESCapacityBasis.FULL_SENSIBLE_HEAT_KWH_TH
                )
                <= 0.0
            ):
                raise ValueError("TES outcome requires positive sensible-heat inventory")
            if not any(
                self.tes_capacity_ledger.quantity(basis) > 0.0
                for basis in (
                    TESCapacityBasis.ELECTRIC_OUTPUT_KW_EL,
                    TESCapacityBasis.USEFUL_HEAT_OUTPUT_KW_TH,
                )
            ):
                raise ValueError("TES outcome requires a positive discharge-service port")


@dataclass(frozen=True)
class TESPhysicalValueDelta:
    """Candidate-minus-comparator physical changes with beneficial signs disclosed."""

    fuel_saving_tce: float
    curtailment_reduction_mwh: float
    pcc_export_change_mwh: float
    tes_auxiliary_mwh_e: float

    def __post_init__(self) -> None:
        for field_name in (
            "fuel_saving_tce",
            "curtailment_reduction_mwh",
            "pcc_export_change_mwh",
            "tes_auxiliary_mwh_e",
        ):
            _finite(getattr(self, field_name), field_name)
        if self.tes_auxiliary_mwh_e < 0.0:
            raise ValueError("tes_auxiliary_mwh_e must be non-negative")


@dataclass(frozen=True)
class TESBreakEvenNormalization:
    """One denominator view of the whole-system EAC ceiling, not a cost allocation."""

    basis: TESCapacityBasis
    quantity: float
    system_eac_ceiling_per_unit_year: float

    def __post_init__(self) -> None:
        if self.basis not in _NORMALIZATION_BASES:
            raise ValueError("basis is not registered for break-even normalization")
        quantity = _finite(self.quantity, "quantity")
        if quantity <= 0.0:
            raise ValueError("break-even normalization quantity must be positive")
        _finite(
            self.system_eac_ceiling_per_unit_year,
            "system_eac_ceiling_per_unit_year",
        )

    @property
    def capacity_unit(self) -> str:
        return self.basis.capacity_unit


class TESBreakEvenClaimScope(str, Enum):
    """Disclosure level allowed by non-TES cost completeness and TES evidence."""

    EXPLORATORY_THRESHOLD_ONLY = "exploratory_threshold_only"
    AUDITABLE_NON_TES_COST_CEILING = "auditable_non_tes_cost_ceiling"


@dataclass(frozen=True)
class TESBreakEvenResult:
    """Audited system EAC ceiling and price-independent physical value deltas."""

    comparator_id: str
    candidate_id: str
    physical_delta: TESPhysicalValueDelta
    operating_cost_saving_cny_per_year: float
    known_fixed_cost_advantage_cny_per_year: float
    maximum_tes_ownership_eac_cny_per_year: float
    normalizations: tuple[TESBreakEvenNormalization, ...]
    claim_scope: TESBreakEvenClaimScope
    formal_tes_portfolio_ready: bool
    non_tes_cost_scope_complete: bool

    def __post_init__(self) -> None:
        _non_empty(self.comparator_id, "comparator_id")
        _non_empty(self.candidate_id, "candidate_id")
        if not isinstance(self.physical_delta, TESPhysicalValueDelta):
            raise ValueError("physical_delta must be a TESPhysicalValueDelta")
        operating = _finite(
            self.operating_cost_saving_cny_per_year,
            "operating_cost_saving_cny_per_year",
        )
        fixed = _finite(
            self.known_fixed_cost_advantage_cny_per_year,
            "known_fixed_cost_advantage_cny_per_year",
        )
        maximum = _finite(
            self.maximum_tes_ownership_eac_cny_per_year,
            "maximum_tes_ownership_eac_cny_per_year",
        )
        if not math.isclose(maximum, operating + fixed, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("TES EAC ceiling must equal operating plus fixed advantage")
        if not isinstance(self.normalizations, tuple) or any(
            not isinstance(item, TESBreakEvenNormalization)
            for item in self.normalizations
        ):
            raise ValueError("normalizations must be an immutable canonical tuple")
        bases = tuple(item.basis for item in self.normalizations)
        if len(set(bases)) != len(bases):
            raise ValueError("break-even normalization bases must be unique")
        for item in self.normalizations:
            reconstructed = item.system_eac_ceiling_per_unit_year * item.quantity
            if not math.isclose(reconstructed, maximum, rel_tol=1e-12, abs_tol=1e-5):
                raise ValueError("every normalization must reconstruct one system ceiling")
        if not isinstance(self.claim_scope, TESBreakEvenClaimScope):
            raise ValueError("claim_scope must be a TESBreakEvenClaimScope")
        if not isinstance(self.formal_tes_portfolio_ready, bool):
            raise ValueError("formal_tes_portfolio_ready must be boolean")
        if not isinstance(self.non_tes_cost_scope_complete, bool):
            raise ValueError("non_tes_cost_scope_complete must be boolean")

    @property
    def viable_at_nonnegative_tes_ownership_cost(self) -> bool:
        return self.maximum_tes_ownership_eac_cny_per_year >= -_ABS_TOL

    def headroom_at_tes_eac(self, annual_tes_eac_cny: float) -> float:
        annual_cost = _non_negative(annual_tes_eac_cny, "annual_tes_eac_cny")
        return self.maximum_tes_ownership_eac_cny_per_year - annual_cost

    def normalization(
        self,
        basis: TESCapacityBasis,
    ) -> TESBreakEvenNormalization:
        if not isinstance(basis, TESCapacityBasis):
            raise ValueError("basis must be selected with TESCapacityBasis")
        try:
            return next(item for item in self.normalizations if item.basis is basis)
        except StopIteration as error:
            raise ValueError("requested break-even normalization is unavailable") from error


def compare_tes_break_even(
    comparator: ComparableAnnualOutcome,
    candidate: ComparableAnnualOutcome,
    *,
    tes_readiness: TESFormalCostReadinessAudit,
) -> TESBreakEvenResult:
    """Compare one non-TES architecture with one TES-containing architecture."""

    if not isinstance(comparator, ComparableAnnualOutcome) or not isinstance(
        candidate,
        ComparableAnnualOutcome,
    ):
        raise ValueError("comparator and candidate must be comparable annual outcomes")
    if not isinstance(tes_readiness, TESFormalCostReadinessAudit):
        raise ValueError("tes_readiness must be a TESFormalCostReadinessAudit")
    if comparator.architecture not in (Architecture.NO_STORAGE, Architecture.BESS):
        raise ValueError("comparator must not contain TES")
    if candidate.architecture not in (Architecture.TES, Architecture.HYBRID):
        raise ValueError("candidate must contain TES")

    for field_name in ("scenario_id", "service_id", "horizon_id"):
        if getattr(comparator, field_name) != getattr(candidate, field_name):
            raise ValueError(f"comparison requires the same {field_name}")
    if not math.isclose(
        comparator.service_curtailment_ceiling_mwh,
        candidate.service_curtailment_ceiling_mwh,
        rel_tol=0.0,
        abs_tol=_ABS_TOL,
    ):
        raise ValueError("comparison requires one curtailment service ceiling")
    if not math.isclose(
        comparator.physical.renewable_available_mwh,
        candidate.physical.renewable_available_mwh,
        rel_tol=0.0,
        abs_tol=_ABS_TOL,
    ):
        raise ValueError("comparison requires identical renewable availability")
    if comparator.known_cost.scope_id != candidate.known_cost.scope_id:
        raise ValueError("comparison requires one declared known-cost scope")
    if (
        comparator.known_cost.currency != candidate.known_cost.currency
        or comparator.known_cost.price_base_year
        != candidate.known_cost.price_base_year
    ):
        raise ValueError("comparison requires one currency and price base year")
    if (
        comparator.known_cost.non_tes_scope_complete
        != candidate.known_cost.non_tes_scope_complete
    ):
        raise ValueError("comparison requires the same non-TES cost completeness")
    if any(
        outcome.known_cost.includes_artificial_penalties
        for outcome in (comparator, candidate)
    ):
        raise ValueError("artificial curtailment penalties cannot create TES value")
    if any(
        outcome.known_cost.includes_tes_ownership_cost
        for outcome in (comparator, candidate)
    ):
        raise ValueError("break-even outcomes must exclude all TES ownership costs")
    if any(
        outcome.solver_termination.strip().lower() != "optimal"
        for outcome in (comparator, candidate)
    ):
        raise ValueError("break-even comparison requires optimal outcomes")
    if any(
        outcome.physical.heat_shortfall_mwh_th > _ABS_TOL
        for outcome in (comparator, candidate)
    ):
        raise ValueError("break-even comparison requires zero heat shortfall")

    operating_saving = (
        comparator.known_cost.operating_cost_cny
        - candidate.known_cost.operating_cost_cny
    )
    fixed_advantage = (
        comparator.known_cost.known_fixed_cost_cny
        - candidate.known_cost.known_fixed_cost_cny
    )
    maximum_eac = operating_saving + fixed_advantage
    assert candidate.tes_capacity_ledger is not None
    normalizations = tuple(
        TESBreakEvenNormalization(
            basis=basis,
            quantity=candidate.tes_capacity_ledger.quantity(basis),
            system_eac_ceiling_per_unit_year=(
                maximum_eac / candidate.tes_capacity_ledger.quantity(basis)
            ),
        )
        for basis in _NORMALIZATION_BASES
        if candidate.tes_capacity_ledger.quantity(basis) > 0.0
    )
    non_tes_complete = comparator.known_cost.non_tes_scope_complete
    formal_ready = tes_readiness.formal_portfolio_ready
    claim_scope = (
        TESBreakEvenClaimScope.AUDITABLE_NON_TES_COST_CEILING
        if non_tes_complete and formal_ready
        else TESBreakEvenClaimScope.EXPLORATORY_THRESHOLD_ONLY
    )
    return TESBreakEvenResult(
        comparator_id=comparator.outcome_id,
        candidate_id=candidate.outcome_id,
        physical_delta=TESPhysicalValueDelta(
            fuel_saving_tce=(
                comparator.physical.fuel_tce - candidate.physical.fuel_tce
            ),
            curtailment_reduction_mwh=(
                comparator.physical.curtailment_mwh
                - candidate.physical.curtailment_mwh
            ),
            pcc_export_change_mwh=(
                candidate.physical.pcc_export_mwh
                - comparator.physical.pcc_export_mwh
            ),
            tes_auxiliary_mwh_e=candidate.physical.tes_auxiliary_mwh_e,
        ),
        operating_cost_saving_cny_per_year=operating_saving,
        known_fixed_cost_advantage_cny_per_year=fixed_advantage,
        maximum_tes_ownership_eac_cny_per_year=maximum_eac,
        normalizations=normalizations,
        claim_scope=claim_scope,
        formal_tes_portfolio_ready=formal_ready,
        non_tes_cost_scope_complete=non_tes_complete,
    )
