from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

try:
    import cv2
except ImportError as exc:  # pragma: no cover - reported clearly at runtime
    raise SystemExit(
        "OpenCV is required to extract thermal frames. Install with: "
        "python -m pip install opencv-python-headless"
    ) from exc


RAW_ROOT_DEFAULT = Path(
    r"C:\Users\ADMIN\Documents\IYYAKUTTI\FlareAnalysis\[15_05_2026]_dataCollection"
)
OUTPUT_ROOT_DEFAULT = Path(
    r"C:\Users\ADMIN\Documents\IYYAKUTTI\FlareAnalysis\FlareScientificData_2026-05-15_preprocessed"
)

IMAGE_RE = re.compile(r"^(?P<seq>\d+)_(?P<tick>[0-9A-Fa-f]+)\.png$")
APP_TIME_RE = re.compile(
    r"Application\s+(?P<app>\d+):\s+"
    r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
)
GAS_ROW_RE = re.compile(r"^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}$")

GAS_FIELDS = [
    ("efficiency_percent", "Efficiency (%)"),
    ("ambient_temp_c", "Ambient Temp"),
    ("stack_temp_c", "Stack Temp"),
    ("oxygen_percent", "Oxygen (%)"),
    ("carbon_monoxide_ppm", "Carbon Monoxide"),
    ("carbon_dioxide_percent", "Carbon Dioxide (%)"),
    ("stack_draft_inwc", "Stack Draft (inWC)"),
    ("excess_air_percent", "Excess Air (%)"),
    ("nitric_oxide_ppm", "Nitric Oxide"),
    ("nitrogen_dioxide_ppm", "Nitrogen Dioxide"),
    ("oxides_of_nitrogen_ppm", "Oxides of Nitrogen"),
]


@dataclass(frozen=True)
class ImageRecord:
    source_path: Path
    sequence: int
    tick_ms: int


@dataclass
class RunRecord:
    fuel: str
    set_name: str
    set_number: int
    run_dir: Path
    rgb_dir: Path
    ir_dir: Path
    thermal_video: Path
    app1_start: datetime
    app1_stop: datetime
    app3_start: datetime
    app3_stop: datetime
    flow_setting: str | None
    start_times_file: Path
    stop_times_file: Path
    rgb_count: int
    ir_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize flare RGB, IR, thermal video, and gas analyser data."
    )
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT_DEFAULT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT_DEFAULT)
    parser.add_argument(
        "--link-mode",
        choices=["hardlink", "copy"],
        default="hardlink",
        help="How to place RGB/IR images in the curated dataset.",
    )
    parser.add_argument(
        "--max-gas-delta-seconds",
        type=float,
        default=2.0,
        help="Expected maximum distance to nearest gas analyser row. Larger deltas are flagged.",
    )
    return parser.parse_args()


def parse_datetime(value: str, fmt: str = "%Y-%m-%d %H:%M:%S.%f") -> datetime:
    if "." not in value:
        fmt = "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(value, fmt)


def read_app_times(path: Path) -> dict[int, datetime]:
    times: dict[int, datetime] = {}
    for line in path.read_text(errors="replace").splitlines():
        match = APP_TIME_RE.search(line)
        if match:
            times[int(match.group("app"))] = parse_datetime(match.group("ts"))
    return times


def sorted_set_dirs(fuel_dir: Path) -> list[Path]:
    def set_number(path: Path) -> int:
        match = re.search(r"(\d+)", path.name)
        return int(match.group(1)) if match else 10_000

    return sorted((p for p in fuel_dir.iterdir() if p.is_dir()), key=set_number)


def count_files(path: Path, suffix: str | None = None) -> int:
    if not path.exists():
        return 0
    if suffix is None:
        return sum(1 for p in path.iterdir() if p.is_file())
    return sum(1 for p in path.iterdir() if p.is_file() and p.suffix.lower() == suffix)


