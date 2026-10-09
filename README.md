# MotorTrust — Paper 4: electrothermal model transport

Independent companion repository for **Do Electrothermal Models Transport Across PMSMs? A Protocol-Frozen Benchmark of Source Priors, Five-Minute Calibration, and Support-Aware Uncertainty**.

Split from [lkcfqy/motortrust](https://github.com/lkcfqy/motortrust/tree/0cbfc7e5b2868f482902f16d6d0b0c71f9d01f11), commit `0cbfc7e5b2868f482902f16d6d0b0c71f9d01f11` (`0cbfc7e`). Copied source, manuscript, configuration, frozen results, figures, submission files and ZIP archives retain their original relative paths and bytes. `SPLIT_MANIFEST.json` records SHA-256 values for those copies.

This repository covers the two-machine thermal-transport benchmark, source priors, instrumented commissioning calibration, support-aware uncertainty and frozen post-reveal diagnostics. It includes only Paper 4 publication artifacts and results. Four shared publication/reference scripts retain historical Paper 2/JEET filenames because the Paper 4 builders import them; the shared bibliography is preserved for rendering and citation validation.

## Contents

- `papers/paper4_thermal_transport/`: manuscript, supplement, five PNG/PDF figure pairs, anonymous DOCX/PDF submission files and original 79-file reproducibility ZIP.
- `configs/paper4_thermal_transport.yaml` and `docs/paper4_*.md`: frozen protocol, data contracts and reveal record.
- `results/paper4_thermal_data_audit/`, `results/paper4_thermal_transport/`, `results/paper4_transport_diagnostics/`: original tables, model bundle and compressed trajectory predictions.
- `src/pmsm_sci/thermal*.py`, `scripts/` and `tests/`: thermal code, reproducibility scripts, required shared renderers and existing Paper 4/thermal tests.
- `data/raw/`: acquisition instructions, source provenance and upstream README/license metadata. Raw third-party datasets, nested Git databases and generated caches are excluded from Git.

## Environment and checks without raw data

Use Python 3.11 or newer. From this repository root:

```sh
python -m venv .venv
. .venv/bin/activate                 # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,publication]"
ruff check .
python scripts/build_paper4_reproducibility_bundle.py --check
python scripts/build_paper4_supplementary_material.py --check
python scripts/build_paper4_submission.py --check
pytest -q -k "not frozen_hashes and not full_report_is_json_ready and not supplement_pdf_audit_when_present"
```

The selected tests check the included frozen headline tables, support/coverage results, publication structure, figures, protocol, thermal calculations, diagnostics and bundle integrity. The full `pytest -q` and `validate_paper4_evidence.py` require raw datasets plus the upstream Git commit. The supplementary PDF audit/builder also registers Windows fonts at `C:/Windows/Fonts`; the original implementation and original PDF are preserved, so that check needs those fonts. The existing manuscript and supplementary PDFs can be inspected on other platforms without rebuilding them.

The frozen run environment is recorded in `results/paper4_thermal_transport/run_metadata.json`. An editable install resolves the package from this repository; avoid importing an earlier MotorTrust editable installation.

## Restore data and reproduce the analysis

Follow [`data/raw/README.md`](data/raw/README.md) to acquire the source CSV and external upstream repository at its frozen commit. The source CSV is 300,061,411 bytes and is omitted here; the external 16 raw profiles and aggregate CSV are omitted too. No processed raw thermal table is needed: the analysis harmonizes the acquired raw tables in memory. Full data audits and a numerical rerun cannot be completed from Git files alone.

After restoration, run from this repository root:

```sh
python scripts/audit_paper4_thermal_data.py
python scripts/validate_paper4_evidence.py
python scripts/run_paper4_thermal_transport.py
python scripts/analyze_paper4_transport_diagnostics.py
python scripts/make_paper4_figures.py
python scripts/validate_paper4_evidence.py
python scripts/build_paper4_supplementary_material.py
python scripts/build_paper4_supplementary_material.py --check
python scripts/build_paper4_submission.py
python scripts/build_paper4_submission.py --check
python scripts/build_paper4_supplementary_pdf.py
python scripts/build_paper4_supplementary_pdf.py --check
python scripts/build_paper4_reproducibility_bundle.py
python scripts/build_paper4_reproducibility_bundle.py --check
pytest -q
```

These rebuild commands update generated artifacts. For the original Windows setup and scientific claim limits, see [`papers/paper4_thermal_transport/README_REPRODUCE.md`](papers/paper4_thermal_transport/README_REPRODUCE.md). Its upstream external-file example says `data/id_*.csv`; the actual upstream layout and preserved scripts use **`dataset/id_*.csv`**.

The results concern two physical machines. Repeated profiles are duty cycles, and the frozen chronology cannot be recreated as a new blind experiment after viewing the outcomes.

## Attribution and licenses

The source Electric Motor Temperature dataset is credited to Kirgsn (`wkirgsn`) and retains CC BY-SA 4.0. The external LPTN-informed LSTM repository retains MIT and Copyright (c) 2024 Zirui Liu. Original applicable license texts are included in `recovery/licenses/` and upstream metadata in `data/raw/`. See [`recovery/licenses/PAPER4_DATA_SOURCES_AND_LICENSES.md`](recovery/licenses/PAPER4_DATA_SOURCES_AND_LICENSES.md).

The source snapshot makes no separate license declaration for independently authored MotorTrust code or manuscripts. This split does not introduce one or relicense those works.
