"""E0-D-42 native HiGHS LP fingerprints and interruptible lower bounds.

This module is the Gate A implementation surface.  It deliberately operates
on a frozen ``HighsLp`` rather than parsing solver logs or trusting the Pyomo
Appsi result wrapper.  A row-multiplier vector is converted into a rigorous
Lagrangian lower bound using outward-rounded Decimal interval arithmetic.
"""

from __future__ import annotations

import hashlib
import math
import struct
import sys
from array import array
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Iterable, Sequence


LP_FINGERPRINT_SCHEMA_ID = "tes_bess_boundary.e0d42_highs_lp_fingerprint.v1"
CERTIFICATE_SCHEMA_ID = "tes_bess_boundary.e0d42_lagrangian_certificate.v1"
MINIMUM_DECIMAL_PRECISION = 80
SUPPORTED_HIGHS_VERSION = "1.15.1"


def _sense_token(lp: object) -> str:
    token = str(lp.sense_)
    if token.endswith("kMinimize"):
        return "minimize"
    if token.endswith("kMaximize"):
        return "maximize"
    raise ValueError(f"unsupported HiGHS objective sense: {token}")


def _integrality_token(value: object) -> int:
    token = str(value)
    mapping = {
        "kContinuous": 0,
        "kInteger": 1,
        "kSemiContinuous": 2,
        "kSemiInteger": 3,
        "kImplicitInteger": 4,
    }
    for suffix, number in mapping.items():
        if token.endswith(suffix):
            return number
    raise ValueError(f"unsupported HiGHS integrality value: {token}")


def _require_colwise(lp: object) -> None:
    if not str(lp.a_matrix_.format_).endswith("kColwise"):
        raise ValueError("D42 certificates require a column-wise HighsLp")


def audit_highs_lp(lp: object) -> dict[str, Any]:
    """Validate the structural arrays used by the D42 fingerprint/certificate."""

    _require_colwise(lp)
    num_col = int(lp.num_col_)
    num_row = int(lp.num_row_)
    starts = lp.a_matrix_.start_
    indices = lp.a_matrix_.index_
    values = lp.a_matrix_.value_
    lengths = {
        "col_cost": len(lp.col_cost_),
        "col_lower": len(lp.col_lower_),
        "col_upper": len(lp.col_upper_),
        "row_lower": len(lp.row_lower_),
        "row_upper": len(lp.row_upper_),
        "matrix_start": len(starts),
        "matrix_index": len(indices),
        "matrix_value": len(values),
        "integrality": len(lp.integrality_),
    }
    if lengths["col_cost"] != num_col:
        raise ValueError("column cost length does not match num_col")
    if lengths["col_lower"] != num_col or lengths["col_upper"] != num_col:
        raise ValueError("column bound length does not match num_col")
    if lengths["row_lower"] != num_row or lengths["row_upper"] != num_row:
        raise ValueError("row bound length does not match num_row")
    if lengths["matrix_start"] != num_col + 1:
        raise ValueError("column-wise matrix start must have num_col + 1 entries")
    if lengths["matrix_index"] != lengths["matrix_value"]:
        raise ValueError("matrix index/value lengths differ")
    if int(starts[0]) != 0 or int(starts[-1]) != lengths["matrix_value"]:
        raise ValueError("matrix start endpoints are inconsistent")
    if any(int(starts[i]) > int(starts[i + 1]) for i in range(num_col)):
        raise ValueError("matrix starts are not monotone")
    if any(int(index) < 0 or int(index) >= num_row for index in indices):
        raise ValueError("matrix row index lies outside the LP")
    if not all(math.isfinite(float(value)) for value in lp.col_cost_):
        raise ValueError("LP objective contains a non-finite coefficient")
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("LP matrix contains a non-finite coefficient")
    if lengths["integrality"] not in {0, num_col}:
        raise ValueError("integrality vector must be empty or have num_col entries")
    noncontinuous = sum(
        _integrality_token(value) != 0 for value in lp.integrality_
    )
    return {
        "schema_id": LP_FINGERPRINT_SCHEMA_ID,
        "objective_sense": _sense_token(lp),
        "num_col": num_col,
        "num_row": num_row,
        "num_nz": lengths["matrix_value"],
        "noncontinuous_column_count": noncontinuous,
        "array_lengths": lengths,
        "passed": True,
    }


def _update_scalar(hasher: Any, label: str, payload: bytes) -> None:
    encoded = label.encode("utf-8")
    hasher.update(struct.pack("<Q", len(encoded)))
    hasher.update(encoded)
    hasher.update(struct.pack("<Q", len(payload)))
    hasher.update(payload)