def discover_runs(raw_root: Path) -> tuple[list[RunRecord], list[dict[str, Any]]]:
    runs: list[RunRecord] = []
    excluded: list[dict[str, Any]] = []

    for fuel_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        fuel = fuel_dir.name.lower()
        for set_dir in sorted_set_dirs(fuel_dir):
            set_match = re.search(r"(\d+)", set_dir.name)
            set_number = int(set_match.group(1)) if set_match else 0
            rgb_dir = set_dir / "RGB"
            ir_dir = set_dir / "IR"
            thermal_dir = set_dir / "Thermal"
            videos = sorted(
                p
                for p in thermal_dir.glob("*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"}
            )
            starts = sorted(set_dir.glob("start_times_*.txt"))
            stops = sorted(set_dir.glob("stop_times_*.txt"))
            rgb_count = count_files(rgb_dir, ".png")
            ir_count = count_files(ir_dir, ".png")

            missing = []
            if rgb_count == 0:
                missing.append("RGB images")
            if ir_count == 0:
                missing.append("IR images")
            if len(videos) != 1:
                missing.append(f"thermal video count={len(videos)}")
            if len(starts) != 1:
                missing.append(f"start_times files={len(starts)}")
            if len(stops) != 1:
                missing.append(f"stop_times files={len(stops)}")

            if missing:
                excluded.append(
                    {
                        "fuel": fuel,
                        "set_id": set_dir.name,
                        "rgb_images": rgb_count,
                        "ir_images": ir_count,
                        "thermal_videos": len(videos),
                        "reason": "; ".join(missing),
                    }
                )
                continue

            start_times = read_app_times(starts[0])
            stop_times = read_app_times(stops[0])
            if not {1, 3}.issubset(start_times) or not {1, 3}.issubset(stop_times):
                excluded.append(
                    {
                        "fuel": fuel,
                        "set_id": set_dir.name,
                        "rgb_images": rgb_count,
                        "ir_images": ir_count,
                        "thermal_videos": len(videos),
                        "reason": "missing Application 1 or Application 3 times",
                    }
                )
                continue

            flow_file = set_dir / "flow.txt"
            flow_setting = None
            if flow_file.exists():
                flow_setting = flow_file.read_text(errors="replace").strip() or None

            runs.append(
                RunRecord(
                    fuel=fuel,
                    set_name=set_dir.name,
                    set_number=set_number,
                    run_dir=set_dir,
                    rgb_dir=rgb_dir,
                    ir_dir=ir_dir,
                    thermal_video=videos[0],
                    app1_start=start_times[1],
                    app1_stop=stop_times[1],
                    app3_start=start_times[3],
                    app3_stop=stop_times[3],
                    flow_setting=flow_setting,
                    start_times_file=starts[0],
                    stop_times_file=stops[0],
                    rgb_count=rgb_count,
                    ir_count=ir_count,
                )
            )

    return runs, excluded


def read_images(path: Path) -> list[ImageRecord]:
    records: list[ImageRecord] = []
    for file_path in path.glob("*.png"):
        match = IMAGE_RE.match(file_path.name)
        if not match:
            continue
        records.append(
            ImageRecord(
                source_path=file_path,
                sequence=int(match.group("seq")),
                tick_ms=int(match.group("tick"), 16),
            )
        )
    return sorted(records, key=lambda item: (item.tick_ms, item.sequence))


def median_tick_interval_ms(records: list[ImageRecord]) -> float | None:
    diffs = [
        records[idx].tick_ms - records[idx - 1].tick_ms
        for idx in range(1, len(records))
        if records[idx].tick_ms > records[idx - 1].tick_ms
    ]
    return float(median(diffs)) if diffs else None


