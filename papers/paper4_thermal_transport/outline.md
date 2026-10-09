# Paper 4 outline

## Working title

**Do Electrothermal Models Transport Across PMSMs? A Protocol-Frozen Benchmark of Source Priors,
Five-Minute Calibration, and Support-Aware Uncertainty**

## One-sentence answer

A low-order raw-unit thermal network was accurate on held-out profiles of its source PMSM but lost
more than an order of magnitude in RMSE on a second machine; five-minute source-prior calibration
helped only inside a narrow predeclared support region, while target-only fitting was safer across
all external profiles.

## Results spine

1. Data contract and frozen profile-level protocol across two public PMSMs.
2. Strong within-machine raw thermal model: 1.8673 °C profile-macro RMSE.
3. Direct transport failure: 24.4928 °C external RMSE and 1/16 joint trajectory coverage.
4. Source-prior conditionality: external normalized-baseline gate passes arithmetically, but the
   method is worse than target-only/persistence overall and activates 999 guard events on one
   rejected profile.
5. Support-aware result: 3.1933 °C on 6 supported external profiles versus 19.8607 °C on 10 rejected
   profiles; abstention rate 62.5% prevents a broad deployment claim.
6. Uncertainty caveat: coverage can be achieved with a 106.07 °C mean half-width and is therefore
   not sufficient evidence of usefulness.
7. Budget result: target-only fitting reaches about 2.07 °C external RMSE after a 15-minute prefix
   on a common 10-minute horizon, without guard activation.

## Contribution boundary

- Empirical transport protocol and failure evidence, not a new architecture claim.
- Two physical machines only; profiles are the statistical units.
- Rotor is a semantic proxy for source PM temperature.
- Full all-profile outcomes remain primary; support-accepted results are secondary.
- Negative source gate and numerical failures are retained in title, abstract, tables, and figures.

