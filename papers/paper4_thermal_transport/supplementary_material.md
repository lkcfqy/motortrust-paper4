# Supplementary material

## Do Electrothermal Models Transport Across PMSMs?

This supplement reports the complete frozen evidence behind the main manuscript. Temperatures are
in degrees Celsius unless stated otherwise. One complete operating profile is the statistical unit;
seconds within a profile are dependent trajectory points. “External” means the second recorded
IPMSM, not a fleet sample. No table below removes predeclared-unsupported profiles from a primary
endpoint.

# S1. Dataset contract, profiles, and leakage controls

The source dataset contains 1,330,816 rows, 69 profiles, one 52 kW PMSM, 2 Hz native acquisition,
and 184.836 audited hours. The external dataset contains 97,725 rows, 16 profiles, one IPMSM, and a
published one-second update step. The raw external rows imply 27.146 h; the source repository states
23.8 h. The discrepancy was frozen as a metadata limitation, and timing calculations use row order
and the code-defined step.

The grouped source split is immutable:

- train (44): 3, 4, 5, 8, 9, 15, 16, 17, 18, 19, 21, 24, 27, 29, 30, 36, 41, 44, 46, 47, 48, 49, 50, 51, 52, 57, 58, 60, 61, 62, 64, 66, 67, 68, 70, 72, 73, 74, 75, 76, 78, 79, 80, 81;
- validation (11): 10, 13, 23, 31, 32, 42, 53, 54, 55, 63, 69;
- locked test (14): 2, 6, 7, 11, 12, 14, 20, 26, 43, 45, 56, 59, 65, 71.

All 16 external profiles were locked from selection. External aggregate columns
`active_wind_est`, `stator_est`, and `rotor_est` are outputs of the published target-specific model.
They were never loaded into the primary feature, target, tuning, support, or evaluation pipeline.
Raw `id_*.csv` files were authoritative. Their shared 22 columns agreed exactly with the same raw
columns in the aggregate file.

The harmonized state was winding, stator core, and rotor. Source `stator_winding` mapped to the mean
of external `activewind_1` and `activewind_2`; the mean of source `stator_tooth` and `stator_yoke`
mapped to the mean of external `slotbottom` and `outer_yoke`; source `pm` mapped to external
`rotor`. The last mapping is a semantic proxy and not an identical sensor location.

# S2. Timeline, state equation, and estimand

Source samples were reduced to 1 Hz by averaging paired exogenous/boundary values and retaining the
thermal endpoint. Every primary profile exposed seconds `[0,300)` for commissioning. The state at
second 299 anchored a recursive hidden-label rollout over `[300,1500)`. Source profiles also used
`[300,3600)` for the long-horizon endpoint. Frozen models could use the boundary state but could not
fit to prefix temperatures. Target-only and source-prior models could use only prefix transitions.

For thermal node j, the constrained model was

**ΔT(j,t) = Σ(k≠j) a(j,k)[T(k,t−1)−T(j,t−1)] + b(j,c)[Tc(t)−T(j,t−1)] + b(j,a)[Ta(t)−T(j,t−1)] + Σ(m=1…5) q(j,m) φm(t).**

Every coefficient was nonnegative. Loss proxies were |i|², |i|²|ω|, |u||i|, |τω|, and |ω|². The
raw model retained source absolute scale through source-only
numerical denominators. The normalized model used only first-prefix exogenous magnitudes and
source-learned positive floors. These coefficients are effective grey-box terms, not uniquely
identified physical resistances or capacitances.

Profile-macro RMSE first averaged the three node RMSEs within each profile and then equally averaged
profiles. Paired intervals resampled complete profiles 10,000 times. The common numerical guard was
[-50,250] °C; a clipped prediction remained in the error calculation and every clip was counted.

# S3. Validation-only model selection

The first five rows tune Ridge alpha; the remaining rows tune the quadratic source-prior penalty.
Only 11 source-validation profiles entered this table. Source test and all external errors were
unknown at selection.