def pair_rgb_ir(
    rgb_records: list[ImageRecord],
    ir_records: list[ImageRecord],
) -> tuple[list[tuple[ImageRecord, ImageRecord, int]], int, int, float]:
    rgb_interval = median_tick_interval_ms(rgb_records)
    ir_interval = median_tick_interval_ms(ir_records)
    intervals = [x for x in [rgb_interval, ir_interval] if x is not None]
    typical_interval = min(intervals) if intervals else 1000.0
    threshold_ms = max(500.0, min(1000.0, typical_interval * 0.75))

    ir_ticks = [record.tick_ms for record in ir_records]
    used_ir: set[int] = set()
    pairs: list[tuple[ImageRecord, ImageRecord, int]] = []

    for rgb in rgb_records:
        insertion = bisect.bisect_left(ir_ticks, rgb.tick_ms)
        candidate_indices = range(max(0, insertion - 3), min(len(ir_records), insertion + 4))
        best: tuple[int, int] | None = None
        for ir_index in candidate_indices:
            if ir_index in used_ir:
                continue
            delta_ms = abs(rgb.tick_ms - ir_records[ir_index].tick_ms)
            if best is None or delta_ms < best[0]:
                best = (delta_ms, ir_index)
        if best is not None and best[0] <= threshold_ms:
            used_ir.add(best[1])
            pairs.append((rgb, ir_records[best[1]], rgb.tick_ms - ir_records[best[1]].tick_ms))

    unmatched_rgb = len(rgb_records) - len(pairs)
    unmatched_ir = len(ir_records) - len(used_ir)
    return pairs, unmatched_rgb, unmatched_ir, threshold_ms


