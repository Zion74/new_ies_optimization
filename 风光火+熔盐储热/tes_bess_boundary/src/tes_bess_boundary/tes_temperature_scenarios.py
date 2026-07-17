"""Auditable medium-temperature scenarios for three-state molten-salt TES."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum

from tes_bess_boundary.model import TESFixedSpec
from tes_bess_boundary.tes_heat_delivery import (
    HeatNetworkPinchSpec,
    MoltenSaltMaterialEnvelope,
    TESHeatDeliveryPinchAudit,
)


class MTTemperatureBasis(str, Enum):
    """Evidence identity of one medium-temperature value."""

    SITE_PRIMARY = "site_primary"
    CORE_PAPER_DIRECT = "core_paper_direct"
    AUTHOR_NORMALIZED_ENTHALPY = "author_normalized_enthalpy"


@dataclass(frozen=True)
class MTScenarioPoint:
    """One MT point and its raw sensible-enthalpy partition."""

    scenario_id: str
    temperature_lt_c: float
    temperature_mt_c: float
    temperature_ht_c: float
    low_grade_enthalpy_fraction: float
    temperature_basis: MTTemperatureBasis
    source_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id must be non-empty")
        temperatures = (
            self.temperature_lt_c,
            self.temperature_mt_c,
            self.temperature_ht_c,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in temperatures
        ):
            raise ValueError("MT scenario temperatures must be finite")
        if not self.temperature_ht_c > self.temperature_mt_c > self.temperature_lt_c:
            raise ValueError("MT scenario must satisfy HT > MT > LT")
        fraction = self.low_grade_enthalpy_fraction
        if (
            isinstance(fraction, bool)
            or not isinstance(fraction, (int, float))
            or not math.isfinite(fraction)
            or not 0.0 < fraction < 1.0
        ):
            raise ValueError(
                "low-grade enthalpy fraction must lie strictly between zero and one"
            )
        if not isinstance(self.temperature_basis, MTTemperatureBasis):
            raise ValueError("temperature_basis must use MTTemperatureBasis")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must disclose MT provenance")
        source_id = self.source_id.strip().lower()
        if (
            self.temperature_basis is MTTemperatureBasis.CORE_PAPER_DIRECT
            and not source_id.startswith("10.")
        ):
            raise ValueError("core paper MT values require a DOI source_id")
        if (
            self.temperature_basis
            is MTTemperatureBasis.AUTHOR_NORMALIZED_ENTHALPY
            and not source_id.startswith("author:")
        ):
            raise ValueError("author MT sensitivities require an author: source_id")

    @property
    def low_grade_delta_k(self) -> float:
        return self.temperature_mt_c - self.temperature_lt_c

    @property
    def high_grade_delta_k(self) -> float:
        return self.temperature_ht_c - self.temperature_mt_c

    @property
    def total_delta_k(self) -> float:
        return self.temperature_ht_c - self.temperature_lt_c

    @property
    def high_grade_enthalpy_fraction(self) -> float:
        return 1.0 - self.low_grade_enthalpy_fraction


@dataclass(frozen=True)
class MTScenarioSet:
    """A pre-registered MT set on one fixed LT/HT material envelope."""

    set_id: str
    temperature_lt_c: float
    temperature_ht_c: float
    endpoint_source_doi: str
    points: tuple[MTScenarioPoint, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.set_id, str) or not self.set_id.strip():
            raise ValueError("set_id must be non-empty")
        endpoints = (self.temperature_lt_c, self.temperature_ht_c)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in endpoints
        ):
            raise ValueError("MT scenario endpoints must be finite")
        if self.temperature_ht_c <= self.temperature_lt_c:
            raise ValueError("HT endpoint must exceed LT endpoint")
        if not isinstance(self.endpoint_source_doi, str) or not (
            self.endpoint_source_doi.strip().lower().startswith("10.")
        ):
            raise ValueError("LT/HT endpoint evidence requires a DOI")
        if not isinstance(self.points, tuple) or not self.points:
            raise ValueError("MT scenario set requires at least one point")
        if any(not isinstance(point, MTScenarioPoint) for point in self.points):
            raise ValueError("points must contain MTScenarioPoint values")

        identifiers = tuple(point.scenario_id for point in self.points)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("MT scenario ids must be unique")
        fractions = tuple(
            point.low_grade_enthalpy_fraction for point in self.points
        )
        if any(
            later <= earlier
            for earlier, later in zip(fractions, fractions[1:])
        ):
            raise ValueError("MT scenario fractions must be strictly increasing")

        for point in self.points:
            if not math.isclose(
                point.temperature_lt_c,
                self.temperature_lt_c,
                rel_tol=0.0,
                abs_tol=1e-9,
            ) or not math.isclose(
                point.temperature_ht_c,
                self.temperature_ht_c,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError("all MT points must share the set LT/HT endpoints")
            expected_mt = self.temperature_lt_c + (
                point.low_grade_enthalpy_fraction * self.total_delta_k
            )
            if not math.isclose(
                point.temperature_mt_c,
                expected_mt,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    "MT temperature must follow the normalized enthalpy definition"
                )

    @property
    def total_delta_k(self) -> float:
        return self.temperature_ht_c - self.temperature_lt_c

    @property
    def scenario_ids(self) -> tuple[str, ...]:
        return tuple(point.scenario_id for point in self.points)

    def point(self, scenario_id: str) -> MTScenarioPoint:
        for point in self.points:
            if point.scenario_id == scenario_id:
                return point
        raise ValueError(f"unknown MT scenario_id: {scenario_id}")

    def apply_to_tes(self, tes: TESFixedSpec, scenario_id: str) -> TESFixedSpec:
        """Replace only MT after checking that the LT/HT endpoints match."""

        if not isinstance(tes, TESFixedSpec):
            raise ValueError("tes must be a TESFixedSpec")
        physics = tes.physics
        if not math.isclose(
            physics.temperature_lt,
            self.temperature_lt_c,
            rel_tol=0.0,
            abs_tol=1e-9,
        ) or not math.isclose(
            physics.temperature_ht,
            self.temperature_ht_c,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("TES LT/HT endpoints do not match the MT scenario set")
        selected = self.point(scenario_id)
        return replace(
            tes,
            physics=replace(
                physics,
                temperature_mt=selected.temperature_mt_c,
            ),
        )

    def certify_heat_delivery(
        self,
        tes: TESFixedSpec,
        *,
        heat_network: HeatNetworkPinchSpec,
        material: MoltenSaltMaterialEnvelope,
        dispatch_interval_hours: float,
    ) -> tuple[TESHeatDeliveryPinchAudit, ...]:
        """Certify every pre-registered MT point against one disclosed boundary."""

        audits: list[TESHeatDeliveryPinchAudit] = []
        for point in self.points:
            audit = TESHeatDeliveryPinchAudit(
                tes=self.apply_to_tes(tes, point.scenario_id),
                heat_network=heat_network,
                material=material,
                dispatch_interval_hours=dispatch_interval_hours,
            )
            try:
                audit.certify_heat_delivery()
            except ValueError as error:
                raise ValueError(
                    f"MT scenario {point.scenario_id} is infeasible: {error}"
                ) from error
            audits.append(audit)
        return tuple(audits)


def build_e0d8_hitec_normalized_mt_scenarios() -> MTScenarioSet:
    """Build author sensitivities; no returned MT is a site or paper value."""

    temperature_lt_c = 180.0
    temperature_ht_c = 390.0
    source_id = "author:e0-d-8-normalized-enthalpy-quartiles-v1"
    definitions = (
        ("low_grade_25", 0.25),
        ("balanced_50", 0.50),
        ("low_grade_75", 0.75),
    )
    points = tuple(
        MTScenarioPoint(
            scenario_id=scenario_id,
            temperature_lt_c=temperature_lt_c,
            temperature_mt_c=temperature_lt_c
            + fraction * (temperature_ht_c - temperature_lt_c),
            temperature_ht_c=temperature_ht_c,
            low_grade_enthalpy_fraction=fraction,
            temperature_basis=MTTemperatureBasis.AUTHOR_NORMALIZED_ENTHALPY,
            source_id=source_id,
        )
        for scenario_id, fraction in definitions
    )
    return MTScenarioSet(
        set_id="e0-d-8-hitec-normalized-enthalpy-v1",
        temperature_lt_c=temperature_lt_c,
        temperature_ht_c=temperature_ht_c,
        endpoint_source_doi="10.1016/j.apenergy.2025.126876",
        points=points,
    )