def _update_array(
    hasher: Any,
    label: str,
    values: Iterable[Any],
    *,
    typecode: str,
    coercer: Any,
) -> None:
    normalized = array(typecode, (coercer(value) for value in values))
    if sys.byteorder != "little":
        normalized.byteswap()
    _update_scalar(
        hasher,
        label,
        struct.pack("<Q", len(normalized)) + normalized.tobytes(),
    )


def fingerprint_highs_lp(lp: object) -> str:
    """Return a cross-platform SHA-256 over the complete numerical LP identity."""

    audit = audit_highs_lp(lp)
    hasher = hashlib.sha256()
    _update_scalar(hasher, "schema", LP_FINGERPRINT_SCHEMA_ID.encode("ascii"))
    _update_scalar(hasher, "sense", audit["objective_sense"].encode("ascii"))
    _update_scalar(hasher, "num_col", struct.pack("<q", audit["num_col"]))
    _update_scalar(hasher, "num_row", struct.pack("<q", audit["num_row"]))
    _update_scalar(hasher, "offset", struct.pack("<d", float(lp.offset_)))
    _update_array(hasher, "col_cost", lp.col_cost_, typecode="d", coercer=float)
    _update_array(hasher, "col_lower", lp.col_lower_, typecode="d", coercer=float)
    _update_array(hasher, "col_upper", lp.col_upper_, typecode="d", coercer=float)
    _update_array(hasher, "row_lower", lp.row_lower_, typecode="d", coercer=float)
    _update_array(hasher, "row_upper", lp.row_upper_, typecode="d", coercer=float)
    _update_array(
        hasher,
        "integrality",
        lp.integrality_,
        typecode="b",
        coercer=_integrality_token,
    )
    _update_array(
        hasher,
        "matrix_start",
        lp.a_matrix_.start_,
        typecode="q",
        coercer=int,
    )
    _update_array(
        hasher,
        "matrix_index",
        lp.a_matrix_.index_,
        typecode="q",
        coercer=int,
    )
    _update_array(
        hasher,
        "matrix_value",
        lp.a_matrix_.value_,
        typecode="d",
        coercer=float,
    )
    return hasher.hexdigest()


def _decimal(value: float) -> Decimal:
    if not math.isfinite(value):
        raise ValueError("cannot convert a non-finite endpoint to Decimal")
    return Decimal.from_float(value)


def _product_interval(
    left: Decimal,
    right: Decimal,
    down: Context,
    up: Context,
) -> tuple[Decimal, Decimal]:
    return down.multiply(left, right), up.multiply(left, right)


def _residual_bound_interval(
    *,
    residual_lower: Decimal,
    residual_upper: Decimal,
    lower: float,
    upper: float,
    down: Context,
    up: Context,
) -> tuple[Decimal, Decimal] | None:
    lower_finite = math.isfinite(lower)
    upper_finite = math.isfinite(upper)
    zero = Decimal(0)
    if lower_finite and upper_finite:
        lower_d = _decimal(lower)
        upper_d = _decimal(upper)
        lower_products: list[Decimal] = []
        upper_products: list[Decimal] = []
        for residual in (residual_lower, residual_upper):
            for bound in (lower_d, upper_d):
                product_lower, product_upper = _product_interval(
                    residual, bound, down, up
                )
                lower_products.append(product_lower)
                upper_products.append(product_upper)
        if residual_lower <= zero <= residual_upper:
            lower_products.append(zero)
            upper_products.append(zero)
        return min(lower_products), max(upper_products)
    if lower_finite and not upper_finite:
        if residual_lower < zero:
            return None
        lower_d = _decimal(lower)
        first = _product_interval(residual_lower, lower_d, down, up)
        second = _product_interval(residual_upper, lower_d, down, up)
        return min(first[0], second[0]), max(first[1], second[1])
    if not lower_finite and upper_finite:
        if residual_upper > zero:
            return None
        upper_d = _decimal(upper)
        first = _product_interval(residual_lower, upper_d, down, up)
        second = _product_interval(residual_upper, upper_d, down, up)
        return min(first[0], second[0]), max(first[1], second[1])
    if residual_lower == zero and residual_upper == zero:
        return zero, zero
    return None


