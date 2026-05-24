from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any


CORE_COLUMNS = {"Solution_ID", "Economic_Cost", "Matching_Index", "method", "scenario_id", "is_feasible"}
DEFAULT_COST_THRESHOLD = 1e8


class ResultExporter:
    """Export current CCHP raw Pareto files to a standard design result package."""

    @classmethod
    def export(
        cls,
        result_dir: str | Path,
        resolved: dict[str, Any],
        cost_threshold: float = DEFAULT_COST_THRESHOLD,
        validation: Any | None = None,
    ) -> dict[str, Path]:
        result_dir = Path(result_dir)
        scenario = resolved.get("scenario", {})
        scenario_id = scenario.get("id", "scenario")
        scenario_name = scenario.get("name", scenario_id)
        currency = scenario.get("currency", "")

        pareto_rows = cls._load_pareto_rows(result_dir, scenario_id, cost_threshold)
        if not pareto_rows:
            raise FileNotFoundError(f"No Pareto_*.csv files found under {result_dir}")

        selected = cls._select_recommendations(pareto_rows)

        pareto_path = result_dir / "pareto_solutions.csv"
        long_path = result_dir / "design_summary.csv"
        wide_path = result_dir / "design_summary_wide.csv"
        xlsx_path = result_dir / "design_summary.xlsx"
        report_path = result_dir / "design_report.md"
        resolved_path = result_dir / "resolved_scenario.json"
        validation_path = result_dir / "validation_report.md"

        cls._write_pareto(pareto_path, pareto_rows)
        cls._write_wide(wide_path, selected, scenario_id)
        cls._write_long(long_path, selected, scenario_id)
        cls._write_xlsx(xlsx_path, selected, scenario_id)
        cls._write_report(report_path, selected, scenario_id, scenario_name, currency, result_dir, resolved)
        cls._write_resolved_scenario(resolved_path, resolved)
        cls._write_validation_report(validation_path, validation)

        return {
            "pareto_solutions": pareto_path,
            "design_summary": long_path,
            "design_summary_wide": wide_path,
            "design_summary_xlsx": xlsx_path,
            "design_report": report_path,
            "resolved_scenario": resolved_path,
            "validation_report": validation_path,
        }

    @staticmethod
    def _load_pareto_rows(result_dir: Path, scenario_id: str, cost_threshold: float) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for path in sorted(result_dir.glob("*/Pareto_*.csv")):
            method = path.stem.replace("Pareto_", "")
            with path.open("r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    parsed = {k: _parse_number(v) for k, v in row.items()}
                    parsed["method"] = method
                    parsed["scenario_id"] = scenario_id
                    parsed["is_feasible"] = float(parsed.get("Economic_Cost", math.inf)) <= cost_threshold
                    rows.append(parsed)
        return rows

    @staticmethod
    def _select_recommendations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [row for row in rows if row.get("is_feasible")]
        if not candidates:
            candidates = rows

        selected_specs = [
            ("min_cost", min(candidates, key=lambda row: float(row.get("Economic_Cost", math.inf)))),
            ("min_matching", min(candidates, key=lambda row: float(row.get("Matching_Index", math.inf)))),
            ("knee_point", _knee_point(candidates)),
        ]

        selected: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for label, row in selected_specs:
            key = (label, str(row.get("method")), str(row.get("Solution_ID")))
            if key in seen:
                continue
            item = dict(row)
            item["solution_label"] = label
            selected.append(item)
            seen.add(key)
        return selected

    @staticmethod
    def _write_pareto(path: Path, rows: list[dict[str, Any]]) -> None:
        columns = _ordered_columns(rows)
        _write_dict_rows(path, columns, rows)

    @staticmethod
    def _write_wide(path: Path, rows: list[dict[str, Any]], scenario_id: str) -> None:
        columns = ["scenario_id", "solution_label", "method", "Solution_ID", "Economic_Cost", "Matching_Index"]
        device_columns = sorted({key for row in rows for key in row if key not in CORE_COLUMNS and key != "solution_label"})
        output_rows = []
        for row in rows:
            out = {column: row.get(column, "") for column in columns}
            out["scenario_id"] = scenario_id
            for column in device_columns:
                out[column] = row.get(column, "")
            output_rows.append(out)
        _write_dict_rows(path, columns + device_columns, output_rows)

    @staticmethod
    def _write_long(path: Path, rows: list[dict[str, Any]], scenario_id: str) -> None:
        columns = ["scenario_id", "solution_label", "method", "source_solution_id", "item_type", "item_id", "value", "unit"]
        output_rows = []
        for row in rows:
            common = {
                "scenario_id": scenario_id,
                "solution_label": row.get("solution_label", ""),
                "method": row.get("method", ""),
                "source_solution_id": row.get("Solution_ID", ""),
            }
            output_rows.append({**common, "item_type": "objective", "item_id": "economic_cost", "value": row.get("Economic_Cost", ""), "unit": "currency_per_year"})
            output_rows.append({**common, "item_type": "objective", "item_id": "matching_index", "value": row.get("Matching_Index", ""), "unit": "index"})
            for key in sorted(row):
                if key in CORE_COLUMNS or key == "solution_label":
                    continue
                output_rows.append({**common, "item_type": "device_capacity", "item_id": key, "value": row.get(key, ""), "unit": "kW"})
        _write_dict_rows(path, columns, output_rows)

    @staticmethod
    def _write_report(
        path: Path,
        rows: list[dict[str, Any]],
        scenario_id: str,
        scenario_name: str,
        currency: str,
        result_dir: Path,
        resolved: dict[str, Any],
    ) -> None:
        system = resolved.get("system", {})
        carriers = resolved.get("energy_carriers", {})
        data = resolved.get("data", {})
        optimization = resolved.get("optimization", {})
        lines = [
            "# 场景化系统设计结果报告",
            "",
            f"- 场景 ID: `{scenario_id}`",
            f"- 场景名称: {scenario_name}",
            f"- 结果目录: `{result_dir}`",
            f"- 货币: {currency or '未声明'}",
            "",
            "## 输入数据",
            "",
            f"- 负荷数据文件: `{data.get('load_file', '')}`",
            f"- 典型日文件: `{data.get('typical_day_file') or resolved.get('typical_day', {}).get('file', '')}`",
            f"- 数据类型: {data.get('input_type', '未声明')}",
            "",
            "## 系统结构",
            "",
            f"- 系统模板: `{system.get('template', '')}`",
            f"- 用户负荷: {', '.join(carriers.get('demands', [])) or '未声明'}",
            f"- 能源输入: {', '.join(carriers.get('inputs', [])) or '未声明'}",
            f"- 资源/环境: {', '.join(carriers.get('resources', [])) or '未声明'}",
            "",
            "## 优化设置",
            "",
            f"- 模式: {optimization.get('mode', '')}",
            f"- 方法: {optimization.get('methods', [])}",
            f"- 种群规模 nind: {optimization.get('nind', '')}",
            f"- 最大代数 maxgen: {optimization.get('maxgen', '')}",
            "",
            "## 推荐配置",
            "",
            "| 推荐类型 | 方法 | 原方案ID | 年化成本 | 匹配度 |",
            "|---|---|---:|---:|---:|",
        ]
        for row in rows:
            lines.append(
                "| {label} | {method} | {sid} | {cost:.2f} | {matching:.4f} |".format(
                    label=row.get("solution_label", ""),
                    method=row.get("method", ""),
                    sid=row.get("Solution_ID", ""),
                    cost=float(row.get("Economic_Cost", 0) or 0),
                    matching=float(row.get("Matching_Index", 0) or 0),
                )
            )
        lines.extend(
            [
                "",
                "## 输出文件",
                "",
                "- `pareto_solutions.csv`: 汇总现有优化器输出的所有 Pareto 解，并标记是否超过成本阈值。",
                "- `design_summary.csv`: 推荐方案长表，适配后续多能源载体和设备扩展。",
                "- `design_summary_wide.csv`: 推荐方案宽表，便于人工查看和 Excel 展示。",
                "- `design_summary.xlsx`: Excel 展示版推荐方案表。",
                "- `resolved_scenario.json`: 本次运行实际使用的完整场景配置。",
                "- `validation_report.md`: 输入校验报告。",
            ]
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _write_xlsx(path: Path, rows: list[dict[str, Any]], scenario_id: str) -> None:
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Excel result export requires openpyxl. Use `uv run python ...`.") from exc

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "design_summary"
        columns = ["scenario_id", "solution_label", "method", "Solution_ID", "Economic_Cost", "Matching_Index"]
        device_columns = sorted({key for row in rows for key in row if key not in CORE_COLUMNS and key != "solution_label"})
        headers = columns + device_columns
        ws.append(headers)
        for row in rows:
            ws.append([scenario_id if column == "scenario_id" else row.get(column, "") for column in headers])
        for cell in ws[1]:
            cell.font = openpyxl.styles.Font(bold=True)
        ws.freeze_panes = "A2"
        for column_cells in ws.columns:
            width = max(len(str(cell.value or "")) for cell in column_cells) + 2
            ws.column_dimensions[column_cells[0].column_letter].width = min(width, 28)
        wb.save(path)

    @staticmethod
    def _write_resolved_scenario(path: Path, resolved: dict[str, Any]) -> None:
        path.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _write_validation_report(path: Path, validation: Any | None) -> None:
        lines = ["# 场景输入校验报告", ""]
        if validation is None:
            lines.extend(["未传入校验结果。", ""])
        else:
            ok = getattr(validation, "ok", False)
            errors = list(getattr(validation, "errors", []) or [])
            warnings = list(getattr(validation, "warnings", []) or [])
            lines.extend([f"- 状态: {'通过' if ok else '未通过'}", f"- 错误数: {len(errors)}", f"- 警告数: {len(warnings)}", ""])
            if errors:
                lines.extend(["## 错误", ""])
                lines.extend([f"- {item}" for item in errors])
                lines.append("")
            if warnings:
                lines.extend(["## 警告", ""])
                lines.extend([f"- {item}" for item in warnings])
                lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


def _parse_number(value: Any) -> Any:
    if value is None:
        return ""
    text = str(value).strip()
    if text == "":
        return ""
    try:
        number = float(text)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
    preferred = ["scenario_id", "method", "is_feasible", "Solution_ID", "Economic_Cost", "Matching_Index"]
    rest = sorted({key for row in rows for key in row if key not in preferred})
    return preferred + rest


def _write_dict_rows(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _knee_point(rows: list[dict[str, Any]]) -> dict[str, Any]:
    min_cost = min(float(row.get("Economic_Cost", math.inf)) for row in rows)
    max_cost = max(float(row.get("Economic_Cost", -math.inf)) for row in rows)
    min_match = min(float(row.get("Matching_Index", math.inf)) for row in rows)
    max_match = max(float(row.get("Matching_Index", -math.inf)) for row in rows)
    cost_range = max(max_cost - min_cost, 1e-12)
    match_range = max(max_match - min_match, 1e-12)

    def score(row: dict[str, Any]) -> float:
        cost_norm = (float(row.get("Economic_Cost", math.inf)) - min_cost) / cost_range
        match_norm = (float(row.get("Matching_Index", math.inf)) - min_match) / match_range
        return math.sqrt(cost_norm * cost_norm + match_norm * match_norm)

    return min(rows, key=score)
