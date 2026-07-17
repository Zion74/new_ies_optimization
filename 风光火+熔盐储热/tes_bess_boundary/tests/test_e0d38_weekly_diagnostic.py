from __future__ import annotations

from pathlib import Path

import pytest

from tes_bess_boundary.e0d38_weekly_diagnostic import (
    evaluate_minimum_curtailment_gate,
    group_actual_weeks,
    group_representative_weeks,
    summarize_assignment_error,
    validate_d39_gate_b_artifacts,
)


def _d39_data_file(name: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "数据采集"
        / "e0d39_service_aware_representative_weeks"
        / name
    )


def test_d39_gate_b_artifact_pair_is_hash_and_name_locked(tmp_path: Path) -> None:
    periods = _d39_data_file("e0d39_representative_periods.csv")
    assignments = _d39_data_file("e0d39_week_assignments.csv")

    validated = validate_d39_gate_b_artifacts(periods, assignments)
    assert validated == {
        "representative_periods_sha256": (
            "fb7aa1e9d8815a2a22eee68b61af12b44c4485ba3ca464d21652480d9b75c2ac"
        ),
        "week_assignments_sha256": (
            "7949d6f58d86787cf9ea8129dae3adc85ec20ffba8a157ad7e121395f2f5052e"
        ),
    }

    wrong_name = tmp_path / "assignments.csv"
    wrong_name.write_bytes(assignments.read_bytes())
    with pytest.raises(ValueError, match="must be named"):
        validate_d39_gate_b_artifacts(periods, wrong_name)

    tampered = tmp_path / "e0d39_week_assignments.csv"
    tampered.write_bytes(assignments.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_d39_gate_b_artifacts(periods, tampered)


def test_minimum_curtailment_gate_requires_classification_and_one_pp() -> None:
    gate = evaluate_minimum_curtailment_gate(
        actual_minimum_curtailment_mwh=560.0,
        representative_minimum_curtailment_mwh=530.0,
        actual_renewable_available_mwh=3_000.0,
        epsilon_ceiling_mwh=300.0,
    )

    assert gate["feasibility_classification_consistent"] is True
    assert gate["absolute_natural_curtailment_rate_error_percentage_points"] == (
        pytest.approx(1.0)
    )
    assert gate["passed"] is True

    classification_failure = evaluate_minimum_curtailment_gate(
        actual_minimum_curtailment_mwh=560.0,
        representative_minimum_curtailment_mwh=299.0,
        actual_renewable_available_mwh=3_000.0,
        epsilon_ceiling_mwh=300.0,
    )
    assert classification_failure["passed"] is False

    quantitative_failure = evaluate_minimum_curtailment_gate(
        actual_minimum_curtailment_mwh=560.0,
        representative_minimum_curtailment_mwh=500.0,
        actual_renewable_available_mwh=3_000.0,
        epsilon_ceiling_mwh=300.0,
    )
    assert quantitative_failure["feasibility_classification_consistent"] is True
    assert quantitative_failure["passed"] is False


def test_group_actual_weeks_retains_52_weeks_and_tail() -> None:
    curtailment = [1.0] * 8_784
    renewable = [2.0] * 8_784

    weeks, tail = group_actual_weeks(curtailment, renewable)

    assert len(weeks) == 52
    assert weeks[1]["curtailment_mwh"] == pytest.approx(168.0)
    assert weeks[52]["curtailment_rate"] == pytest.approx(0.5)
    assert tail["curtailment_mwh"] == pytest.approx(48.0)


def test_representative_grouping_excludes_tail_warmup() -> None:
    rows = [
        {"source_role": "representative_scored", "source_week_index": "4"},
        {"source_role": "tail_warmup", "source_week_index": "52"},
        {"source_role": "tail_scored", "source_week_index": ""},
    ]

    weeks, tail = group_representative_weeks(
        [3.0, 100.0, 5.0],
        [6.0, 100.0, 10.0],
        rows,
    )

    assert weeks[4]["curtailment_mwh"] == pytest.approx(3.0)
    assert tail["curtailment_mwh"] == pytest.approx(5.0)
    assert tail["curtailment_rate"] == pytest.approx(0.5)


def test_assignment_summary_ranks_underrepresented_actual_week() -> None:
    actual = {
        1: {"curtailment_mwh": 12.0, "curtailment_rate": 0.2},
        2: {"curtailment_mwh": 4.0, "curtailment_rate": 0.1},
    }
    representatives = {
        4: {"curtailment_mwh": 5.0, "curtailment_rate": 0.1},
    }
    assignments = [
        {
            "original_week_index": "1",
            "assigned_representative_week_index": "4",
            "week_start": "2024-01-01T00:00:00",
            "week_end": "2024-01-07T23:00:00",
        },
        {
            "original_week_index": "2",
            "assigned_representative_week_index": "4",
            "week_start": "2024-01-08T00:00:00",
            "week_end": "2024-01-14T23:00:00",
        },
    ]

    weekly, clusters = summarize_assignment_error(
        actual,
        representatives,
        assignments,
    )

    assert weekly[0]["original_week_index"] == 1
    assert weekly[0]["curtailment_underrepresentation_mwh"] == pytest.approx(7.0)
    assert clusters[0]["actual_minimum_curtailment_mwh"] == pytest.approx(16.0)
    assert clusters[0]["representative_projected_curtailment_mwh"] == pytest.approx(
        10.0
    )
