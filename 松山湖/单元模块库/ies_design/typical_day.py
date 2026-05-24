from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any


MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class TypicalDayGenerator:
    """Generate current-backend-compatible typical day files."""

    @staticmethod
    def read_user_selected(path: str | Path) -> list[dict[str, Any]]:
        path = Path(path)
        if path.suffix.lower() in {".xlsx", ".xlsm"}:
            return _read_xlsx(path)
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return [_normalize_typical_row(row) for row in csv.DictReader(f)]

    @classmethod
    def generate_monthly_template(cls, output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        start = 1
        for days in MONTH_DAYS:
            end = start + days - 1
            medoid = start + days // 2
            rows.append({
                "typicalDayId": medoid,
                "weight": days,
                "days": ",".join(str(day) for day in range(start, end + 1)),
            })
            start = end + 1
        return _write_outputs(output_dir, rows, "monthly_template", "每月 1 个典型日，权重为该月天数。")

    @classmethod
    def cluster_from_8760(
        cls,
        data_file: str | Path,
        output_dir: str | Path,
        n_clusters: int = 14,
        columns: list[str] | None = None,
        max_iter: int = 20,
    ) -> dict[str, Path]:
        data_file = Path(data_file)
        output_dir = Path(output_dir)
        daily_vectors = _read_daily_vectors(data_file, columns)
        if not 1 <= n_clusters <= len(daily_vectors):
            raise ValueError(f"n_clusters must be between 1 and {len(daily_vectors)}")

        scaled = _scale_vectors(daily_vectors)
        labels = _kmeans_labels(scaled, n_clusters=n_clusters, max_iter=max_iter)
        rows = _labels_to_typical_rows(scaled, labels, n_clusters)
        return _write_outputs(
            output_dir,
            rows,
            "cluster_from_8760",
            f"从 {data_file} 聚类生成 {n_clusters} 个典型日。",
            daily_vectors=daily_vectors,
        )


def _read_xlsx(path: Path) -> list[dict[str, Any]]:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Reading xlsx typical day files requires openpyxl. Use `uv run python ...`.") from exc

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(value) for value in rows[0]]
    output = []
    for row in rows[1:]:
        item = {headers[idx]: row[idx] for idx in range(len(headers)) if idx < len(row)}
        if any(value not in (None, "") for value in item.values()):
            output.append(_normalize_typical_row(item))
    return output


def _normalize_typical_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "typicalDayId": int(row["typicalDayId"]),
        "weight": int(row.get("weight") or len(str(row.get("days", "")).split(","))),
        "days": str(row["days"]),
    }


def _read_daily_vectors(data_file: Path, columns: list[str] | None) -> list[list[float]]:
    with data_file.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) % 24 != 0:
        raise ValueError(f"8760 data row count must be a multiple of 24, got {len(rows)}")
    if len(rows) < 24:
        raise ValueError("8760 data must contain at least one day")
    if columns is None:
        columns = [key for key in rows[0] if _is_number(rows[0].get(key))]
    if not columns:
        raise ValueError("No numeric columns selected for typical-day clustering")

    vectors: list[list[float]] = []
    for day_start in range(0, len(rows), 24):
        vector: list[float] = []
        for row in rows[day_start:day_start + 24]:
            for column in columns:
                vector.append(float(row[column]))
        vectors.append(vector)
    return vectors


def _scale_vectors(vectors: list[list[float]]) -> list[list[float]]:
    n = len(vectors)
    width = len(vectors[0])
    means = [sum(vector[idx] for vector in vectors) / n for idx in range(width)]
    stds = []
    for idx in range(width):
        variance = sum((vector[idx] - means[idx]) ** 2 for vector in vectors) / n
        stds.append(math.sqrt(variance) or 1.0)
    return [[(value - means[idx]) / stds[idx] for idx, value in enumerate(vector)] for vector in vectors]


def _kmeans_labels(vectors: list[list[float]], n_clusters: int, max_iter: int) -> list[int]:
    if n_clusters == 1:
        return [0] * len(vectors)

    step = (len(vectors) - 1) / (n_clusters - 1)
    centers = [vectors[round(i * step)][:] for i in range(n_clusters)]
    labels = [-1] * len(vectors)
    for _ in range(max_iter):
        next_labels = [_closest_center(vector, centers) for vector in vectors]
        if next_labels == labels:
            break
        labels = next_labels
        centers = _updated_centers(vectors, labels, n_clusters)
    return labels


def _closest_center(vector: list[float], centers: list[list[float]]) -> int:
    return min(range(len(centers)), key=lambda idx: _distance(vector, centers[idx]))


