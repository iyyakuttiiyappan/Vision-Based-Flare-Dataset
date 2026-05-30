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
    runs.csv
    excluded_sets.csv
    skipped_samples.csv
    processing_report.json
    schema.json
  scripts/
    preprocess_flare_dataset.py
    requirements_flare_preprocessing.txt
  README.md
```

The `data/` directory contains synchronized RGB, IR, and thermal PNG images organized by fuel and acquisition run. The manifest is the primary index for loading the dataset.
