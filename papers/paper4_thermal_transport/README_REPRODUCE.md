# Reproducing Paper 4

This companion reproduces the protocol-frozen electrothermal transport benchmark, post-reveal
diagnostics, figures, evidence validation, supplementary material, and journal-neutral submission
files for:

> *Do Electrothermal Models Transport Across PMSMs? A Protocol-Frozen Benchmark of Source Priors,
> Five-Minute Calibration, and Support-Aware Uncertainty*

The numerical analysis is deterministic given the two public datasets and recorded software
environment. Raw third-party files are intentionally excluded from the reproducibility bundle.

## 1. Environment

Python 3.11 or newer is required. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,publication]"
```

The frozen run used Python 3.12.13 on Windows 11 with NumPy 2.5.2, pandas 3.0.5, SciPy 1.18.0,
and scikit-learn 1.9.0. `results/paper4_thermal_transport/run_metadata.json` records versions and
SHA-256 hashes.

## 2. Public data

### 52 kW source PMSM

Download the Electric Motor Temperature dataset, DOI
[`10.34740/KAGGLE/DSV/2161054`](https://doi.org/10.34740/KAGGLE/DSV/2161054), and place
`measures_v2.csv` at:

```text
data/raw/electric_motor_temperature/measures_v2.csv
```

The expected file is 300,061,411 bytes with SHA-256
`78f3d150f0f2ad9c5dc7ff24dd12c00d386ad530f48c1589ad24fcd88867d3ad`. It contains
1,330,816 rows and 69 profiles. Observe the dataset's CC BY-SA 4.0 terms.

### External IPMSM

Clone the code/data repository accompanying DOI
[`10.1109/TPEL.2024.3409388`](https://doi.org/10.1109/TPEL.2024.3409388):

```powershell
git clone https://github.com/Zirui24/lptn_informed_LSTM.git data/raw/lptn_informed_lstm
git -C data/raw/lptn_informed_lstm checkout 98e4566b5fb7c70499996fda18dd73179ec16509
```

The 16 authoritative `data/id_*.csv` files must contain 97,725 rows. Do not use
`active_wind_est`, `stator_est`, or `rotor_est` in a target-blind pipeline; they are outputs of the
published target-specific model. The repository is MIT licensed.

## 3. Audit and freeze controls

```powershell
python scripts/audit_paper4_thermal_data.py
python scripts/validate_paper4_evidence.py
```

The audit verifies schemas, finiteness, exact-row uniqueness, contiguous profiles, the lossless
external aggregate, blocked estimate columns, deterministic 2 Hz-to-1 Hz source reduction, and
data hashes. The evidence validator also checks the protocol/configuration/selection hashes and
external Git commit.

The original chronology cannot be recreated as a new blind event after outcomes have been viewed.
`docs/paper4_reveal_log.md` records what was known at freeze, the validation-only selection, the
pre-test mechanical inference amendment, and every gate outcome.

## 4. Rebuild the frozen benchmark

```powershell
python scripts/run_paper4_thermal_transport.py
python scripts/analyze_paper4_transport_diagnostics.py
```

The run must reproduce:

- raw source thermal-network RMSE 1.8673 °C on 14 source-test profiles;
- raw external RMSE 24.4928 °C on 16 profiles, a 13.1167-fold degradation;
- five-minute source-prior external RMSE 13.6104 °C with 999 guard clips;
- five-minute target-only external RMSE 6.0175 °C with no clips;
- 6 supported and 10 rejected external profiles;
- source-prior RMSE 3.1933 °C on the supported external subset;
- raw-model external joint trajectory coverage 1/16; and
- source-prior mean matched band half-width 106.0687 °C.

The diagnostic command only reshapes frozen predictions and profile outputs. It does not refit,
retune, rescale, change support, alter a threshold, or remove a primary profile.

## 5. Rebuild figures and publication artifacts

```powershell
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
```

The evidence validator re-reads the frozen tables and checks all headline errors, gates, support
denominators, coverage counts, band width, budget result, guard counts, bibliography keys, and both
PNG/PDF versions of five figures.

## 6. Verification

```powershell
ruff check .
pytest -q
```

For submission, render the final DOCX in Microsoft Word or LibreOffice and inspect every page.
Rasterize and inspect the manuscript and supplementary PDFs. Repeat this check after applying a
journal template because changed pagination can split tables or detach captions.

## 7. Evidential boundary

The benchmark contains two physical machines, one per public dataset. Profiles are repeated duty
cycles rather than independent motor specimens. The external shift changes machine scale, cooling,
thermal-node semantics, sensors, control, and excitation together. The study therefore supports a
conditional two-machine transport result, not fleet-level generalization or causal attribution to
one shift component. Five- and fifteen-minute target-only results assume temporary access to all
three target temperatures during instrumented commissioning.