| Family | Candidate | Validation RMSE | Clips | Selected |
|---|---|---|---|---|
| Ridge Alpha | 0.01 | 14.087 | 0 | no |
| Ridge Alpha | 0.1 | 14.132 | 0 | no |
| Ridge Alpha | 1.0 | 14.238 | 0 | no |
| Ridge Alpha | 10.0 | 13.826 | 0 | no |
| Ridge Alpha | 100.0 | 10.543 | 0 | yes |
| Source Prior Penalty | 0.1 | 13.427 | 0 | yes |
| Source Prior Penalty | 1.0 | 25.158 | 48 | no |
| Source Prior Penalty | 10.0 | 18.485 | 111 | no |
| Source Prior Penalty | 100.0 | 15.621 | 0 | no |
| Source Prior Penalty | 1000.0 | 14.439 | 0 | no |

The frozen values were Ridge alpha 100 and source-prior penalty 0.1. The selected model bundle,
coefficient table, validation table, configuration, and selection metadata were written before the
locked outcomes. A later fast tree-traversal implementation changed only inference speed for the
already fitted histogram residual comparator; it matched public scikit-learn predictions to
absolute tolerance 10⁻¹⁴ and preceded any test outcome.

# S4. Complete matched-horizon method results

The table contains every locked method. Mean, median, and worst values are complete-profile macro
RMSE. The published LPTN row is external context only because it uses target-specific development
information unavailable to the target-blind methods.

| Method | Source mean | Source median | Source worst | Source clips | External mean | External median | External worst | External clips |
|---|---|---|---|---|---|---|---|---|
| Initial-state persistence | 14.303 | 12.416 | 26.249 | 0 | 6.385 | 6.664 | 13.124 | 0 |
| Boundary-shift persistence | 13.555 | 12.141 | 29.214 | 0 | 6.166 | 6.274 | 12.609 | 0 |
| Source Ridge ARX | 9.570 | 7.867 | 17.013 | 0 | 16.760 | 8.072 | 86.487 | 306 |
| Raw source thermal network | 1.867 | 1.786 | 4.068 | 0 | 24.493 | 27.280 | 44.321 | 0 |
| Normalized source thermal network | 8.918 | 8.507 | 22.469 | 0 | 21.984 | 9.786 | 122.962 | 683 |
| Target-only prefix network | 6.023 | 5.086 | 17.859 | 0 | 6.018 | 5.205 | 23.499 | 0 |
| Source-prior prefix network | 13.508 | 6.270 | 58.534 | 45 | 13.610 | 4.291 | 151.018 | 999 |
| Source thermal + residual | 9.153 | 9.202 | 20.288 | 0 | 26.128 | 17.719 | 120.950 | 684 |
| Published target-specific LPTN (context) | -- | -- | -- | -- | 3.468 | 3.067 | 8.393 | 0 |

The raw source network's 1.867 °C source error and 24.493 °C external error give a 13.1167-fold
transport degradation. The source-prior method's external median (4.291 °C) is much smaller than
its mean (13.610 °C) because profile 14 is catastrophic. Therefore medians alone would conceal a
deployment failure.

## S4.1 Per-node results for the principal thermal models

| Dataset | Method | Node | Mean RMSE | Mean MAE | Mean max error | Clips |
|---|---|---|---|---|---|---|
| External | Normalized source thermal network | Rotor | 12.236 | 9.939 | 22.320 | 683 |
| External | Normalized source thermal network | Stator Core | 17.796 | 15.192 | 26.963 | 683 |
| External | Normalized source thermal network | Winding | 35.920 | 31.720 | 51.526 | 683 |
| External | Raw source thermal network | Rotor | 9.887 | 8.557 | 16.200 | 0 |
| External | Raw source thermal network | Stator Core | 20.245 | 17.889 | 31.106 | 0 |
| External | Raw source thermal network | Winding | 43.346 | 38.815 | 69.330 | 0 |
| External | Source-prior prefix network | Rotor | 12.019 | 10.039 | 20.851 | 999 |
| External | Source-prior prefix network | Stator Core | 12.548 | 10.666 | 19.396 | 999 |
| External | Source-prior prefix network | Winding | 16.265 | 14.778 | 21.618 | 999 |
| External | Target-only prefix network | Rotor | 8.227 | 7.078 | 13.986 | 0 |
| External | Target-only prefix network | Stator Core | 5.697 | 4.548 | 11.921 | 0 |
| External | Target-only prefix network | Winding | 4.128 | 3.328 | 8.500 | 0 |
| Source | Normalized source thermal network | Rotor | 6.331 | 5.417 | 10.614 | 0 |
| Source | Normalized source thermal network | Stator Core | 6.644 | 5.767 | 10.886 | 0 |
| Source | Normalized source thermal network | Winding | 13.779 | 12.124 | 22.450 | 0 |
| Source | Raw source thermal network | Rotor | 1.889 | 1.587 | 3.665 | 0 |
| Source | Raw source thermal network | Stator Core | 1.516 | 1.306 | 2.799 | 0 |
| Source | Raw source thermal network | Winding | 2.197 | 1.886 | 4.205 | 0 |
| Source | Source-prior prefix network | Rotor | 11.035 | 9.402 | 19.474 | 45 |
| Source | Source-prior prefix network | Stator Core | 9.988 | 8.716 | 17.408 | 45 |
| Source | Source-prior prefix network | Winding | 19.500 | 16.967 | 34.656 | 45 |
| Source | Target-only prefix network | Rotor | 5.750 | 4.845 | 10.355 | 0 |
| Source | Target-only prefix network | Stator Core | 4.847 | 4.109 | 8.075 | 0 |
| Source | Target-only prefix network | Winding | 7.472 | 6.303 | 13.205 | 0 |

