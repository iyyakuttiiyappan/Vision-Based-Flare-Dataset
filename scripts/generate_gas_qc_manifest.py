from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DATASET_ROOT = Path(
    r"C:\Users\ADMIN\Documents\IYYAKUTTI\FlareAnalysis\FlareScientificData_2026-05-15_preprocessed"
)
MANIFEST_PATH = DATASET_ROOT / "metadata" / "dataset_manifest.csv"
QC_MANIFEST_PATH = DATASET_ROOT / "metadata" / "dataset_manifest_qc.csv"
QC_REPORT_PATH = DATASET_ROOT / "metadata" / "gas_qc_report.json"
QC_SUMMARY_PATH = DATASET_ROOT / "metadata" / "gas_qc_summary.csv"


TARGET_RULES = {
    "gas_stack_temp_c": (30.0, 1000.0),
    "gas_oxygen_percent": (0.0, 23.0),
    "gas_carbon_monoxide_ppm": (0.0, 50_000.0),
    "gas_carbon_dioxide_percent": (0.0, 15.0),
}


def as_float(row: dict[str, str], column: str) -> float | None:
    value = row.get(column, "")
    if value == "":
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def add_reason(reasons: list[str], condition: bool, reason: str) -> None:
    if condition:
        reasons.append(reason)


def qc_row(row: dict[str, str]) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []

    ambient = as_float(row, "gas_ambient_temp_c")
    stack = as_float(row, "gas_stack_temp_c")
    oxygen = as_float(row, "gas_oxygen_percent")
    carbon_monoxide = as_float(row, "gas_carbon_monoxide_ppm")
    carbon_dioxide = as_float(row, "gas_carbon_dioxide_percent")
    stack_draft = as_float(row, "gas_stack_draft_inwc")
    excess_air = as_float(row, "gas_excess_air_percent")

    for column, (lower, upper) in TARGET_RULES.items():
        value = as_float(row, column)
        short_name = column.removeprefix("gas_")
        if value is None:
            reasons.append(f"{short_name}_missing")
        elif not lower <= value <= upper:
            reasons.append(f"{short_name}_outside_{lower:g}_{upper:g}")

    add_reason(warnings, ambient is None, "ambient_temp_missing")
    add_reason(
        warnings,
        ambient is not None and not 0.0 <= ambient <= 80.0,
        "ambient_temp_outside_0_80",
    )
    add_reason(
        warnings,
        excess_air is not None and excess_air > 5000.0,
        "excess_air_gt_5000",
    )

    add_reason(
        reasons,
        stack_draft is not None and abs(stack_draft) > 100.0,
        "stack_draft_abs_gt_100_column_shift",
    )
    add_reason(
        reasons,
        oxygen is not None and carbon_dioxide is not None and oxygen + carbon_dioxide > 23.0,
        "oxygen_plus_co2_gt_23",
    )
    add_reason(
        reasons,
        stack is not None and oxygen is not None and stack == oxygen and stack <= 80.0,
        "stack_temp_equals_oxygen_small",
    )
    add_reason(
        reasons,
        (
            oxygen is not None
            and carbon_monoxide is not None
            and carbon_dioxide is not None
            and oxygen == carbon_monoxide == carbon_dioxide
            and oxygen > 0.0
        ),
        "oxygen_co_co2_identical_nonzero",
    )
    add_reason(
        reasons,
        (
            oxygen is not None
            and carbon_monoxide is not None
            and carbon_dioxide is not None
            and carbon_monoxide == carbon_dioxide
            and 0.0 < carbon_dioxide <= 25.0
            and oxygen == carbon_dioxide
        ),
        "co_ppm_equals_co2_percent_and_oxygen",
    )

    unique_reasons = sorted(set(reasons))
    unique_warnings = sorted(set(warnings))
    flag = "reject" if unique_reasons else "ok"
    return flag, unique_reasons, unique_warnings


def read_manifest() -> tuple[list[dict[str, str]], list[str]]:
    with MANIFEST_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return rows, fieldnames


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    flag_counts = Counter(row["gas_qc_flag"] for row in rows)
    reason_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    by_fuel = defaultdict(Counter)
    by_run = defaultdict(Counter)
    repeated_gas_groups: Counter[tuple[str, str]] = Counter()

    for row in rows:
        flag = row["gas_qc_flag"]
        fuel = row.get("fuel", "")
        set_id = row.get("set_id", "")
        by_fuel[fuel][flag] += 1
        by_run[f"{fuel}/{set_id}"][flag] += 1
        if row.get("gas_timestamp"):
            repeated_gas_groups[(fuel, row["gas_timestamp"])] += 1
        for reason in row["gas_qc_reasons"].split(";"):
            if reason:
                reason_counts[reason] += 1
        for warning in row["gas_qc_warnings"].split(";"):
            if warning:
                warning_counts[warning] += 1

    repeated_counts = Counter(repeated_gas_groups.values())
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_manifest": str(MANIFEST_PATH),
        "output_manifest": str(QC_MANIFEST_PATH),
        "rules": {
            "target_ranges": TARGET_RULES,
            "reject_patterns": [
                "stack draft absolute value > 100 inWC, suggesting column shift",
                "oxygen + carbon dioxide > 23 percent",
                "small stack temperature numerically equal to oxygen",
                "oxygen, CO, and CO2 exactly identical and non-zero",
                "CO ppm equals CO2 percent and oxygen exactly",
            ],
            "warnings": [
                "ambient temperature missing or outside 0-80 C",
                "excess air > 5000 percent",
            ],
        },
        "row_counts": dict(flag_counts),
        "reason_counts": dict(reason_counts.most_common()),
        "warning_counts": dict(warning_counts.most_common()),
        "by_fuel": {key: dict(value) for key, value in sorted(by_fuel.items())},
        "by_run": {key: dict(value) for key, value in sorted(by_run.items())},
        "repeated_gas_timestamp_distribution": {
            str(key): value for key, value in sorted(repeated_counts.items())
        },
        "repeated_gas_timestamp_groups": sum(
            1 for count in repeated_gas_groups.values() if count > 1
        ),
        "samples_on_repeated_gas_timestamps": sum(
            count for count in repeated_gas_groups.values() if count > 1
        ),
    }


def main() -> None:
    rows, fieldnames = read_manifest()
    qc_fieldnames = [
        "gas_qc_flag",
        "gas_qc_reasons",
        "gas_qc_warnings",
        "gas_qc_version",
    ]
    output_rows: list[dict[str, str]] = []
    for row in rows:
        flag, reasons, warnings = qc_row(row)
        out = dict(row)
        out["gas_qc_flag"] = flag
        out["gas_qc_reasons"] = ";".join(reasons)
        out["gas_qc_warnings"] = ";".join(warnings)
        out["gas_qc_version"] = "gas-qc-v1"
        output_rows.append(out)

    write_csv(QC_MANIFEST_PATH, output_rows, fieldnames + qc_fieldnames)
    report = summarize(output_rows)
    QC_REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    summary_rows: list[dict[str, Any]] = []
    for flag, count in sorted(report["row_counts"].items()):
        summary_rows.append({"section": "flag", "name": flag, "count": count})
    for reason, count in report["reason_counts"].items():
        summary_rows.append({"section": "reject_reason", "name": reason, "count": count})
    for warning, count in report["warning_counts"].items():
        summary_rows.append({"section": "warning", "name": warning, "count": count})
    for run, counts in report["by_run"].items():
        for flag, count in counts.items():
            summary_rows.append({"section": "run", "name": f"{run}:{flag}", "count": count})
    write_csv(QC_SUMMARY_PATH, summary_rows, ["section", "name", "count"])

    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
