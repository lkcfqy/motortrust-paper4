# Paper 4 figure contracts

All figures are static Matplotlib exports for a journal manuscript, delivered as 300 dpi PNG and
vector PDF. The palette uses one blue root for frozen/reference evidence, one orange root for the
source-prior focal method, and neutral grey/black for context. Filled versus open markers and solid
versus dashed lines preserve meaning in grayscale.

## Figure 1: matched-horizon method performance

- Analytical question: How do complete-profile errors change from the source test to the external
  machine, and where do numerical guard events occur?
- Takeaway: the raw source network is accurate in-machine but fails in transport; the proposed
  method is heterogeneous and not competitive all-profile, while target-only prefix fitting is
  stable.
- Family/variant: comparison and distribution; two-panel horizontal profile strip plot on a shared
  logarithmic RMSE axis, with arithmetic means as diamonds.
- Data: 14 source-test profiles, 16 external profiles, 20 min hidden-label rollout after 5 min
  commissioning; one point per physical profile and method.
- Non-color distinction: focal orange diamond/points, open circles for numerical guard profiles,
  neutral target-specific oracle, direct method labels.
- Outputs: `paper4_transport_performance.{png,pdf}`.

## Figure 2: support distance and adaptation effect

- Analytical question: Does the predeclared source-support flag separate useful from harmful
  source-prior adaptation?
- Takeaway: all six supported external profiles improve over the frozen normalized source model;
  ten of sixteen profiles are rejected, and support does not make the source-machine effect
  uniformly positive.
- Family/variant: relationship; source/external scatter, one point per profile.
- Axes: source-support distance versus frozen-normalized RMSE minus proposed RMSE; positive is
  improvement. The frozen support threshold and zero-improvement reference are explicit.
- Non-color distinction: filled supported markers, open unsupported markers, labels for guard-event
  profiles and selected extremes.
- Outputs: `paper4_support_adaptation.{png,pdf}`.

## Figure 3: commissioning-budget sensitivity

- Analytical question: How do 1, 5, and 15 minutes of labels change frozen, target-only, and
  source-prior performance over a common subsequent 10-minute rollout?
- Takeaway: longer target prefixes improve both fitted models; 15-minute target-only fitting is the
  most stable aggregate, so the source prior is not uniformly beneficial.
- Family/variant: ordered comparison; two-panel line-dot chart with profile-mean RMSE and 95% paired
  profile-bootstrap intervals.
- Data: identical physical profile sets within each dataset and budget; 14 source, 16 external.
- Non-color distinction: line styles and marker shapes in addition to color.
- Outputs: `paper4_budget_sensitivity.{png,pdf}`.

## Figure 4: trajectory coverage versus width

- Analytical question: Does nominal-looking coverage remain informative after accounting for band
  width?
- Takeaway: the proposed band attains coverage with a mean half-width above 100 °C, whereas the sharp
  raw-source band transports to only one of sixteen external profiles.
- Family/variant: uncertainty/benchmark scatter; joint all-node trajectory coverage versus mean
  node half-width, faceted by source/external test.
- References: 0.90 nominal coverage line; direct method abbreviations.
- Outputs: `paper4_uncertainty_tradeoff.{png,pdf}`.

## Figure 5: representative and failure trajectories

- Analytical question: What does conditional success and numerical failure look like in time?
- Selection rule: the supported row is the external profile with minimum predeclared support
  distance; the failure row is the external profile that activated the proposed method's numerical
  guard. The latter is explicitly post-reveal failure selection.
- Family/variant: six small-multiple time-series panels (two profiles by three nodes).
- Series: measured temperature, proposed source-prior calibration, target-only prefix fit, and raw
  frozen source network; the 5-minute commissioning boundary is the plotted time origin.
- Outputs: `paper4_external_trajectories.{png,pdf}`.

## QA requirements

Every panel must state units and sample count, preserve a visible zero/reference where relevant,
avoid clipped labels, and keep method encoding consistent. PNGs are visually inspected at final
resolution; PDFs are re-rendered with Poppler and checked for identical layout. Exact numbers remain
available in the manuscript tables and source CSV files rather than being forced into every mark.