Source permanent-magnet and external rotor temperatures are displayed under the common “Rotor”
label only for the frozen semantic bridge. The large raw-model external winding error should not be
interpreted as a controlled estimate of sensor-location effects.

## S4.2 Complete source-prior paired comparisons

Positive improvement means the candidate source-prior method has lower RMSE than the named
baseline. Intervals and Holm-adjusted values are profile-level descriptions; they do not provide
machine-population inference.

| Dataset | Horizon | Baseline | Baseline RMSE | Prior RMSE | Improvement | 95% interval | Holm p |
|---|---|---|---|---|---|---|---|
| External | matched 20min | Boundary-shift persistence | 6.166 | 13.610 | -7.444 | [-26.762, 2.853] | 0.1160 |
| External | matched 20min | Initial-state persistence | 6.385 | 13.610 | -7.225 | [-26.629, 3.138] | 0.1160 |
| External | matched 20min | Normalized source thermal network | 21.984 | 13.610 | 8.373 | [0.130, 17.652] | 0.1869 |
| External | matched 20min | Raw source thermal network | 24.493 | 13.610 | 10.882 | [-12.251, 25.296] | 0.0361 |
| External | matched 20min | Source Ridge ARX | 16.760 | 13.610 | 3.150 | [-7.449, 11.039] | 0.0549 |
| External | matched 20min | Source thermal + residual | 26.128 | 13.610 | 12.517 | [3.736, 21.215] | 0.0377 |
| External | matched 20min | Target-only prefix network | 6.018 | 13.610 | -7.593 | [-23.847, 0.948] | 0.6322 |
| Source | long 55min | Boundary-shift persistence | 16.576 | 28.654 | -12.078 | [-34.385, 4.692] | 1.0000 |
| Source | long 55min | Initial-state persistence | 18.722 | 28.654 | -9.933 | [-31.449, 6.148] | 1.0000 |
| Source | long 55min | Normalized source thermal network | 13.252 | 28.654 | -15.403 | [-38.083, 2.603] | 1.0000 |
| Source | long 55min | Raw source thermal network | 2.376 | 28.654 | -26.278 | [-47.258, -10.067] | 0.0043 |
| Source | long 55min | Source Ridge ARX | 13.226 | 28.654 | -15.429 | [-36.942, 1.572] | 1.0000 |
| Source | long 55min | Source thermal + residual | 12.880 | 28.654 | -15.774 | [-37.732, 1.009] | 1.0000 |
| Source | long 55min | Target-only prefix network | 10.943 | 28.654 | -17.712 | [-38.955, -1.010] | 0.7134 |
| Source | matched 20min | Boundary-shift persistence | 13.555 | 13.508 | 0.047 | [-10.595, 8.507] | 0.9185 |
| Source | matched 20min | Initial-state persistence | 14.303 | 13.508 | 0.795 | [-9.397, 8.500] | 0.9185 |
| Source | matched 20min | Normalized source thermal network | 8.918 | 13.508 | -4.590 | [-15.642, 4.079] | 1.0000 |
| Source | matched 20min | Raw source thermal network | 1.867 | 13.508 | -11.640 | [-21.536, -3.902] | 0.0120 |
| Source | matched 20min | Source Ridge ARX | 9.570 | 13.508 | -3.938 | [-12.880, 3.364] | 1.0000 |
| Source | matched 20min | Source thermal + residual | 9.153 | 13.508 | -4.355 | [-15.196, 4.393] | 1.0000 |
| Source | matched 20min | Target-only prefix network | 6.023 | 13.508 | -7.485 | [-17.670, 0.479] | 0.9185 |

