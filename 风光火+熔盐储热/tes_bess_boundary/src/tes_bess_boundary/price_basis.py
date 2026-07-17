"""Auditable official price-index and exchange-rate snapshot loading."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path

from tes_bess_boundary.economics import PriceBasisConversion


SNAPSHOT_SCHEMA = "tes_bess_boundary.e0d4_price_basis.v1"
MANIFEST_SCHEMA = "tes_bess_boundary.e0d4_price_basis_manifest.v1"


def _currency(value: object, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or not value.isalpha()
        or value != value.upper()
    ):
        raise ValueError(f"{field_name} must be an uppercase ISO 4217 currency code")
    return value


def _positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be finite and positive")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{field_name} must be finite and positive")
    return number


@dataclass(frozen=True)
class OfficialPriceIndexSeries:
    """One disclosed annual price-index series."""

    currency: str
    series_id: str
    source_file: str
    observations: tuple[tuple[int, float], ...]

    def value_for(self, year: int) -> float:
        for observation_year, value in self.observations:
            if observation_year == year:
                return value
        raise ValueError(
            f"price-index series {self.series_id} has no observation for {year}"
        )


@dataclass(frozen=True)
class OfficialExchangeRateSeries:
    """One disclosed annual target-currency-per-source-currency rate."""

    source_currency: str
    target_currency: str
    year: int
    target_per_source: float
    series_id: str
    source_file: str


@dataclass(frozen=True)
class OfficialPriceBasisSnapshot:
    """Canonical official evidence that can build one conversion contract."""

    target_currency: str
    target_year: int
    price_indices: tuple[OfficialPriceIndexSeries, ...]
    exchange_rates: tuple[OfficialExchangeRateSeries, ...]

    def to_conversion(
        self,
        source_currency: str,
        source_price_base_year: int,
    ) -> PriceBasisConversion:
        """Build the exact disclosed conversion for one registered source basis."""

        source_currency = _currency(source_currency, "source_currency")
        price_series = next(
            (
                series
                for series in self.price_indices
                if series.currency == source_currency
            ),
            None,
        )
        if price_series is None:
            raise ValueError(
                f"snapshot has no price-index series for {source_currency}"
            )
        exchange_rate = next(
            (
                series
                for series in self.exchange_rates
                if series.source_currency == source_currency
                and series.target_currency == self.target_currency
                and series.year == self.target_year
            ),
            None,
        )
        if exchange_rate is None:
            raise ValueError(
                f"snapshot has no {self.target_year} exchange rate for "
                f"{source_currency}/{self.target_currency}"
            )
        return PriceBasisConversion(
            source_currency=source_currency,
            source_price_base_year=source_price_base_year,
            target_currency=self.target_currency,
            target_price_base_year=self.target_year,
            source_price_index=price_series.value_for(source_price_base_year),
            target_price_index=price_series.value_for(self.target_year),
            target_currency_per_source_currency=exchange_rate.target_per_source,
            price_index_series_id=price_series.series_id,
            exchange_rate_series_id=exchange_rate.series_id,
        )


def _load_json_object(path: Path, description: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{description} must be readable valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{description} must contain a JSON object")
    return value


def _verify_registered_file(
    directory: Path,
    entry: dict[str, object],
    description: str,
) -> Path:
    file_name = entry.get("file")
    recorded_sha256 = entry.get("sha256")
    if not isinstance(file_name, str) or not file_name.strip():
        raise ValueError(f"{description} file must be a non-empty string")
    if (
        not isinstance(recorded_sha256, str)
        or len(recorded_sha256) != 64
        or any(character not in "0123456789abcdef" for character in recorded_sha256)
    ):
        raise ValueError(f"{description} SHA-256 must be lowercase hexadecimal")
    registered_path = (directory / file_name).resolve()
    if not registered_path.is_relative_to(directory.resolve()):
        raise ValueError(f"{description} file must stay inside the snapshot directory")
    try:
        actual_sha256 = hashlib.sha256(registered_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"{description} file must be readable") from error
    if actual_sha256 != recorded_sha256:
        raise ValueError(f"{description} SHA-256 does not match the registered file")
    return registered_path


def load_price_basis_snapshot(path: str | Path) -> OfficialPriceBasisSnapshot:
    """Load one E0-D-4 snapshot directory through its public manifest."""

    directory = Path(path)
    manifest = _load_json_object(directory / "manifest.json", "price-basis manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"price-basis manifest schema must be {MANIFEST_SCHEMA}")
    snapshot_entry = manifest.get("snapshot")
    if not isinstance(snapshot_entry, dict):
        raise ValueError("price-basis manifest must register the snapshot file")
    snapshot_path = _verify_registered_file(
        directory,
        snapshot_entry,
        "snapshot",
    )
    source_entries = manifest.get("sources")
    if not isinstance(source_entries, list) or not source_entries:
        raise ValueError("price-basis manifest must register official sources")
    registered_sources: set[str] = set()
    for entry in source_entries:
        if not isinstance(entry, dict):
            raise ValueError("price-basis source entries must be JSON objects")
        source_path = _verify_registered_file(directory, entry, "source")
        source_url = entry.get("url")
        if not isinstance(source_url, str) or not source_url.startswith("https://"):
            raise ValueError("price-basis source URL must use HTTPS")
        registered_sources.add(source_path.relative_to(directory.resolve()).as_posix())
    snapshot = _load_json_object(
        snapshot_path,
        "price-basis snapshot",
    )
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError(f"price-basis snapshot schema must be {SNAPSHOT_SCHEMA}")
    target_currency = _currency(snapshot.get("target_currency"), "target_currency")
    target_year = snapshot.get("target_year")
    if isinstance(target_year, bool) or not isinstance(target_year, int):
        raise ValueError("target_year must be a positive integer")
    if target_year <= 0:
        raise ValueError("target_year must be a positive integer")

    price_indices: list[OfficialPriceIndexSeries] = []
    raw_price_indices = snapshot.get("price_indices")
    if not isinstance(raw_price_indices, list) or not raw_price_indices:
        raise ValueError("price_indices must contain at least one series")
    registered_price_currencies: set[str] = set()
    for raw_series in raw_price_indices:
        if not isinstance(raw_series, dict):
            raise ValueError("price-index entries must be JSON objects")
        series_id = raw_series.get("series_id")
        source_file = raw_series.get("source_file")
        observations = raw_series.get("observations")
        if not isinstance(series_id, str) or not series_id.strip():
            raise ValueError("price-index series_id must be a non-empty string")
        if not isinstance(source_file, str) or not source_file.strip():
            raise ValueError("price-index source_file must be a non-empty string")
        if Path(source_file).as_posix() not in registered_sources:
            raise ValueError(
                "price-index source_file must be registered in the manifest"
            )
        if not isinstance(observations, dict) or not observations:
            raise ValueError("price-index observations must be a non-empty object")
        parsed_observations = tuple(
            sorted(
                (
                    int(year),
                    _positive_number(value, "price-index observation"),
                )
                for year, value in observations.items()
            )
        )
        currency = _currency(raw_series.get("currency"), "currency")
        if currency in registered_price_currencies:
            raise ValueError(f"duplicate price-index currency: {currency}")
        registered_price_currencies.add(currency)
        price_indices.append(
            OfficialPriceIndexSeries(
                currency=currency,
                series_id=series_id,
                source_file=source_file,
                observations=parsed_observations,
            )
        )

    exchange_rates: list[OfficialExchangeRateSeries] = []
    raw_exchange_rates = snapshot.get("exchange_rates")
    if not isinstance(raw_exchange_rates, list) or not raw_exchange_rates:
        raise ValueError("exchange_rates must contain at least one series")
    for raw_series in raw_exchange_rates:
        if not isinstance(raw_series, dict):
            raise ValueError("exchange-rate entries must be JSON objects")
        year = raw_series.get("year")
        series_id = raw_series.get("series_id")
        source_file = raw_series.get("source_file")
        if isinstance(year, bool) or not isinstance(year, int) or year <= 0:
            raise ValueError("exchange-rate year must be a positive integer")
        if not isinstance(series_id, str) or not series_id.strip():
            raise ValueError("exchange-rate series_id must be a non-empty string")
        if not isinstance(source_file, str) or not source_file.strip():
            raise ValueError("exchange-rate source_file must be a non-empty string")
        if Path(source_file).as_posix() not in registered_sources:
            raise ValueError(
                "exchange-rate source_file must be registered in the manifest"
            )
        exchange_rates.append(
            OfficialExchangeRateSeries(
                source_currency=_currency(
                    raw_series.get("source_currency"),
                    "source_currency",
                ),
                target_currency=_currency(
                    raw_series.get("target_currency"),
                    "target_currency",
                ),
                year=year,
                target_per_source=_positive_number(
                    raw_series.get("target_per_source"),
                    "target_per_source",
                ),
                series_id=series_id,
                source_file=source_file,
            )
        )

    return OfficialPriceBasisSnapshot(
        target_currency=target_currency,
        target_year=target_year,
        price_indices=tuple(price_indices),
        exchange_rates=tuple(exchange_rates),
    )
