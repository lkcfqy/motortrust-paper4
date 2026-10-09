# Paper 4 raw data acquisition

Raw measurements are not tracked in Git. Retained metadata records attribution and the exact frozen source hash.

## 52 kW source PMSM

Download **Electric Motor Temperature**, credited to Kirgsn (`wkirgsn`), from the [official Kaggle dataset](https://www.kaggle.com/datasets/wkirgsn/electric-motor-temperature), DOI [10.34740/KAGGLE/DSV/2161054](https://doi.org/10.34740/KAGGLE/DSV/2161054), version 3.

Place `measures_v2.csv` at `data/raw/electric_motor_temperature/measures_v2.csv`. Required size: **300,061,411 bytes**. Required SHA-256: `78f3d150f0f2ad9c5dc7ff24dd12c00d386ad530f48c1589ad24fcd88867d3ad`. The dataset contains 1,330,816 rows and 69 profiles. Preserve CC BY-SA 4.0 attribution and ShareAlike terms. `provenance.json` is retained byte-for-byte as historical acquisition metadata.

## External IPMSM

The [upstream repository](https://github.com/Zirui24/lptn_informed_LSTM) accompanies [10.1109/TPEL.2024.3409388](https://doi.org/10.1109/TPEL.2024.3409388). Paper 4 uses commit `98e4566b5fb7c70499996fda18dd73179ec16509`.

The `data/raw/lptn_informed_lstm/` directory already contains the original README and MIT license. Clone the upstream repository into an empty temporary directory, check out the frozen commit, then copy its contents (including its `.git` directory for local validation) into `data/raw/lptn_informed_lstm/`. Keep this restored repository excluded from the parent Git repository.

```sh
git clone https://github.com/Zirui24/lptn_informed_LSTM.git /tmp/paper4-lptn-source
git -C /tmp/paper4-lptn-source checkout 98e4566b5fb7c70499996fda18dd73179ec16509
cp -R /tmp/paper4-lptn-source/. data/raw/lptn_informed_lstm/
```

Use a fresh temporary path if `/tmp/paper4-lptn-source` already exists. On Windows, use an empty temporary folder and an equivalent copy command that includes hidden `.git` files.

The required native files are `dataset/id_0.csv` through `dataset/id_15.csv` plus `dataset/temperature.csv`, with 97,725 rows across the 16 authoritative profiles. The aggregate contains published estimate columns `active_wind_est`, `stator_est` and `rotor_est`; the target-blind pipeline blocks those outputs. The repository is MIT licensed, Copyright (c) 2024 Zirui Liu.

Check restoration with `python scripts/audit_paper4_thermal_data.py` and `python scripts/validate_paper4_evidence.py` from the repository root. The latter checks the upstream Git commit as well as raw-file and protocol hashes. Downloading CSVs alone does not satisfy its Git provenance check.
