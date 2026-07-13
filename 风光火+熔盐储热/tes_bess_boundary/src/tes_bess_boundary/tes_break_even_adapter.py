"""Adapt solved E0-C annual cases to the E0-D-16 break-even contract.

The adapter is deliberately conservative.  It accepts only penalty-free,
HiGHS-optimal annual cases with an explicit curtailment-service constraint.  It
removes every TES lifecycle asset from the fixed-capacity result while keeping
verified BESS ownership and operating terms.  The current E0-C objective still
omits system VOM, carbon, and electricity settlement, so every adapted result
is locked to exploratory scope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from tes_bess_boundary.economics import LifecycleAssetClass
from tes_bess_boundary.formal_tes_costs import TESFormalCostReadinessAudit
from tes_bess_boundary.model import Architecture, E0CCase, E0CResult
from tes_bess_boundary.tes_break_even import (
    AnnualPhysicalOutcome,
    ComparableAnnualOutcome,
    KnownAnnualCostScope,
    TESBreakEvenResult,
    compare_tes_break_even,
)
from tes_bess_boundary.tes_cost_mapping import derive_tes_capacity_ledger


_ABS_TOL = 1e-7
_TES_OWNERSHIP_CLASSES = frozenset(
    {
        LifecycleAssetClass.TES_COMPONENT,
        LifecycleAssetClass.SALT_TO_STEAM_GENERATOR,
        LifecycleAssetClass.EXISTING_TURBINE_REUSE,
        LifecycleAssetClass.NEW_POWER_BLOCK,
    }
)


def _non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _finite_non_negative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be finite and non-negative")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return number


@dataclass(frozen=True)
class E0CBreakEvenAdapterSpec:
    """Identity and disclosed omissions for one E0-D-17 result seam."""

    scenario_id: str
    horizon_id: str
    known_cost_scope_id: str
    omitted_non_tes_cost_terms: tuple[str, ...]
    residual_tolerance: float = _ABS_TOL

    def __post_init__(self) -> None:
        for field_name in (
            "scenario_id",
            "horizon_id",
            "known_cost_scope_id",
        ):
            _non_empty(getattr(self, field_name), field_name)
        if not isinstance(self.omitted_non_tes_cost_terms, tuple) or not (
            self.omitted_non_tes_cost_terms
        ):
            raise ValueError(
                "E0-D-17 requires an explicit non-empty tuple of omitted cost terms"
            )
        if any(
            not isinstance(term, str) or not term.strip()
            for term in self.omitted_non_tes_cost_terms
        ):
            raise ValueError("omitted cost terms must be non-empty strings")
        if len(set(self.omitted_non_tes_cost_terms)) != len(
            self.omitted_non_tes_cost_terms
        ):
            raise ValueError("omitted cost terms must be unique")
        tolerance = _finite_non_negative(
            self.residual_tolerance,
            "residual_tolerance",
        )
        if tolerance == 0.0:
            raise ValueError("residual_tolerance must be positive")


@dataclass(frozen=True)
class E0CBreakEvenAdaptation:
    """Comparable outcome plus the exact ownership-cost removal audit."""

    outcome: ComparableAnnualOutcome
    source_total_cost_cny_per_year: float
    retained_operating_cost_cny_per_year: float
    retained_non_tes_fixed_cost_cny_per_year: float
    excluded_tes_ownership_cost_cny_per_year: float
    omitted_non_tes_cost_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ComparableAnnualOutcome):
            raise ValueError("outcome must be a ComparableAnnualOutcome")
        values = tuple(
            _finite_non_negative(getattr(self, field_name), field_name)
            for field_name in (
                "source_total_cost_cny_per_year",
                "retained_operating_cost_cny_per_year",
                "retained_non_tes_fixed_cost_cny_per_year",
                "excluded_tes_ownership_cost_cny_per_year",
            )
        )
        if not math.isclose(
            values[0],
            values[1] + values[2] + values[3],
            rel_tol=0.0,
            abs_tol=1e-5,
        ):
            raise ValueError(
                "source annual cost must equal retained costs plus excluded TES ownership"
            )
        if self.omitted_non_tes_cost_terms != tuple(
            self.omitted_non_tes_cost_terms
        ) or not self.omitted_non_tes_cost_terms:
            raise ValueError("omitted cost terms must remain an immutable tuple")


@dataclass(frozen=True)
class E0CBreakEvenComparison:
    """Two audited adaptations and their E0-D-16 comparison result."""

    comparator: E0CBreakEvenAdaptation
    candidate: E0CBreakEvenAdaptation
    break_even: TESBreakEvenResult

    def __post_init__(self) -> None:
        if not isinstance(self.comparator, E0CBreakEvenAdaptation) or not isinstance(
            self.candidate,
            E0CBreakEvenAdaptation,
        ):
            raise ValueError("comparison entries must be E0-C adaptations")
        if not isinstance(self.break_even, TESBreakEvenResult):
            raise ValueError("break_even must be a TESBreakEvenResult")


def adapt_e0c_annual_outcome(
    case: E0CCase,
    result: E0CResult,
    *,
    spec: E0CBreakEvenAdapterSpec,
) -> E0CBreakEvenAdaptation:
    """Convert one solved annual E0-C case without overstating cost completeness."""

    if not isinstance(case, E0CCase) or not isinstance(result, E0CResult):
        raise ValueError("case and result must use the E0-C public contracts")
    if not isinstance(spec, E0CBreakEvenAdapterSpec):
        raise ValueError("spec must be an E0CBreakEvenAdapterSpec")
    if case.architecture is not result.architecture:
        raise ValueError("case and result architectures must match")
    if case.economics is None or result.annual_economics is None:
        raise ValueError("break-even adaptation requires annual economics")
    if case.curtailment_service is None:
        raise ValueError("break-even adaptation requires an explicit curtailment service")
    if case.objective.curtailment_penalty_cny_per_mwh != 0.0:
        raise ValueError("break-even adaptation rejects artificial curtailment penalties")
    if result.solver_name != "appsi_highs" or result.termination.strip().lower() != (
        "optimal"
    ):
        raise ValueError("break-even adaptation requires an optimal appsi_highs result")

    tolerance = spec.residual_tolerance
    if result.max_pcc_balance_residual_mw > tolerance:
        raise ValueError("PCC balance residual exceeds the adapter tolerance")
    if result.max_heat_balance_residual_mw > tolerance:
        raise ValueError("heat balance residual exceeds the adapter tolerance")
    if result.bess_cyclic_residual_mwh is not None and (
        result.bess_cyclic_residual_mwh > tolerance
    ):
        raise ValueError("BESS cyclic residual exceeds the adapter tolerance")
    if result.tes_cyclic_residual_t is not None and (
        result.tes_cyclic_residual_t > tolerance
    ):
        raise ValueError("TES cyclic residual exceeds the adapter tolerance")

    annual = result.annual_economics
    if (
        annual.curtailment_service_id != case.curtailment_service.service_id
        or annual.curtailment_ceiling_mwh is None
        or not math.isclose(
            annual.curtailment_ceiling_mwh,
            case.curtailment_service.maximum_curtailment_mwh,
            rel_tol=0.0,
            abs_tol=tolerance,
        )
    ):
        raise ValueError("result does not retain the case curtailment-service contract")
    if annual.weighted_curtailment_mwh > (
        case.curtailment_service.maximum_curtailment_mwh + tolerance
    ):
        raise ValueError("annual result violates its curtailment-service ceiling")
    if annual.weighted_renewable_available_mwh <= 0.0:
        raise ValueError("break-even adaptation requires positive renewable availability")

    tes_ownership_cost = 0.0
    non_tes_non_cell_fixed_cost = annual.non_cell_fixed_cost_cny
    if case.economics.non_cell_cost is not None:
        portfolio_cost = case.economics.non_cell_cost.annual_cost
        tes_ownership_cost = math.fsum(
            asset.total_annual_cost
            for asset in portfolio_cost.assets
            if asset.asset_class in _TES_OWNERSHIP_CLASSES
        )
        non_tes_non_cell_fixed_cost = (
            portfolio_cost.total_annual_cost - tes_ownership_cost
        )
    if non_tes_non_cell_fixed_cost < 0.0 and abs(
        non_tes_non_cell_fixed_cost
    ) <= tolerance:
        non_tes_non_cell_fixed_cost = 0.0
    _finite_non_negative(
        non_tes_non_cell_fixed_cost,
        "retained non-TES non-cell fixed cost",
    )

    retained_operating = (
        annual.operating_cost_cny
        + annual.bess_cycle_cost_cny
        + annual.bess_variable_om_cost_cny
    )
    retained_fixed = (
        non_tes_non_cell_fixed_cost + annual.bess_calendar_cost_cny
    )
    source_total = annual.total_cost_cny
    if not math.isclose(
        source_total,
        retained_operating + retained_fixed + tes_ownership_cost,
        rel_tol=0.0,
        abs_tol=1e-5,
    ):
        raise ValueError("annual E0-C cost audit cannot be decomposed exactly")

    includes_tes = case.architecture in (Architecture.TES, Architecture.HYBRID)
    tes_ledger = None
    tes_auxiliary_mwh_e = 0.0
    if includes_tes:
        if case.tes is None or result.tes_operation is None:
            raise ValueError("TES outcomes require fixed TES and annual operation audits")
        if not math.isclose(
            result.tes_operation.weighted_hours,
            annual.weighted_hours,
            rel_tol=0.0,
            abs_tol=tolerance,
        ):
            raise ValueError("TES operation and annual economics use different weights")
        tes_ledger = derive_tes_capacity_ledger(case.tes)
        tes_auxiliary_mwh_e = result.tes_operation.total_auxiliary_mwh_e
    elif result.tes_operation is not None:
        raise ValueError("non-TES outcomes must not contain a TES operation audit")

    outcome = ComparableAnnualOutcome(
        outcome_id=(
            f"{spec.scenario_id}:{spec.horizon_id}:{case.architecture.value}"
        ),
        scenario_id=spec.scenario_id,
        service_id=case.curtailment_service.service_id,
        horizon_id=spec.horizon_id,
        architecture=case.architecture,
        service_curtailment_ceiling_mwh=(
            case.curtailment_service.maximum_curtailment_mwh
        ),
        physical=AnnualPhysicalOutcome(
            weighted_hours=annual.weighted_hours,
            fuel_tce=annual.weighted_fuel_tce,
            curtailment_mwh=annual.weighted_curtailment_mwh,
            renewable_available_mwh=annual.weighted_renewable_available_mwh,
            pcc_export_mwh=annual.weighted_pcc_export_mwh,
            tes_auxiliary_mwh_e=tes_auxiliary_mwh_e,
            heat_shortfall_mwh_th=0.0,
        ),
        known_cost=KnownAnnualCostScope(
            scope_id=spec.known_cost_scope_id,
            operating_cost_cny=retained_operating,
            known_fixed_cost_cny=retained_fixed,
            includes_artificial_penalties=False,
            includes_tes_ownership_cost=False,
            non_tes_scope_complete=False,
        ),
        solver_termination=result.termination,
        mip_gap=result.mip_gap,
        tes_capacity_ledger=tes_ledger,
    )
    return E0CBreakEvenAdaptation(
        outcome=outcome,
        source_total_cost_cny_per_year=source_total,
        retained_operating_cost_cny_per_year=retained_operating,
        retained_non_tes_fixed_cost_cny_per_year=retained_fixed,
        excluded_tes_ownership_cost_cny_per_year=tes_ownership_cost,
        omitted_non_tes_cost_terms=spec.omitted_non_tes_cost_terms,
    )


def compare_e0c_annual_break_even(
    comparator_case: E0CCase,
    comparator_result: E0CResult,
    candidate_case: E0CCase,
    candidate_result: E0CResult,
    *,
    spec: E0CBreakEvenAdapterSpec,
    tes_readiness: TESFormalCostReadinessAudit,
) -> E0CBreakEvenComparison:
    """Adapt and compare a matched pair of actual E0-C annual solves."""

    comparator = adapt_e0c_annual_outcome(
        comparator_case,
        comparator_result,
        spec=spec,
    )
    candidate = adapt_e0c_annual_outcome(
        candidate_case,
        candidate_result,
        spec=spec,
    )
    break_even = compare_tes_break_even(
        comparator.outcome,
        candidate.outcome,
        tes_readiness=tes_readiness,
    )
    return E0CBreakEvenComparison(
        comparator=comparator,
        candidate=candidate,
        break_even=break_even,
    )