# S5. Commissioning-label budget

Every budget is followed by the same 600-s hidden-label rollout. This prevents later budgets from
receiving an easier endpoint merely because their remaining profile segment is shorter. The
five-minute values here use a 10-minute rollout and therefore differ from the primary five-minute,
20-minute endpoint.

| Dataset | Prefix (min) | Method | Mean RMSE | Median RMSE | Worst RMSE | Clips |
|---|---|---|---|---|---|---|
| External | 1 | Normalized source thermal network | 44.218 | 5.087 | 174.082 | 2294 |
| External | 1 | Source-prior prefix network | 23.931 | 9.601 | 157.427 | 1213 |
| External | 1 | Target-only prefix network | 9.317 | 5.814 | 48.755 | 153 |
| External | 5 | Normalized source thermal network | 12.454 | 5.513 | 82.882 | 83 |
| External | 5 | Source-prior prefix network | 8.090 | 2.611 | 89.429 | 129 |
| External | 5 | Target-only prefix network | 3.408 | 3.228 | 7.853 | 0 |
| External | 15 | Normalized source thermal network | 4.897 | 4.723 | 18.642 | 0 |
| External | 15 | Source-prior prefix network | 2.566 | 1.831 | 10.370 | 0 |
| External | 15 | Target-only prefix network | 2.065 | 1.819 | 5.349 | 0 |
| Source | 1 | Normalized source thermal network | 11.502 | 7.484 | 45.082 | 0 |
| Source | 1 | Source-prior prefix network | 20.649 | 16.269 | 66.687 | 202 |
| Source | 1 | Target-only prefix network | 22.395 | 16.775 | 70.917 | 34 |
| Source | 5 | Normalized source thermal network | 6.019 | 4.589 | 17.366 | 0 |
| Source | 5 | Source-prior prefix network | 7.463 | 3.127 | 33.096 | 0 |
| Source | 5 | Target-only prefix network | 3.523 | 3.227 | 8.911 | 0 |
| Source | 15 | Normalized source thermal network | 6.550 | 6.147 | 14.358 | 0 |
| Source | 15 | Source-prior prefix network | 2.247 | 1.878 | 8.133 | 0 |
| Source | 15 | Target-only prefix network | 2.035 | 1.043 | 12.082 | 0 |

The 15-minute target-only result is the lowest average error on both recorded machines and has no
guard activation. This does not establish an optimal universal budget; it shows that the source
prior was not needed once these prefixes supplied sufficient local transitions.

# S6. Complete trajectory-band audit

Each source-validation profile contributed one maximum absolute error per node. With 11 calibration
profiles and nominal 90% coverage, rank 11—the maximum calibration score—sets the constant
half-width. “Node coverage” means every second for the named node was inside its band. “Joint” means
all three nodes and all seconds were covered. External values are stress-test outcomes without a
cross-machine guarantee.