def parse_numeric(raw_value: str) -> float | None:
    value = raw_value.strip()
    if not value:
        return None
    if value.upper() in {"N.A.", "NA", "N/A", "OVER"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_gas_log(path: Path, fuel: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current_header = ""
    for line_number, raw_line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        line = raw_line.rstrip("\t")
        if not line:
            continue
        parts = line.split("\t")
        if parts[0] == "ENERAC 700-EMS":
            continue
        if parts[0] == "Current/Time":
            current_header = " | ".join(parts)
            continue
        if not parts or not GAS_ROW_RE.match(parts[0]):
            continue
        if len(parts) < 12:
            parts.extend([""] * (12 - len(parts)))
        elif len(parts) > 12:
            parts = parts[:12]

        timestamp = datetime.strptime(parts[0], "%m/%d/%y %H:%M:%S")
        row: dict[str, Any] = {
            "fuel": fuel,
            "gas_timestamp": timestamp,
            "gas_timestamp_iso": timestamp.isoformat(sep=" "),
            "source_line": line_number,
            "source_header": current_header,
        }
        for index, (field_name, _label) in enumerate(GAS_FIELDS, start=1):
            raw_value = parts[index].strip()
            row[f"raw_{field_name}"] = raw_value
            row[field_name] = parse_numeric(raw_value)
        rows.append(row)

    rows.sort(key=lambda row: row["gas_timestamp"])
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def link_or_copy(source: Path, destination: Path, mode: str) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.stat().st_size == source.stat().st_size:
            return "existing"
        destination.unlink()
    if mode == "copy":
        shutil.copy2(source, destination)
        return "copy"
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy_fallback"


def relative_to_output(path: Path, output_root: Path) -> str:
    return path.relative_to(output_root).as_posix()


def nearest_gas_row(
    timestamp: datetime,
    rows: list[dict[str, Any]],
    timestamps: list[datetime],
) -> tuple[dict[str, Any] | None, float | None]:
    if not rows:
        return None, None
    insertion = bisect.bisect_left(timestamps, timestamp)
    candidates = []
    if insertion < len(rows):
        candidates.append(insertion)
    if insertion > 0:
        candidates.append(insertion - 1)
    best_index = min(
        candidates,
        key=lambda index: abs((timestamps[index] - timestamp).total_seconds()),
    )
    delta = (timestamps[best_index] - timestamp).total_seconds()
    return rows[best_index], delta


def open_video(video_path: Path) -> tuple[Any, float, int, int, int]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open thermal video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or frame_count <= 0:
        capture.release()
        raise RuntimeError(f"Could not read FPS/frame count from: {video_path}")
    return capture, fps, frame_count, width, height


def extract_frames_sequential(
    video_path: Path,
    index_to_destinations: dict[int, list[Path]],
) -> dict[int, dict[str, Any]]:
    capture, fps, frame_count, width, height = open_video(video_path)
    extracted: dict[int, dict[str, Any]] = {}
    target_indices = sorted(index_to_destinations)
    target_pos = 0
    current_index = 0

    try:
        while target_pos < len(target_indices):
            target_index = target_indices[target_pos]
            if target_index < 0 or target_index >= frame_count:
                extracted[target_index] = {
                    "ok": False,
                    "reason": "frame index outside video",
                    "fps": fps,
                    "frame_count": frame_count,
                    "width": width,
                    "height": height,
                }
                target_pos += 1
                continue
            if current_index < target_index:
                capture.grab()
                current_index += 1
                continue

            ok, frame = capture.read()
            if not ok:
                extracted[target_index] = {
                    "ok": False,
                    "reason": "cv2 read failed",
                    "fps": fps,
                    "frame_count": frame_count,
                    "width": width,
                    "height": height,
                }
            else:
                for destination in index_to_destinations[target_index]:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    write_ok = cv2.imwrite(str(destination), frame)
                    if not write_ok:
                        raise RuntimeError(f"Could not write thermal frame: {destination}")
                extracted[target_index] = {
                    "ok": True,
                    "fps": fps,
                    "frame_count": frame_count,
                    "width": width,
                    "height": height,
                }
            current_index += 1
            target_pos += 1
    finally:
        capture.release()

    return extracted


def gas_fieldnames() -> list[str]:
    names = []
    for field_name, _label in GAS_FIELDS:
        names.append(f"gas_raw_{field_name}")
        names.append(f"gas_{field_name}")
    return names


def build_schema() -> dict[str, Any]:
    return {
        "dataset": "FlareScientificData_2026-05-15_preprocessed",
        "time_zone": "local laboratory computer time, as recorded in source files",
        "modalities": {
            "rgb": "PNG images from Application 3",
            "ir": "PNG images from Application 3",
            "thermal": "PNG frames extracted from Application 1 video",
            "gas_analyser": "ENERAC 700-EMS rows matched by nearest timestamp",
        },
        "synchronization": {
            "rgb_ir_pairing": "Each RGB image is paired to the nearest unused IR image by hexadecimal camera tick.",
            "rgb_ir_timestamp": "Application 3 start time plus camera tick offset from the first observed RGB/IR tick in that run.",
            "thermal_frame": "Nearest video frame index from Application 1 start time and OpenCV-reported FPS.",
            "gas_row": "Nearest gas analyser row by wall-clock timestamp.",
        },
        "columns": {
            "dataset_manifest.csv": {
                "sample_id": "Unique synchronized sample id.",
                "fuel": "Fuel folder name from source data.",
                "set_id": "Source set folder.",
                "flow_setting": "Value from flow.txt when present.",
                "sync_timestamp": "Mean timestamp of paired RGB and IR camera ticks.",
                "rgb_path": "Curated relative RGB path.",
                "ir_path": "Curated relative IR path.",
                "thermal_path": "Curated relative thermal PNG frame path.",
                "gas_*": "Matched gas analyser raw and numeric fields.",
            }
        },
    }


def write_readme(
    output_root: Path,
    total_samples: int,
    usable_runs: int,
    excluded_count: int,
    skipped_samples: int,
) -> None:
    readme = f"""# FlareScientificData 2026-05-15 Preprocessed

This folder contains synchronized flare stack observations from the 2026-05-15 laboratory collection.

## Contents

- `data/`: Curated synchronized RGB, IR, and thermal PNG images, organized by fuel and set.
- `metadata/dataset_manifest.csv`: One row per synchronized sample, including image paths and nearest gas analyser values.
- `metadata/runs.csv`: Run-level timing, counts, FPS, and pairing statistics.
- `metadata/excluded_sets.csv`: Empty or incomplete source sets that were not included.
- `gas_analyser/*_clean.csv`: Parsed ENERAC 700-EMS logs with raw strings and numeric fields.
- `scripts/preprocess_flare_dataset.py`: Reproducible preprocessing script used to create this folder.
- `scripts/requirements_flare_preprocessing.txt`: Python dependency needed for thermal video extraction.

## Summary

- Usable runs: {usable_runs}
- Complete synchronized samples: {total_samples}
- Skipped RGB/IR edge pairs outside thermal video windows: {skipped_samples}
- Excluded empty/incomplete sets: {excluded_count}

## Synchronization Notes

RGB and IR image filenames contain a hexadecimal camera tick. For each run, RGB images were used as anchors and paired with the nearest unused IR image. The paired timestamp is the mean of the RGB and IR tick-derived timestamps. Thermal frames were extracted from the corresponding MP4 using the Application 1 start time and the FPS reported by OpenCV. Gas analyser values were attached from the nearest ENERAC timestamp. The main manifest includes only rows with all three visual modalities available.

The gas logs contain repeated ENERAC headers and status strings such as `OVER` and `N.A.`. The clean gas CSVs and manifest preserve raw values in `gas_raw_*` columns and provide numeric values in `gas_*` columns where conversion was possible.
"""
    (output_root / "README.md").write_text(readme, encoding="utf-8")


def process_dataset(
    raw_root: Path,
    output_root: Path,
    link_mode: str,
    max_gas_delta_seconds: float,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "metadata").mkdir(exist_ok=True)
    (output_root / "gas_analyser").mkdir(exist_ok=True)
    (output_root / "scripts").mkdir(exist_ok=True)

    runs, excluded = discover_runs(raw_root)

    gas_logs: dict[str, list[dict[str, Any]]] = {
        "methane": parse_gas_log(raw_root / "Data_methane.Txt", "methane"),
        "propene": parse_gas_log(raw_root / "Data_propene.Txt", "propene"),
    }
    gas_times = {
        fuel: [row["gas_timestamp"] for row in rows] for fuel, rows in gas_logs.items()
    }

    clean_gas_fieldnames = [
        "fuel",
        "gas_timestamp_iso",
        "source_line",
        "source_header",
    ]
    for field_name, _label in GAS_FIELDS:
        clean_gas_fieldnames.extend([f"raw_{field_name}", field_name])

    for fuel, rows in gas_logs.items():
        write_csv(output_root / "gas_analyser" / f"{fuel}_gas_clean.csv", rows, clean_gas_fieldnames)

    all_manifest_rows: list[dict[str, Any]] = []
    skipped_sample_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    link_counts: dict[str, int] = {}

    for run in runs:
        rgb_records = read_images(run.rgb_dir)
        ir_records = read_images(run.ir_dir)
        pairs, unmatched_rgb, unmatched_ir, rgb_ir_threshold_ms = pair_rgb_ir(
            rgb_records, ir_records
        )
        base_tick_ms = min(
            min(record.tick_ms for record in rgb_records),
            min(record.tick_ms for record in ir_records),
        )

        capture, fps, frame_count, video_width, video_height = open_video(run.thermal_video)
        capture.release()

        run_key = f"{run.fuel}_set{run.set_number:03d}"
        run_output = output_root / "data" / run.fuel / f"set-{run.set_number:03d}"
        rgb_output = run_output / "rgb"
        ir_output = run_output / "ir"
        thermal_output = run_output / "thermal"

        pending_rows: list[dict[str, Any]] = []
        frame_destinations: dict[int, list[Path]] = {}
        skipped_outside_thermal_window = 0

        for pair_index, (rgb, ir, rgb_ir_delta_ms) in enumerate(pairs):
            rgb_ts = run.app3_start + timedelta(milliseconds=rgb.tick_ms - base_tick_ms)
            ir_ts = run.app3_start + timedelta(milliseconds=ir.tick_ms - base_tick_ms)
            sync_ts = run.app3_start + timedelta(
                milliseconds=((rgb.tick_ms + ir.tick_ms) / 2.0) - base_tick_ms
            )
            thermal_delta_s = (sync_ts - run.app1_start).total_seconds()
            thermal_frame_index = int(round(thermal_delta_s * fps))
            thermal_ts = run.app1_start + timedelta(seconds=thermal_frame_index / fps)
            thermal_time_delta_ms = (thermal_ts - sync_ts).total_seconds() * 1000.0

            if not 0 <= thermal_frame_index < frame_count:
                skipped_outside_thermal_window += 1
                skipped_sample_rows.append(
                    {
                        "fuel": run.fuel,
                        "set_id": f"set-{run.set_number:03d}",
                        "source_set_id": run.set_name,
                        "candidate_pair_index": pair_index,
                        "reason": "thermal frame outside video window",
                        "sync_timestamp": sync_ts.isoformat(sep=" ", timespec="microseconds"),
                        "thermal_frame_index": thermal_frame_index,
                        "thermal_video_frame_count": frame_count,
                        "rgb_sequence": rgb.sequence,
                        "ir_sequence": ir.sequence,
                        "rgb_tick_ms": rgb.tick_ms,
                        "ir_tick_ms": ir.tick_ms,
                        "source_rgb_path": str(rgb.source_path),
                        "source_ir_path": str(ir.source_path),
                        "source_thermal_video": str(run.thermal_video),
                    }
                )
                continue

            sample_index = len(pending_rows)
            sample_id = f"flare_20260515_{run.fuel}_set{run.set_number:03d}_{sample_index:06d}"
            rgb_dest = rgb_output / f"{sample_id}_rgb.png"
            ir_dest = ir_output / f"{sample_id}_ir.png"
            thermal_dest = thermal_output / f"{sample_id}_thermal.png"

            link_result = link_or_copy(rgb.source_path, rgb_dest, link_mode)
            link_counts[link_result] = link_counts.get(link_result, 0) + 1
            link_result = link_or_copy(ir.source_path, ir_dest, link_mode)
            link_counts[link_result] = link_counts.get(link_result, 0) + 1

            frame_destinations.setdefault(thermal_frame_index, []).append(thermal_dest)

            gas_row, gas_delta_s = nearest_gas_row(
                sync_ts, gas_logs.get(run.fuel, []), gas_times.get(run.fuel, [])
            )

            manifest_row: dict[str, Any] = {
                "sample_id": sample_id,
                "fuel": run.fuel,
                "set_id": f"set-{run.set_number:03d}",
                "source_set_id": run.set_name,
                "candidate_pair_index": pair_index,
                "flow_setting": run.flow_setting,
                "sync_timestamp": sync_ts.isoformat(sep=" ", timespec="microseconds"),
                "rgb_timestamp": rgb_ts.isoformat(sep=" ", timespec="microseconds"),
                "ir_timestamp": ir_ts.isoformat(sep=" ", timespec="microseconds"),
                "thermal_timestamp": thermal_ts.isoformat(sep=" ", timespec="microseconds"),
                "rgb_ir_delta_ms": rgb_ir_delta_ms,
                "thermal_time_delta_ms": round(thermal_time_delta_ms, 3),
                "thermal_frame_index": thermal_frame_index,
                "thermal_fps": round(fps, 6),
                "rgb_sequence": rgb.sequence,
                "ir_sequence": ir.sequence,
                "rgb_tick_ms": rgb.tick_ms,
                "ir_tick_ms": ir.tick_ms,
                "rgb_path": relative_to_output(rgb_dest, output_root),
                "ir_path": relative_to_output(ir_dest, output_root),
                "thermal_path": relative_to_output(thermal_dest, output_root),
                "source_rgb_path": str(rgb.source_path),
                "source_ir_path": str(ir.source_path),
                "source_thermal_video": str(run.thermal_video),
                "gas_timestamp": "",
                "gas_time_delta_s": "",
                "gas_source_line": "",
                "gas_match_flag": "missing",
            }

            if gas_row is not None:
                manifest_row["gas_timestamp"] = gas_row["gas_timestamp_iso"]
                manifest_row["gas_time_delta_s"] = round(float(gas_delta_s), 6)
                manifest_row["gas_source_line"] = gas_row["source_line"]
                manifest_row["gas_match_flag"] = (
                    "ok"
                    if abs(float(gas_delta_s)) <= max_gas_delta_seconds
                    else "outside_expected_delta"
                )
                for field_name, _label in GAS_FIELDS:
                    manifest_row[f"gas_raw_{field_name}"] = gas_row[f"raw_{field_name}"]
                    manifest_row[f"gas_{field_name}"] = gas_row[field_name]
            else:
                for field_name, _label in GAS_FIELDS:
                    manifest_row[f"gas_raw_{field_name}"] = ""
                    manifest_row[f"gas_{field_name}"] = ""

            pending_rows.append(manifest_row)

        extracted = extract_frames_sequential(run.thermal_video, frame_destinations)
        for row in pending_rows:
            frame_index = int(row["thermal_frame_index"])
            result = extracted.get(frame_index)
            if result and result.get("ok"):
                row["thermal_extract_flag"] = "ok"
                row["thermal_video_width"] = result["width"]
                row["thermal_video_height"] = result["height"]
                row["thermal_video_frame_count"] = result["frame_count"]
            else:
                row["thermal_extract_flag"] = (
                    result.get("reason", "not extracted") if result else "not extracted"
                )
                row["thermal_video_width"] = video_width
                row["thermal_video_height"] = video_height
                row["thermal_video_frame_count"] = frame_count

        run_manifest_fieldnames = manifest_fieldnames()
        write_csv(run_output / "manifest.csv", pending_rows, run_manifest_fieldnames)
        all_manifest_rows.extend(pending_rows)

        gas_ok = sum(1 for row in pending_rows if row["gas_match_flag"] == "ok")
        thermal_ok = sum(1 for row in pending_rows if row["thermal_extract_flag"] == "ok")
        max_abs_gas_delta = max(
            (
                abs(float(row["gas_time_delta_s"]))
                for row in pending_rows
                if row["gas_time_delta_s"] != ""
            ),
            default=None,
        )

        run_rows.append(
            {
                "fuel": run.fuel,
                "set_id": f"set-{run.set_number:03d}",
                "source_set_id": run.set_name,
                "flow_setting": run.flow_setting,
                "app1_start": run.app1_start.isoformat(sep=" ", timespec="microseconds"),
                "app1_stop": run.app1_stop.isoformat(sep=" ", timespec="microseconds"),
                "app3_start": run.app3_start.isoformat(sep=" ", timespec="microseconds"),
                "app3_stop": run.app3_stop.isoformat(sep=" ", timespec="microseconds"),
                "rgb_images": len(rgb_records),
                "ir_images": len(ir_records),
                "candidate_rgb_ir_pairs": len(pairs),
                "paired_samples": len(pending_rows),
                "skipped_outside_thermal_window": skipped_outside_thermal_window,
                "unmatched_rgb_images": unmatched_rgb,
                "unmatched_ir_images": unmatched_ir,
                "rgb_ir_threshold_ms": round(rgb_ir_threshold_ms, 3),
                "thermal_video": str(run.thermal_video),
                "thermal_fps": round(fps, 6),
                "thermal_video_frame_count": frame_count,
                "thermal_video_width": video_width,
                "thermal_video_height": video_height,
                "thermal_frames_extracted": thermal_ok,
                "gas_matches_ok": gas_ok,
                "max_abs_gas_delta_s": (
                    round(max_abs_gas_delta, 6) if max_abs_gas_delta is not None else ""
                ),
            }
        )

    write_csv(output_root / "metadata" / "dataset_manifest.csv", all_manifest_rows, manifest_fieldnames())

    run_fieldnames = [
        "fuel",
        "set_id",
        "source_set_id",
        "flow_setting",
        "app1_start",
        "app1_stop",
        "app3_start",
        "app3_stop",
        "rgb_images",
        "ir_images",
        "candidate_rgb_ir_pairs",
        "paired_samples",
        "skipped_outside_thermal_window",
        "unmatched_rgb_images",
        "unmatched_ir_images",
        "rgb_ir_threshold_ms",
        "thermal_video",
        "thermal_fps",
        "thermal_video_frame_count",
        "thermal_video_width",
        "thermal_video_height",
        "thermal_frames_extracted",
        "gas_matches_ok",
        "max_abs_gas_delta_s",
    ]
    write_csv(output_root / "metadata" / "runs.csv", run_rows, run_fieldnames)
    write_csv(
        output_root / "metadata" / "excluded_sets.csv",
        excluded,
        ["fuel", "set_id", "rgb_images", "ir_images", "thermal_videos", "reason"],
    )
    write_csv(
        output_root / "metadata" / "skipped_samples.csv",
        skipped_sample_rows,
        [
            "fuel",
            "set_id",
            "source_set_id",
            "candidate_pair_index",
            "reason",
            "sync_timestamp",
            "thermal_frame_index",
            "thermal_video_frame_count",
            "rgb_sequence",
            "ir_sequence",
            "rgb_tick_ms",
            "ir_tick_ms",
            "source_rgb_path",
            "source_ir_path",
            "source_thermal_video",
        ],
    )

    schema = build_schema()
    (output_root / "metadata" / "schema.json").write_text(
        json.dumps(schema, indent=2, default=json_safe),
        encoding="utf-8",
    )

    report = {
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "raw_root": raw_root,
        "output_root": output_root,
        "usable_runs": len(runs),
        "excluded_sets": len(excluded),
        "skipped_candidate_samples": len(skipped_sample_rows),
        "synchronized_samples": len(all_manifest_rows),
        "link_mode_requested": link_mode,
        "link_counts": link_counts,
        "gas_rows": {fuel: len(rows) for fuel, rows in gas_logs.items()},
        "runs": run_rows,
        "assumptions": [
            "Application 1 is the thermal camera.",
            "Application 3 is the RGB/IR capture application.",
            "PNG filename hexadecimal suffix is treated as a millisecond camera tick.",
            "Thermal video timing is linear at OpenCV-reported FPS from Application 1 start time.",
            "Gas analyser rows are matched by nearest wall-clock timestamp.",
        ],
    }
    (output_root / "metadata" / "processing_report.json").write_text(
        json.dumps(report, indent=2, default=json_safe),
        encoding="utf-8",
    )
    write_readme(
        output_root,
        len(all_manifest_rows),
        len(runs),
        len(excluded),
        len(skipped_sample_rows),
    )

    script_destination = output_root / "scripts" / Path(__file__).name
    if Path(__file__).resolve() != script_destination.resolve():
        shutil.copy2(Path(__file__), script_destination)

    requirements_source = Path(__file__).with_name("requirements_flare_preprocessing.txt")
    if requirements_source.exists():
        shutil.copy2(
            requirements_source,
            output_root / "scripts" / requirements_source.name,
        )

    return report


def manifest_fieldnames() -> list[str]:
    base = [
        "sample_id",
        "fuel",
        "set_id",
        "source_set_id",
        "candidate_pair_index",
        "flow_setting",
        "sync_timestamp",
        "rgb_timestamp",
        "ir_timestamp",
        "thermal_timestamp",
        "rgb_ir_delta_ms",
        "thermal_time_delta_ms",
        "thermal_frame_index",
        "thermal_fps",
        "thermal_video_width",
        "thermal_video_height",
        "thermal_video_frame_count",
        "rgb_sequence",
        "ir_sequence",
        "rgb_tick_ms",
        "ir_tick_ms",
        "rgb_path",
        "ir_path",
        "thermal_path",
        "source_rgb_path",
        "source_ir_path",
        "source_thermal_video",
        "thermal_extract_flag",
        "gas_timestamp",
        "gas_time_delta_s",
        "gas_source_line",
        "gas_match_flag",
    ]
    return base + gas_fieldnames()


def main() -> None:
    args = parse_args()
    report = process_dataset(
        raw_root=args.raw_root,
        output_root=args.output_root,
        link_mode=args.link_mode,
        max_gas_delta_seconds=args.max_gas_delta_seconds,
    )
    print(json.dumps(report, indent=2, default=json_safe))


if __name__ == "__main__":
    main()