@dataclass(frozen=True)
class LagrangianCertificate:
    """Auditable lower-bound result for one frozen minimization LP."""

    lp_sha256: str
    precision: int
    row_multiplier_count: int
    projected_row_multiplier_count: int
    invalid_column_endpoint_count: int
    lower_bound_decimal: str | None
    upper_bound_decimal: str | None
    lower_bound_float: float | None
    interval_width_decimal: str | None
    eligible: bool
    status: str

    def to_audit(self) -> dict[str, Any]:
        return {
            "schema_id": CERTIFICATE_SCHEMA_ID,
            "lp_sha256": self.lp_sha256,
            "decimal_precision": self.precision,
            "row_multiplier_count": self.row_multiplier_count,
            "projected_row_multiplier_count": (
                self.projected_row_multiplier_count
            ),
            "invalid_column_endpoint_count": self.invalid_column_endpoint_count,
            "lower_bound_decimal": self.lower_bound_decimal,
            "upper_bound_decimal": self.upper_bound_decimal,
            "lower_bound_float": self.lower_bound_float,
            "interval_width_decimal": self.interval_width_decimal,
            "formal_lower_bound_eligible": self.eligible,
            "status": self.status,
        }


def certify_lagrangian_lower_bound(
    lp: object,
    row_multipliers: Sequence[float],
    *,
    expected_lp_sha256: str | None = None,
    precision: int = MINIMUM_DECIMAL_PRECISION,
) -> LagrangianCertificate:
    """Compute an outward-rounded Lagrangian lower bound for a frozen LP."""

    if precision < MINIMUM_DECIMAL_PRECISION:
        raise ValueError(
            f"D42 requires decimal precision >= {MINIMUM_DECIMAL_PRECISION}"
        )
    audit = audit_highs_lp(lp)
    if audit["objective_sense"] != "minimize":
        raise ValueError("D42 lower-bound certification requires minimization")
    if audit["noncontinuous_column_count"] != 0:
        raise ValueError("D42 Lagrangian certification requires a continuous LP")
    lp_sha256 = fingerprint_highs_lp(lp)
    if expected_lp_sha256 is not None and lp_sha256 != expected_lp_sha256:
        raise ValueError("LP fingerprint differs from the locked D42 identity")
    if len(row_multipliers) != audit["num_row"]:
        raise ValueError("row multiplier length does not match num_row")
    multiplier_values = tuple(float(value) for value in row_multipliers)
    if not all(math.isfinite(value) for value in multiplier_values):
        raise ValueError("row multipliers must all be finite")

    down = Context(prec=precision, rounding=ROUND_FLOOR)
    up = Context(prec=precision, rounding=ROUND_CEILING)
    zero = Decimal(0)
    total_lower = _decimal(float(lp.offset_))
    total_upper = total_lower
    projected: list[float] = []
    projected_count = 0

    for multiplier, raw_lower, raw_upper in zip(
        multiplier_values, lp.row_lower_, lp.row_upper_
    ):
        lower = float(raw_lower)
        upper = float(raw_upper)
        if lower > upper:
            raise ValueError("row lower bound exceeds upper bound")
        lower_finite = math.isfinite(lower)
        upper_finite = math.isfinite(upper)
        repaired = multiplier
        if not lower_finite and not upper_finite:
            repaired = 0.0
        elif lower_finite and not upper_finite and repaired < 0.0:
            repaired = 0.0
        elif not lower_finite and upper_finite and repaired > 0.0:
            repaired = 0.0
        if repaired != multiplier:
            projected_count += 1
        projected.append(repaired)
        if repaired == 0.0:
            continue
        selected_bound = lower if repaired > 0.0 else upper
        if not math.isfinite(selected_bound):
            raise AssertionError("row multiplier projection selected infinity")
        term_lower, term_upper = _product_interval(
            _decimal(repaired), _decimal(selected_bound), down, up
        )
        total_lower = down.add(total_lower, term_lower)
        total_upper = up.add(total_upper, term_upper)

    projected_decimal = tuple(_decimal(value) for value in projected)
    starts = lp.a_matrix_.start_
    indices = lp.a_matrix_.index_
    matrix_values = lp.a_matrix_.value_
    invalid_columns = 0
    for column in range(audit["num_col"]):
        activity_lower = zero
        activity_upper = zero
        for position in range(int(starts[column]), int(starts[column + 1])):
            coefficient = _decimal(float(matrix_values[position]))
            multiplier = projected_decimal[int(indices[position])]
            product_lower, product_upper = _product_interval(
                coefficient, multiplier, down, up
            )
            activity_lower = down.add(activity_lower, product_lower)
            activity_upper = up.add(activity_upper, product_upper)
        cost = _decimal(float(lp.col_cost_[column]))
        residual_lower = down.subtract(cost, activity_upper)
        residual_upper = up.subtract(cost, activity_lower)
        lower = float(lp.col_lower_[column])
        upper = float(lp.col_upper_[column])
        if lower > upper:
            raise ValueError("column lower bound exceeds upper bound")
        contribution = _residual_bound_interval(
            residual_lower=residual_lower,
            residual_upper=residual_upper,
            lower=lower,
            upper=upper,
            down=down,
            up=up,
        )
        if contribution is None:
            invalid_columns += 1
            continue
        total_lower = down.add(total_lower, contribution[0])
        total_upper = up.add(total_upper, contribution[1])

    eligible = invalid_columns == 0 and total_lower.is_finite()
    if not eligible:
        return LagrangianCertificate(
            lp_sha256=lp_sha256,
            precision=precision,
            row_multiplier_count=len(multiplier_values),
            projected_row_multiplier_count=projected_count,
            invalid_column_endpoint_count=invalid_columns,
            lower_bound_decimal=None,
            upper_bound_decimal=None,
            lower_bound_float=None,
            interval_width_decimal=None,
            eligible=False,
            status="nonfinite_required_column_endpoint",
        )
    width = up.subtract(total_upper, total_lower)
    lower_as_float = float(total_lower)
    if not math.isfinite(lower_as_float):
        raise ValueError("certified lower bound is not representable as finite float")
    return LagrangianCertificate(
        lp_sha256=lp_sha256,
        precision=precision,
        row_multiplier_count=len(multiplier_values),
        projected_row_multiplier_count=projected_count,
        invalid_column_endpoint_count=0,
        lower_bound_decimal=str(total_lower),
        upper_bound_decimal=str(total_upper),
        lower_bound_float=lower_as_float,
        interval_width_decimal=str(width),
        eligible=True,
        status="certified_finite_lower_bound",
    )