| Dataset | Method | Node | Half-width | Node coverage | Joint coverage |
|---|---|---|---|---|---|
| External | Boundary-shift persistence | Rotor | 43.099 | 16/16 | 16/16 |
| External | Boundary-shift persistence | Stator Core | 41.819 | 16/16 | 16/16 |
| External | Boundary-shift persistence | Winding | 83.229 | 16/16 | 16/16 |
| External | Initial-state persistence | Rotor | 44.592 | 16/16 | 16/16 |
| External | Initial-state persistence | Stator Core | 43.121 | 16/16 | 16/16 |
| External | Initial-state persistence | Winding | 84.539 | 16/16 | 16/16 |
| External | Normalized source thermal network | Rotor | 26.741 | 13/16 | 13/16 |
| External | Normalized source thermal network | Stator Core | 46.703 | 13/16 | 13/16 |
| External | Normalized source thermal network | Winding | 91.637 | 13/16 | 13/16 |
| External | Raw source thermal network | Rotor | 3.810 | 2/16 | 1/16 |
| External | Raw source thermal network | Stator Core | 4.317 | 1/16 | 1/16 |
| External | Raw source thermal network | Winding | 8.058 | 1/16 | 1/16 |
| External | Source-prior prefix network | Rotor | 72.058 | 15/16 | 15/16 |
| External | Source-prior prefix network | Stator Core | 87.265 | 15/16 | 15/16 |
| External | Source-prior prefix network | Winding | 158.883 | 15/16 | 15/16 |
| External | Source Ridge ARX | Rotor | 20.195 | 13/16 | 11/16 |
| External | Source Ridge ARX | Stator Core | 20.165 | 11/16 | 11/16 |
| External | Source Ridge ARX | Winding | 44.405 | 11/16 | 11/16 |
| External | Source thermal + residual | Rotor | 38.455 | 13/16 | 13/16 |
| External | Source thermal + residual | Stator Core | 51.647 | 14/16 | 13/16 |
| External | Source thermal + residual | Winding | 100.600 | 14/16 | 13/16 |
| External | Target-only prefix network | Rotor | 66.992 | 16/16 | 15/16 |
| External | Target-only prefix network | Stator Core | 37.807 | 15/16 | 15/16 |
| External | Target-only prefix network | Winding | 77.821 | 16/16 | 15/16 |
| Source | Boundary-shift persistence | Rotor | 43.099 | 13/14 | 13/14 |
| Source | Boundary-shift persistence | Stator Core | 41.819 | 14/14 | 13/14 |
| Source | Boundary-shift persistence | Winding | 83.229 | 14/14 | 13/14 |
| Source | Initial-state persistence | Rotor | 44.592 | 13/14 | 13/14 |
| Source | Initial-state persistence | Stator Core | 43.121 | 14/14 | 13/14 |
| Source | Initial-state persistence | Winding | 84.539 | 14/14 | 13/14 |
| Source | Normalized source thermal network | Rotor | 26.741 | 14/14 | 14/14 |
| Source | Normalized source thermal network | Stator Core | 46.703 | 14/14 | 14/14 |
| Source | Normalized source thermal network | Winding | 91.637 | 14/14 | 14/14 |
| Source | Raw source thermal network | Rotor | 3.810 | 10/14 | 9/14 |
| Source | Raw source thermal network | Stator Core | 4.317 | 13/14 | 9/14 |
| Source | Raw source thermal network | Winding | 8.058 | 13/14 | 9/14 |
| Source | Source-prior prefix network | Rotor | 72.058 | 13/14 | 13/14 |
| Source | Source-prior prefix network | Stator Core | 87.265 | 14/14 | 13/14 |
| Source | Source-prior prefix network | Winding | 158.883 | 14/14 | 13/14 |
| Source | Source Ridge ARX | Rotor | 20.195 | 13/14 | 11/14 |
| Source | Source Ridge ARX | Stator Core | 20.165 | 12/14 | 11/14 |
| Source | Source Ridge ARX | Winding | 44.405 | 12/14 | 11/14 |
| Source | Source thermal + residual | Rotor | 38.455 | 14/14 | 14/14 |
| Source | Source thermal + residual | Stator Core | 51.647 | 14/14 | 14/14 |
| Source | Source thermal + residual | Winding | 100.600 | 14/14 | 14/14 |
| Source | Target-only prefix network | Rotor | 66.992 | 14/14 | 14/14 |
| Source | Target-only prefix network | Stator Core | 37.807 | 14/14 | 14/14 |
| Source | Target-only prefix network | Winding | 77.821 | 14/14 | 14/14 |

The source-prior half-widths are 72.06 °C (rotor), 87.26 °C (stator core), and 158.88 °C
(winding). Their 106.07 °C mean makes the 15/16 external joint coverage operationally weak. In
contrast, the raw network's mean half-width is 5.40 °C but covers only 1/16 external profiles
jointly. Both coverage and sharpness are necessary.

# S7. Support and abstention

Support used median and 95th-percentile summaries of first-five-minute exogenous variables,
source-train robust scaling, and nearest-source-profile distance. The threshold 7.8263 was the 95th
percentile of source leave-one-profile-out nearest-neighbour distances. It did not use target
temperature labels.

## S7.1 External profile decisions

