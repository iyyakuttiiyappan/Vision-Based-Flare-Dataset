# Dataset Structure

The full dataset is hosted outside GitHub because it contains thousands of image files.

```text
FlareScientificData_2026-05-15_dataset_v1/
  data/
    methane/
    propene/
  gas_analyser/
    methane_gas_clean.csv
    propene_gas_clean.csv
  metadata/
    dataset_manifest.csv
    dataset_manifest_qc.csv
    gas_qc_report.json
    gas_qc_summary.csv
    runs.csv
    excluded_sets.csv
    skipped_samples.csv
    processing_report.json
    schema.json
  scripts/
    generate_gas_qc_manifest.py
    preprocess_flare_dataset.py
    requirements_flare_preprocessing.txt
  README.md
```

The `data/` directory contains synchronized RGB, IR, and thermal PNG images organized by fuel and acquisition run. The QC manifest is the recommended index for modelling; the original manifest is retained for audit.