@dataclass
class NativeTranslation:
    """Keep the Appsi owner alive together with its native HiGHS LP."""

    appsi_solver: object
    native_solver: object
    lp: object
    audit: dict[str, Any]


def translate_pyomo_model(model: object) -> NativeTranslation:
    """Translate a Pyomo LP once and expose the version-locked native model."""

    from pyomo.contrib.appsi.solvers.highs import Highs

    solver = Highs()
    solver.set_instance(model)
    native = solver._solver_model  # version-locked Pyomo 6.10.1 interface
    if native is None:
        raise RuntimeError("Appsi did not create a native HiGHS model")
    native.ensureColwise()
    lp = native.getLp()
    audit = audit_highs_lp(lp)
    audit.update(
        {
            "lp_sha256": fingerprint_highs_lp(lp),
            "pyomo_variable_map_count": len(solver._pyomo_var_to_solver_var_map),
            "pyomo_constraint_map_count": len(
                solver._pyomo_con_to_solver_con_map
            ),
            "highs_version": native.version(),
        }
    )
    return NativeTranslation(
        appsi_solver=solver,
        native_solver=native,
        lp=lp,
        audit=audit,
    )


@dataclass
class PresolvedLp:
    """Explicit HiGHS presolve output and its immutable identity audit."""

    owner: object
    lp: object
    audit: dict[str, Any]


def explicit_presolve(lp: object) -> PresolvedLp:
    """Run exactly one explicit presolve and return the resulting LP."""

    import highspy

    source_sha256 = fingerprint_highs_lp(lp)
    owner = highspy.Highs()
    owner.setOptionValue("output_flag", False)
    status = owner.passModel(lp)
    if status != highspy.HighsStatus.kOk:
        raise RuntimeError(f"HiGHS passModel failed: {status}")
    presolve_status = owner.presolve()
    if presolve_status != highspy.HighsStatus.kOk:
        raise RuntimeError(f"HiGHS presolve failed: {presolve_status}")
    presolved = owner.getPresolvedLp()
    audit = audit_highs_lp(presolved)
    audit.update(
        {
            "source_lp_sha256": source_sha256,
            "presolved_lp_sha256": fingerprint_highs_lp(presolved),
            "presolve_status": str(owner.getModelPresolveStatus()),
            "highs_version": owner.version(),
            "passed": True,
        }
    )
    return PresolvedLp(owner=owner, lp=presolved, audit=audit)


