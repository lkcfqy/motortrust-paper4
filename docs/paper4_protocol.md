# Paper 4 frozen protocol: cross-machine electrothermal transport

Frozen on 2026-08-21 before any candidate-model error, ranking, interval coverage, or external
transport outcome was computed. Raw schemas, published code, row counts, node definitions, and
univariate ranges had been inspected for compatibility. The machine-readable contract is
`configs/paper4_thermal_transport.yaml`.

## Question and defensible contribution

The paper asks whether a low-order electrothermal state model learned from one instrumented PMSM
can be transported to a physically different PMSM, and whether five minutes of target-machine
commissioning data improve a frozen source prior without hiding unsupported deployment conditions.

Adaptive PMSM thermal twins, physics-informed neural thermal models, incremental learning, and
domain-adaptation temperature estimators already exist. Therefore, the contribution is not a
first-ever self-calibration algorithm. It is a protocol-frozen, profile-disjoint transport audit
that combines source-prior calibration, closed-loop rather than teacher-forced evaluation,
trajectory-level uncertainty, an explicit support flag, and a fully untouched second public
machine.

## Data and experimental units

The development source is the public 52 kW automotive PMSM dataset (DOI
`10.34740/KAGGLE/DSV/2161054`): 1,330,816 rows, 69 contiguous drive profiles, 2 Hz, approximately
184.836 h, one physical machine. Its immutable CSV SHA-256 is
`78f3d150f0f2ad9c5dc7ff24dd12c00d386ad530f48c1589ad24fcd88867d3ad`.

The external target is the IPMSM dataset accompanying Liu et al. (DOI
`10.1109/TPEL.2024.3409388`), repository commit
`98e4566b5fb7c70499996fda18dd73179ec16509`: 97,725 rows, 16 contiguous profiles, a published
one-second simulation/update step, and one physical machine. The 16 files imply 27.146 h at 1 Hz,
not the 23.8 h stated in the repository README; both figures are disclosed, and all calculations
use the auditable row count and published `tsim = 1` code.

The independent analysis unit is a complete operating profile. Time samples are repeated dependent
observations, not independent replicates. With only two machines, no confidence interval is
interpreted as fleet-population evidence.

## Three-node semantic bridge

The common state vector is winding, stator core, and rotor:

| Node | 52 kW source | External IPMSM | Boundary |
|---|---|---|---|
| Winding | `stator_winding` | mean(`activewind_1`, `activewind_2`) | direct/constructed winding mean |
| Stator core | mean(`stator_tooth`, `stator_yoke`) | mean(`slotbottom`, `outer_yoke`) | constructed core mean |
| Rotor | `pm` | `rotor` | transport proxy, not identical sensor location |

Ambient, coolant/water outlet, dq voltage, feedback dq current, speed, and torque are harmonized in
physical units. External `active_wind_est`, `stator_est`, and `rotor_est` are published model outputs
and are forbidden as model inputs, targets, preprocessing aids, or selection evidence. They may
appear only as a clearly labelled target-specific contextual oracle after the frozen external run.

The source is reduced from 2 Hz to 1 Hz in non-overlapping two-row bins: boundary/electrical inputs
are averaged and thermal states use the bin endpoint. The external data remain at native 1 Hz.

## Immutable source split and timelines

The existing grouped split with seed 42 is retained: 44 source-train profiles, 11 source-validation
profiles, and 14 locked source-test profiles. The exact IDs are stored in the YAML contract. No row
from a profile crosses a role.

For every deployment profile:

1. the three-node initial state at `t=0` is observed;
2. only the first 300 s of target temperature labels may update a target-specific model;
3. every method anchors its rollout at the final observed prefix state (`t=299` for the primary
   budget); frozen methods may use this state but may not update their parameters from prefix labels;
4. all subsequent target temperatures are hidden until an entire recursive rollout is complete;
5. the matched endpoint uses `[300, 1500)` s, giving 20 min of evaluation on all 14 source-test and
   all 16 external profiles;
6. the source dataset additionally uses `[300, 3600)` s as a 55 min long-horizon endpoint.

All methods share a numerical state guard of -50 to 250 °C. Every clipped state and non-finite
rollout is reported. A method with any guard activation cannot be described as numerically reliable,
even when its guarded error remains finite.

The primary adaptation budget is five minutes. One- and fifteen-minute budgets are mechanical
sensitivity analyses and cannot replace the primary result. For budget comparability, each of the
60, 300, and 900 s budgets is followed by exactly 600 hidden-label rollout seconds; the primary
300 s endpoint remains the separate 1,200 s test. Source fitting uses at most the first 60 min of
each train profile, with equal total regression weight per profile.

## Locked models

The comparison set is fixed before outcomes: initial-state persistence, boundary-shift persistence,
source ridge ARX, a raw-unit positive thermal network, a dimensionless-loss positive thermal
network, target-only prefix fitting, source-prior prefix calibration, and a source thermal network
with histogram-gradient residual correction. Hyperparameters and the source-prior penalty are
selected only on the 11 source-validation profiles.

The positive thermal network predicts each node's one-second increment from nonnegative effective
couplings to the other nodes and the two boundary temperatures, plus nonnegative current-, voltage-,
mechanical-power-, and speed-derived heat proxies. The source-prior method fits the same parameter
vector on the commissioning prefix with a nonnegative quadratic penalty toward the source estimate.
This is a reduced-order grey-box model; it is not claimed to identify unique physical resistances or
capacitances.

All positive networks use SciPy bounded least squares with tolerance `1e-10`, at most 2,000
iterations, and no intercept. The ridge ARX predicts the same one-second increments with an
intercept. The fixed residual comparator uses `HistGradientBoostingRegressor` with learning rate
0.05, 200 iterations, 15 leaves, minimum leaf size 50, L2 penalty 1.0, and seed 20260821. Inputs at
second `t` update the state observed or predicted at `t-1`, matching the published external LPTN's
Euler alignment.

## Uncertainty, support, and statistics

For each method and node, each source-validation profile contributes one score: the maximum
absolute closed-loop error over the declared trajectory. Eleven profiles permit a finite 90%
split-conformal trajectory band using rank 11, the maximum calibration score. Exchangeability is
only a working profile-level assumption within the source machine. Applying the band to the external
machine is a stress test with no cross-machine coverage guarantee.

Support is determined without target temperature labels. Median and 95th-percentile summaries of
the first five minutes of electrical, mechanical, coolant, and ambient variables are robust-scaled
from source-train profiles. The threshold is the 95th percentile of source leave-one-profile-out
nearest-neighbour distances. Unsupported profiles remain in every primary summary; rejection cannot
be used to conceal external error.

Method differences use 10,000 paired bootstrap resamples of complete profiles with seed 20260821.
Holm correction is applied within declared comparison families. Primary reporting includes
profile-macro RMSE/MAE, worst-profile error, per-node errors, simultaneous band coverage and width,
support incidence, and any numerical rollout failure.

## Gates and non-negotiable failure reporting

The source and external adaptation gates each require at least a 10% profile-macro RMSE reduction
against the frozen normalized source thermal network and a paired-bootstrap improvement interval
whose lower bound is positive. The source uncertainty gate requires at least 0.80 empirical
simultaneous-in-time trajectory coverage for every node (equivalently, the minimum of the three
node-wise coverages is at least 0.80). A failed gate remains a failed result; neither the endpoint,
method, prefix, horizon, node mapping, nor comparator may be replaced after reveal.

The intended final paper is publishable as a positive adaptation result or as a rigorous negative
transport study. It may not claim cross-fleet generalization, exact PM/rotor equivalence, formal
cross-machine conformal validity, or state of the art.