| External profile | Distance | Threshold | Decision | Nearest source profile |
|---|---|---|---|---|
| 0 | 7.099 | 7.826 | supported | 18 |
| 1 | 5.544 | 7.826 | supported | 30 |
| 2 | 5.676 | 7.826 | supported | 30 |
| 3 | 14.581 | 7.826 | rejected | 5 |
| 4 | 16.939 | 7.826 | rejected | 80 |
| 5 | 15.943 | 7.826 | rejected | 16 |
| 6 | 14.330 | 7.826 | rejected | 8 |
| 7 | 6.853 | 7.826 | supported | 3 |
| 8 | 7.670 | 7.826 | supported | 5 |
| 9 | 11.619 | 7.826 | rejected | 44 |
| 10 | 8.016 | 7.826 | rejected | 19 |
| 11 | 11.577 | 7.826 | rejected | 72 |
| 12 | 9.733 | 7.826 | rejected | 70 |
| 13 | 6.709 | 7.826 | supported | 57 |
| 14 | 10.158 | 7.826 | rejected | 3 |
| 15 | 11.794 | 7.826 | rejected | 68 |

Six profiles were accepted and ten rejected. This 62.5% abstention rate is reported beside the
accepted-subset accuracy and prevents the subset from replacing the all-profile result.

## S7.2 Support-stratified performance

| Subset | Method | Profiles | Mean RMSE | Median RMSE | Worst RMSE | Clips |
|---|---|---|---|---|---|---|
| accepted | Boundary-shift persistence | 6 | 5.144 | 5.367 | 10.283 | 0 |
| accepted | Published target-specific LPTN | 6 | 2.099 | 2.153 | 3.895 | 0 |
| accepted | Normalized source thermal network | 6 | 26.452 | 19.653 | 52.323 | 0 |
| accepted | Raw source thermal network | 6 | 19.420 | 19.488 | 31.509 | 0 |
| accepted | Source-prior prefix network | 6 | 3.193 | 4.218 | 4.676 | 0 |
| accepted | Target-only prefix network | 6 | 4.565 | 4.588 | 7.374 | 0 |
| rejected | Boundary-shift persistence | 10 | 6.780 | 6.274 | 12.609 | 0 |
| rejected | Published target-specific LPTN | 10 | 4.289 | 4.377 | 8.393 | 0 |
| rejected | Normalized source thermal network | 10 | 19.303 | 6.143 | 122.962 | 683 |
| rejected | Raw source thermal network | 10 | 27.537 | 31.208 | 44.321 | 0 |
| rejected | Source-prior prefix network | 10 | 19.861 | 4.807 | 151.018 | 999 |
| rejected | Target-only prefix network | 10 | 6.889 | 5.205 | 23.499 | 0 |

On accepted profiles, source-prior calibration has 3.193 °C RMSE versus 4.565 °C for target-only
fitting. On rejected profiles, the corresponding errors are 19.861 and 6.889 °C. All 999 external
source-prior clips occur in the rejected subset. This supports further prospective study of gated
priors, but one external machine and six accepted profiles cannot certify a deployment rule.

# S8. Numerical guard events

The following are all primary matched-horizon profile/method combinations with at least one clip.
No non-finite prediction occurred. Macro RMSE and maximum absolute error are averages across the
three nodes for the profile; clip count is accumulated over node-seconds.

| Dataset | Profile | Method | Macro RMSE | Macro max error | Clips |
|---|---|---|---|---|---|
| Source | 45 | Source-prior prefix network | 48.071 | 92.819 | 45 |
| External | 14 | Source Ridge ARX | 86.487 | 146.268 | 306 |
| External | 14 | Normalized source thermal network | 122.962 | 167.731 | 683 |
| External | 14 | Source-prior prefix network | 151.018 | 214.101 | 999 |
| External | 14 | Source thermal + residual | 120.950 | 163.123 | 684 |

Clipping prevents unbounded values from corrupting files; it is not a stability remedy. The guarded
errors remain in all rankings. The unedited external profile-14 source-prior trajectory reaches the
250 °C ceiling in winding and stator-core states and exceeds 200 °C in rotor prediction while the
recorded states remain near ordinary temperatures.

# S9. Reproducibility and immutable identifiers