@dataclass
class NativeSolveSnapshot:
    """In-memory Gate A snapshot from an intentionally interrupted LP solve."""

    owner: object
    lp_sha256: str
    run_status: str
    model_status: str
    callback_iteration_counts: tuple[int, ...]
    info: object
    solution: object
    basis: object
    certificate: LagrangianCertificate

    def to_audit(self) -> dict[str, Any]:
        return {
            "lp_sha256": self.lp_sha256,
            "run_status": self.run_status,
            "model_status": self.model_status,
            "callback_iteration_counts": list(self.callback_iteration_counts),
            "simplex_iteration_count": int(self.info.simplex_iteration_count),
            "ipm_iteration_count": int(self.info.ipm_iteration_count),
            "primal_solution_status": self.owner.solutionStatusToString(
                self.info.primal_solution_status
            ),
            "dual_solution_status": self.owner.solutionStatusToString(
                self.info.dual_solution_status
            ),
            "basis_valid": bool(self.basis.valid),
            "certificate": self.certificate.to_audit(),
        }


def run_iteration_limited_lp(
    lp: object,
    *,
    solver_name: str,
    interrupt_after_iterations: int,
    basis: object | None = None,
    expected_lp_sha256: str | None = None,
    threads: int = 1,
) -> NativeSolveSnapshot:
    """Run IPX or dual simplex until a deterministic Gate A iteration callback."""

    import highspy

    if solver_name not in {"ipx", "simplex"}:
        raise ValueError("solver_name must be 'ipx' or 'simplex'")
    if interrupt_after_iterations < 1:
        raise ValueError("interrupt_after_iterations must be positive")
    if threads < 1:
        raise ValueError("threads must be positive")
    lp_sha256 = fingerprint_highs_lp(lp)
    if expected_lp_sha256 is not None and lp_sha256 != expected_lp_sha256:
        raise ValueError("LP fingerprint differs from the locked D42 identity")

    # HiGHS shares a scheduler within a process.  A previous solve with a
    # different thread count otherwise makes ``run`` fail with model status
    # ``Not Set``.  D42 runs solver phases sequentially, so a blocking reset is
    # both safe and required before applying the locked thread count.
    highspy.Highs.resetGlobalScheduler(True)
    owner = highspy.Highs()

    def set_option(name: str, value: object) -> None:
        status = owner.setOptionValue(name, value)
        if status != highspy.HighsStatus.kOk:
            raise RuntimeError(f"HiGHS rejected option {name}={value!r}: {status}")

    set_option("output_flag", False)
    set_option("presolve", "off")
    set_option("solver", solver_name)
    set_option("threads", threads)
    set_option("random_seed", 0)
    set_option("primal_feasibility_tolerance", 1e-7)
    set_option("dual_feasibility_tolerance", 1e-7)
    if solver_name == "ipx":
        set_option("run_crossover", "on")
    else:
        set_option("simplex_strategy", 1)
        set_option("simplex_scale_strategy", 2)
    status = owner.passModel(lp)
    if status != highspy.HighsStatus.kOk:
        raise RuntimeError(f"HiGHS passModel failed: {status}")
    if basis is not None:
        basis_status = owner.setBasis(basis)
        if basis_status != highspy.HighsStatus.kOk:
            raise ValueError(f"HiGHS rejected the checkpoint basis: {basis_status}")

    callback_counts: list[int] = []

    def interrupt(event: object) -> None:
        count = int(
            event.data_out.ipm_iteration_count
            if solver_name == "ipx"
            else event.data_out.simplex_iteration_count
        )
        callback_counts.append(count)
        if count >= interrupt_after_iterations:
            event.interrupt()

    if solver_name == "ipx":
        owner.cbIpmInterrupt += interrupt
    else:
        owner.cbSimplexInterrupt += interrupt
    run_status = owner.run()
    if run_status == highspy.HighsStatus.kError:
        raise RuntimeError("HiGHS failed before producing an interruptible LP snapshot")
    solution = owner.getSolution()
    info = owner.getInfo()
    solved_basis = owner.getBasis()
    certificate = certify_lagrangian_lower_bound(
        owner.getLp(),
        tuple(float(value) for value in solution.row_dual),
        expected_lp_sha256=lp_sha256,
    )
    return NativeSolveSnapshot(
        owner=owner,
        lp_sha256=lp_sha256,
        run_status=str(run_status),
        model_status=owner.modelStatusToString(owner.getModelStatus()),
        callback_iteration_counts=tuple(callback_counts),
        info=info,
        solution=solution,
        basis=solved_basis,
        certificate=certificate,
    )
