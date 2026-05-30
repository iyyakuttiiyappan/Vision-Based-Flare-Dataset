# Dataset Card

## Name

SmartFlare synchronized multimodal flare imaging and gas-analyser dataset.

## Modalities

- RGB images.
- IR images.
- Thermal frames extracted from video.
- ENERAC gas-analyser records matched by nearest timestamp.

## Current Release Statistics

| Item | Count |
|---|---:|
| Complete synchronized samples | 2,878 |
| RGB PNG files | 2,878 |
| IR PNG files | 2,878 |
| Thermal PNG files | 2,878 |
| Methane synchronized samples | 938 |
| Propane/propene synchronized samples | 1,940 |

## Recommended Uses

- Dataset technical validation.
- Multimodal image-to-gas regression.
- Sensor fusion across RGB, IR, thermal, and gas-analyser streams.
- Flare-monitoring workflow development.

## Caveats

- Adjacent frames are temporally correlated; random frame splits can overestimate generalization.
- Confirm final propane/propene terminology before public release.
- Some gas-analyser fields contain status strings, missing values, or sparse numeric coverage.