| Artifact | SHA-256 or commit |
|---|---|
| Protocol configuration | 5e98e959b557b69f2c0d2c0f2b035290751ce135cb3a225f8d6b79a8e5c1bc63 |
| Protocol document | ad0834d5e5693e9bc210932a9d41bafead580b7d6ddc40a6f2cde5e4ef336620 |
| Selection freeze | 1fa8dc73b38ec597e82862c862062928d33cb0a8272f71788f7df78d854f3bd0 |
| Source raw CSV | 78f3d150f0f2ad9c5dc7ff24dd12c00d386ad530f48c1589ad24fcd88867d3ad |
| External repository commit | 98e4566b5fb7c70499996fda18dd73179ec16509 |
| Result: aggregate_summary.csv | 03b41560feda8b35a50d8b6fff0411e8ee04a49c7ffdf843a546ec06e151820e |
| Result: budget_sensitivity_per_profile.csv | ec2f5c8c7d4c9fe890c5cee82c78c439dcac9c4f21d280eed8107b2f799b3bff |
| Result: budget_sensitivity_summary.csv | eb453b4e244b4f3ea5607b27c3c0caeaccddda0d74f5f837f9896645aa96f568 |
| Result: paired_method_comparisons.csv | 45ca6e2b86c639f231805968338c49b730b35405bd70dc00cdd9e83a2d78cc72 |
| Result: per_profile_errors.csv | d79ef4c062a179515cbca35a1d916d25e6eac784168a5b31c7f28cd4a5577cd7 |
| Result: predeclared_gates.json | 2619c9c8f4bed1914ceeb170f523ae0abfd9718daf3e23e33734693fffdfde6e |
| Result: selection_freeze.json | 1fa8dc73b38ec597e82862c862062928d33cb0a8272f71788f7df78d854f3bd0 |
| Result: source_model_bundle.joblib | 5821bd198d5b456d0f8724dfd8d472fff01f1c9c10fd29224d4ab8a9b2737607 |
| Result: source_model_coefficients.csv | ec0153ca4c9e591ffd04644a7891f37960f0ca25c750676313606c4ae6187d52 |
| Result: support_reference.csv | 2bd3115a82ed0ece09a85a8ab555e453b00f9e6f83d01685763f4a0e7015377c |
| Result: support_scores.csv | b3ebaf9a9045d82aaa689fa2e2f8b6b1b5d36e64c3b9de91b8feeb345ad75faf |
| Result: trajectory_band_joint_summary.csv | 01a843241c9b127b6edbadc651e32d00e803fe04914190631300d4560fae2dfc |
| Result: trajectory_band_profile_coverage.csv | f948de43ca0789fa679f55002ff191a698e46df2e07e72bb0416412861008c74 |
| Result: trajectory_band_summary.csv | b9b89cf34d4ddc333959ba039d3fac5739d1e09e940fc870596b85d71f4e0691 |
| Result: trajectory_bands.csv | 01b3d83a1924d3f76014586375a8966ed116349d16c7d851c2e1c20b7d8108aa |
| Result: trajectory_predictions.csv.gz | eda4c458b9c4748952c32a7c5d40ac98ac5f33eb858f9d1356de493310d10f76 |
| Result: validation_tuning.csv | 7df5a8361230133c8ef9cbfea582be4a63b527ba6558f25963c82cddcd0ccbc6 |

The audit records Python 3.12.13 (main, Aug  7 2026, 02:26:41) [MSC v.1944 64 bit (AMD64)], NumPy 2.5.2, pandas
3.0.5, SciPy 1.18.0, and scikit-learn
1.9.0. The evidence validator recomputes the raw-data, protocol, configuration,
and selection hashes; re-reads the result tables; checks every headline result, gate, support
denominator, band width, guard count, figure pair, and bibliography key; and writes a JSON report.

# S10. Interpretation limits

1. Two physical machines do not establish fleet transport. Profile bootstrap intervals describe
   condition variation for those machines only.
2. The external shift is compound, so the failure cannot be causally assigned to power, cooling,
   topology, sensors, controller scaling, or excitation separately.
3. Rotor and permanent-magnet sensors are semantic proxies rather than equivalent labels.
4. Target commissioning assumes temporary access to all three temperatures. It is an information
   benchmark for instrumented commissioning, not a sensor-free production claim.
5. The nonnegative model does not guarantee global closed-loop stability. Numerical guards expose
   rather than solve this limitation.
6. External support and interval outcomes are descriptive; neither restores formal cross-machine
   conformal validity.
7. The target-specific published LPTN is contextual and must never be called a target-blind
   baseline.
8. Post-reveal support-stratified comparisons generate hypotheses only. They do not alter the
   frozen all-profile endpoints or gates.

