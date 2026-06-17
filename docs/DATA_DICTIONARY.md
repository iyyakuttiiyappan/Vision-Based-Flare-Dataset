# Data Dictionary

## Core Metadata Files

| File | Purpose |
|---|---|
| `metadata/dataset_manifest.csv` | Unfiltered synchronized sample manifest. |
| `metadata/dataset_manifest_qc.csv` | Synchronized sample manifest with `gas_qc_flag`, `gas_qc_reasons`, and `gas_qc_warnings`. |
| `metadata/gas_qc_report.json` | Gas-label QC rule summary, row counts, and repeated timestamp statistics. |
| `metadata/gas_qc_summary.csv` | Compact table of QC flags, reasons, warnings, and per-run counts. |
| `metadata/runs.csv` | Run-level timing, frame-rate, sample-count, and synchronization summary. |
| `metadata/excluded_sets.csv` | Source sets excluded because they were empty or incomplete. |
| `metadata/skipped_samples.csv` | Candidate samples skipped during synchronization. |
| `metadata/processing_report.json` | Machine-readable preprocessing report. |
| `metadata/schema.json` | Field-level schema generated during preprocessing. |

## Key Manifest Columns

| Column Pattern | Meaning |
|---|---|
| `fuel` | Fuel collection label, including methane and propene/propanerelated source naming. |
| `run_id` or equivalent run fields | Acquisition run/set identifier. |
| `rgb_path` | Relative path to synchronized RGB image. |
| `ir_path` | Relative path to synchronized IR image. |
| `thermal_path` | Relative path to synchronized thermal frame. |
| `gas_*` | Numeric or raw gas-analyser value aligned to the image timestamp. |
| `gas_qc_flag` | `ok` or `reject` for baseline-quality gas-label use. |
| `gas_qc_reasons` | Semicolon-separated reject reasons for suspicious gas rows. |
| `gas_qc_warnings` | Semicolon-separated non-fatal QC warnings. |

## Current Counts

| Item | Count |
|---|---:|
| Complete synchronized samples | 2,878 |
| RGB images | 2,878 |
| IR images | 2,878 |
| Thermal frames | 2,878 |
| Methane synchronized samples | 938 |
| Propane/propene synchronized samples | 1,940 |
