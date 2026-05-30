# SmartFlare Dataset

SmartFlare is a synchronized multimodal flare-stack dataset collected in a laboratory environment on 2026-05-15. Each complete sample links RGB imagery, IR imagery, a thermal frame extracted from video, and the nearest gas-analyser record.

This GitHub repository is the lightweight companion to the full dataset deposit. It contains metadata, gas-analyser tables, preprocessing code, release documentation, and checksum files. The large image payload is hosted separately on our institutional drive.

## Full Dataset Access

Full dataset link: **[SmartFlare institutional-drive dataset](https://kuacae-my.sharepoint.com/:f:/g/personal/iyyakutti_ganapathi_ku_ac_ae/IgB8IwLj3Oa-Q7oXbW1ou7JBAbPEtuy6UreUvFEy4709KlE?e=AOhr3V)**

Expected downloaded dataset folder:

```text
FlareScientificData_2026-05-15_dataset_v1/
  data/
  gas_analyser/
  metadata/
  scripts/
  README.md
```

## Release Snapshot

| Item | Value |
|---|---:|
| Complete synchronized samples | 2,878 |
| RGB PNG files | 2,878 |
| IR PNG files | 2,878 |
| Thermal PNG files | 2,878 |
| Methane synchronized samples | 938 |
| Propane/propene synchronized samples | 1,940 |

The source folder name `propene` is retained in metadata for provenance. In the manuscript text, confirm the final terminology for the propane/propene fuel collection before public release.

## Repository Contents

| Path | Contents |
|---|---|
| `data/` | Placeholder and institutional-drive link template. No image payload is stored in GitHub. |
| `metadata/` | Dataset manifest, run table, schema, processing report, excluded sets, and skipped samples. |
| `gas_analyser/` | Cleaned methane and propane/propene gas-analyser CSV files. |
| `scripts/` | Reproducible preprocessing script. |
| `requirements/` | Python dependency files. |
| `checksums/` | SHA-256 manifest copied from the dataset upload package. |
| `docs/` | Dataset card, structure notes, data dictionary, upload checklist, and data-availability template. |

## Reproducing Preprocessing

Install preprocessing dependencies:

```bash
python -m pip install -r requirements/preprocessing.txt
```

Run preprocessing:

```bash
python scripts/preprocess_flare_dataset.py --raw-root "PATH_TO_RAW_COLLECTION" --output-root "PATH_TO_OUTPUT"
```

## Using The Dataset

After downloading the full dataset from the institutional drive, load `metadata/dataset_manifest.csv`. Each row contains relative paths for the synchronized RGB, IR, and thermal images plus nearest gas-analyser values.

Example fields:

- `rgb_path`
- `ir_path`
- `thermal_path`
- gas-analyser columns with `gas_` prefixes

The dataset is suitable for multimodal sensor fusion, image-to-gas regression, synchronization studies, and technical validation of flare monitoring workflows.


## Citation



## License


