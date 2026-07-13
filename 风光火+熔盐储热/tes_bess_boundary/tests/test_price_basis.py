from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _write_valid_snapshot(directory: Path) -> Path:
    raw_path = directory / "official_source.csv"
    raw_path.write_bytes(b"official evidence\n")
    snapshot = {
        "schema": "tes_bess_boundary.e0d4_price_basis.v1",
        "target_currency": "CNY",
        "target_year": 2024,
        "price_indices": [
            {
                "currency": "EUR",
                "series_id": "Eurostat prc_hicp_aind EA20 CP00 INX_A_AVG",
                "source_file": raw_path.name,
                "observations": {"2022": 116.83, "2024": 126.08},
            }
        ],
        "exchange_rates": [
            {
                "source_currency": "EUR",
                "target_currency": "CNY",
                "year": 2024,
                "target_per_source": 7.787469921875,
                "series_id": "ECB EXR.A.CNY.EUR.SP00.A",
                "source_file": raw_path.name,
            }
        ],
    }
    snapshot_path = directory / "price_basis_snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "tes_bess_boundary.e0d4_price_basis_manifest.v1",
        "snapshot": {
            "file": snapshot_path.name,
            "sha256": hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),
        },
        "sources": [
            {
                "file": raw_path.name,
                "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "url": "https://example.test/official-source",
            }
        ],
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return directory


def test_official_snapshot_builds_an_exact_auditable_conversion(
    tmp_path: Path,
) -> None:
    from tes_bess_boundary.price_basis import load_price_basis_snapshot

    snapshot = load_price_basis_snapshot(_write_valid_snapshot(tmp_path))
    conversion = snapshot.to_conversion("EUR", 2022)

    assert conversion.source_price_index == 116.83
    assert conversion.target_price_index == 126.08
    assert conversion.target_currency_per_source_currency == 7.787469921875
    assert conversion.price_index_series_id == (
        "Eurostat prc_hicp_aind EA20 CP00 INX_A_AVG"
    )
    assert conversion.exchange_rate_series_id == "ECB EXR.A.CNY.EUR.SP00.A"
    assert conversion.conversion_factor == pytest.approx(8.404041836428999)


def test_official_snapshot_rejects_tampered_source_evidence(tmp_path: Path) -> None:
    from tes_bess_boundary.price_basis import load_price_basis_snapshot

    directory = _write_valid_snapshot(tmp_path)
    (directory / "official_source.csv").write_bytes(b"tampered\n")

    with pytest.raises(ValueError, match="source SHA-256"):
        load_price_basis_snapshot(directory)


def test_official_snapshot_rejects_ambiguous_duplicate_series(tmp_path: Path) -> None:
    from tes_bess_boundary.price_basis import load_price_basis_snapshot

    directory = _write_valid_snapshot(tmp_path)
    snapshot_path = directory / "price_basis_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot["price_indices"].append(dict(snapshot["price_indices"][0]))
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["snapshot"]["sha256"] = hashlib.sha256(
        snapshot_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate price-index currency"):
        load_price_basis_snapshot(directory)