def _updated_centers(vectors: list[list[float]], labels: list[int], n_clusters: int) -> list[list[float]]:
    width = len(vectors[0])
    centers = []
    for cid in range(n_clusters):
        members = [vector for vector, label in zip(vectors, labels) if label == cid]
        if not members:
            centers.append(vectors[min(cid, len(vectors) - 1)][:])
            continue
        centers.append([sum(vector[idx] for vector in members) / len(members) for idx in range(width)])
    return centers


def _labels_to_typical_rows(vectors: list[list[float]], labels: list[int], n_clusters: int) -> list[dict[str, Any]]:
    rows = []
    for cid in range(n_clusters):
        member_indices = [idx for idx, label in enumerate(labels) if label == cid]
        if not member_indices:
            continue
        medoid_idx = _cluster_medoid(vectors, member_indices)
        days = [idx + 1 for idx in member_indices]
        rows.append({
            "typicalDayId": medoid_idx + 1,
            "weight": len(days),
            "days": ",".join(str(day) for day in days),
        })
    rows.sort(key=lambda row: int(row["typicalDayId"]))
    return rows


def _cluster_medoid(vectors: list[list[float]], member_indices: list[int]) -> int:
    width = len(vectors[0])
    center = [sum(vectors[idx][col] for idx in member_indices) / len(member_indices) for col in range(width)]
    return min(member_indices, key=lambda idx: _distance(vectors[idx], center))


def _distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right))


def _write_outputs(
    output_dir: Path,
    rows: list[dict[str, Any]],
    source: str,
    description: str,
    daily_vectors: list[list[float]] | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    typical_days = output_dir / "typical_days.csv"
    report = output_dir / "typical_day_report.md"
    weights_csv = output_dir / "typical_day_weights.csv"
    with typical_days.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["typicalDayId", "weight", "days"])
        writer.writeheader()
        writer.writerows(rows)

    with weights_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["typicalDayId", "weight"])
        writer.writeheader()
        writer.writerows({"typicalDayId": row["typicalDayId"], "weight": row["weight"]} for row in rows)

    outputs: dict[str, Path] = {"typical_days": typical_days, "report": report, "weights_csv": weights_csv}
    plot_warnings = _write_visualizations(output_dir, rows, daily_vectors, outputs)

    total_weight = sum(int(row["weight"]) for row in rows)
    report_lines = [
        "# 典型日生成报告",
        "",
        f"- source: {source}",
        f"- 典型日数量: {len(rows)}",
        f"- 权重总和: {total_weight}",
        f"- 说明: {description}",
        "",
        "## 输出文件",
        "",
        f"- typical_days: `{typical_days.name}`",
        f"- typical_day_weights: `{weights_csv.name}`",
    ]
    if "weights_png" in outputs:
        report_lines.append(f"- weights_chart: `{outputs['weights_png'].name}`")
    if "representative_days_png" in outputs:
        report_lines.append(f"- representative_days_chart: `{outputs['representative_days_png'].name}`")
    if plot_warnings:
        report_lines.extend(["", "## 可视化警告", ""])
        report_lines.extend(f"- {warning}" for warning in plot_warnings)
    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return outputs


def _write_visualizations(
    output_dir: Path,
    rows: list[dict[str, Any]],
    daily_vectors: list[list[float]] | None,
    outputs: dict[str, Path],
) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        return [f"matplotlib unavailable: {exc}"]

    warnings: list[str] = []
    weights_png = output_dir / "typical_day_weights.png"
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([str(row["typicalDayId"]) for row in rows], [int(row["weight"]) for row in rows])
    ax.set_xlabel("Typical day id")
    ax.set_ylabel("Represented days")
    ax.set_title("Typical day weights")
    fig.tight_layout()
    fig.savefig(weights_png, dpi=150)
    plt.close(fig)
    outputs["weights_png"] = weights_png

    if daily_vectors:
        representative_png = output_dir / "representative_days.png"
        fig, ax = plt.subplots(figsize=(10, 4))
        for row in rows:
            day_idx = int(row["typicalDayId"]) - 1
            if 0 <= day_idx < len(daily_vectors):
                ax.plot(range(24), daily_vectors[day_idx][:24], alpha=0.75, label=str(row["typicalDayId"]))
        ax.set_xlabel("Hour")
        ax.set_ylabel("First selected variable")
        ax.set_title("Representative day profiles")
        if len(rows) <= 14:
            ax.legend(ncol=2, fontsize=8)
        fig.tight_layout()
        fig.savefig(representative_png, dpi=150)
        plt.close(fig)
        outputs["representative_days_png"] = representative_png
    else:
        warnings.append("representative day profiles require source 8760 vectors")
    return warnings


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
