"""Build the Paper 4 supplementary material from frozen result tables."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results/paper4_thermal_transport"
DIAGNOSTICS = ROOT / "results/paper4_transport_diagnostics"
CONFIG = ROOT / "configs/paper4_thermal_transport.yaml"
OUTPUT = ROOT / "papers/paper4_thermal_transport/supplementary_material.md"

METHOD_LABELS = {
    "initial_state_persistence": "Initial-state persistence",
    "boundary_shift_persistence": "Boundary-shift persistence",
    "source_ridge_arx": "Source Ridge ARX",
    "source_positive_thermal_network_raw": "Raw source thermal network",
    "source_positive_thermal_network_normalized": "Normalized source thermal network",
    "target_only_prefix_positive_thermal_network": "Target-only prefix network",
    "source_prior_prefix_calibrated_thermal_network": "Source-prior prefix network",
    "source_thermal_network_plus_hist_gradient_residual": "Source thermal + residual",
    "published_target_specific_lptn_estimates": "Published target-specific LPTN",
}


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def clean(value: str) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| " + " | ".join(clean(value) for value in headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend(
        "| " + " | ".join(clean(value) for value in row) + " |" for row in rows
    )
    return "\n".join(lines)


def _f(value: object, digits: int = 3) -> str:
    return f"{float(value):.{digits}f}"


def _method(value: object) -> str:
    return METHOD_LABELS.get(str(value), str(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_content(root: Path = ROOT) -> str:
    results = root / "results/paper4_thermal_transport"
    diagnostics = root / "results/paper4_transport_diagnostics"
    config_path = root / "configs/paper4_thermal_transport.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    aggregate = pd.read_csv(results / "aggregate_summary.csv")
    tuning = pd.read_csv(results / "validation_tuning.csv")
    comparisons = pd.read_csv(results / "paired_method_comparisons.csv")
    budget = pd.read_csv(results / "budget_sensitivity_summary.csv")
    bands = pd.read_csv(results / "trajectory_band_summary.csv")
    joint = pd.read_csv(results / "trajectory_band_joint_summary.csv")
    support_scores = pd.read_csv(results / "support_scores.csv")
    support_summary = pd.read_csv(diagnostics / "support_stratified_summary.csv")
    guards = pd.read_csv(diagnostics / "numerical_guard_events.csv")
    metadata = json.loads((results / "run_metadata.json").read_text(encoding="utf-8"))

    source_ids = config["source_roles"]
    primary = aggregate.loc[
        aggregate["horizon"].eq("matched_20min")
        & aggregate["node"].eq("macro")
        & aggregate["role"].isin(["source_test", "external_test"])
    ]
    source_rows = primary.loc[primary["role"].eq("source_test")].set_index("method")
    external_rows = primary.loc[primary["role"].eq("external_test")].set_index("method")
    method_order = list(config["methods"]["locked"])
    performance_rows: list[list[str]] = []
    for method in method_order:
        source = source_rows.loc[method]
        external = external_rows.loc[method]
        performance_rows.append(
            [
                _method(method),
                _f(source["mean_rmse_c"]),
                _f(source["median_rmse_c"]),
                _f(source["worst_profile_rmse_c"]),
                str(int(source["total_clip_count"])),
                _f(external["mean_rmse_c"]),
                _f(external["median_rmse_c"]),
                _f(external["worst_profile_rmse_c"]),
                str(int(external["total_clip_count"])),
            ]
        )
    oracle = external_rows.loc["published_target_specific_lptn_estimates"]
    performance_rows.append(
        [
            "Published target-specific LPTN (context)",
            "--",
            "--",
            "--",
            "--",
            _f(oracle["mean_rmse_c"]),
            _f(oracle["median_rmse_c"]),
            _f(oracle["worst_profile_rmse_c"]),
            str(int(oracle["total_clip_count"])),
        ]
    )

    node_methods = {
        "source_positive_thermal_network_raw",
        "source_positive_thermal_network_normalized",
        "target_only_prefix_positive_thermal_network",
        "source_prior_prefix_calibrated_thermal_network",
    }
    node_rows: list[list[str]] = []
    for _, row in aggregate.loc[
        aggregate["horizon"].eq("matched_20min")
        & aggregate["role"].isin(["source_test", "external_test"])
        & aggregate["node"].ne("macro")
        & aggregate["method"].isin(node_methods)
    ].sort_values(["role", "method", "node"]).iterrows():
        node_rows.append(
            [
                "Source" if row["role"] == "source_test" else "External",
                _method(row["method"]),
                str(row["node"]).replace("temp_", "").replace("_", " ").title(),
                _f(row["mean_rmse_c"]),
                _f(row["mean_mae_c"]),
                _f(row["mean_max_abs_c"]),
                str(int(row["total_clip_count"])),
            ]
        )

    tuning_rows = [
        [
            str(row["family"]).replace("_", " ").title(),
            str(row["candidate"]),
            _f(row["validation_profile_macro_rmse_c"]),
            str(int(row["clip_count"])),
            "yes" if bool(row["selected"]) else "no",
        ]
        for _, row in tuning.iterrows()
    ]

    paired_rows = [
        [
            "Source" if row["role"] == "source_test" else "External",
            str(row["horizon"]).replace("_", " "),
            _method(row["baseline"]),
            _f(row["baseline_mean_rmse_c"]),
            _f(row["candidate_mean_rmse_c"]),
            _f(row["improvement_c"]),
            f"[{_f(row['ci_low_c'])}, {_f(row['ci_high_c'])}]",
            _f(row["holm_p"], 4),
        ]
        for _, row in comparisons.iterrows()
    ]

    budget_rows = [
        [
            "Source" if row["role"] == "source_test" else "External",
            str(int(row["budget_seconds"] // 60)),
            _method(row["method"]),
            _f(row["mean_macro_rmse_c"]),
            _f(row["median_macro_rmse_c"]),
            _f(row["worst_macro_rmse_c"]),
            str(int(row["total_clip_count"])),
        ]
        for _, row in budget.sort_values(["role", "budget_seconds", "method"]).iterrows()
    ]

    joint_index = joint.loc[joint["horizon"].eq("matched_20min")].set_index(
        ["role", "method"]
    )
    band_rows: list[list[str]] = []
    for _, row in bands.loc[
        bands["horizon"].eq("matched_20min")
        & bands["role"].isin(["source_test", "external_test"])
    ].sort_values(["role", "method", "node"]).iterrows():
        if row["method"] not in method_order:
            continue
        joint_row = joint_index.loc[(row["role"], row["method"])]
        band_rows.append(
            [
                "Source" if row["role"] == "source_test" else "External",
                _method(row["method"]),
                str(row["node"]).replace("temp_", "").replace("_", " ").title(),
                _f(row["half_width_c"]),
                f"{int(row['covered'])}/{int(row['profiles'])}",
                f"{int(joint_row['covered'])}/{int(joint_row['profiles'])}",
            ]
        )

    external_support = support_scores.loc[
        support_scores["role"].eq("external_test")
    ].sort_values("profile_id")
    support_profile_rows = [
        [
            str(row["profile_id"]),
            _f(row["support_distance"]),
            _f(row["support_threshold"]),
            "supported" if bool(row["supported"]) else "rejected",
            str(row["nearest_source_profile"]),
        ]
        for _, row in external_support.iterrows()
    ]

    support_methods = {
        "boundary_shift_persistence",
        "source_positive_thermal_network_raw",
        "source_positive_thermal_network_normalized",
        "target_only_prefix_positive_thermal_network",
        "source_prior_prefix_calibrated_thermal_network",
        "published_target_specific_lptn_estimates",
    }
    support_aggregate_rows = [
        [
            "accepted" if bool(row["supported"]) else "rejected",
            _method(row["method"]),
            str(int(row["profiles"])),
            _f(row["mean_rmse_c"]),
            _f(row["median_rmse_c"]),
            _f(row["worst_rmse_c"]),
            str(int(row["total_clip_count"])),
        ]
        for _, row in support_summary.loc[
            support_summary["dataset"].eq("external_ipmsm")
            & support_summary["method"].isin(support_methods)
        ].sort_values(["supported", "method"], ascending=[False, True]).iterrows()
    ]

    guard_rows = [
        [
            "Source" if row["role"] == "source_test" else "External",
            str(row["profile_id"]),
            _method(row["method"]),
            _f(row["rmse_c"]),
            _f(row["max_abs_c"]),
            str(int(row["clip_count"])),
        ]
        for _, row in guards.iterrows()
    ]

    hash_rows = [
        ["Protocol configuration", metadata["protocol_config_sha256"]],
        ["Protocol document", metadata["protocol_document_sha256"]],
        ["Selection freeze", metadata["selection_freeze_sha256"]],
        ["Source raw CSV", metadata["primary_data_sha256"]],
        ["External repository commit", metadata["external_repository_commit"]],
    ]
    hash_rows.extend(
        [f"Result: {name}", digest]
        for name, digest in sorted(metadata["output_sha256"].items())
    )

    return f"""# Supplementary material

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

- train (44): {', '.join(map(str, source_ids['train_profiles']))};
- validation (11): {', '.join(map(str, source_ids['validation_profiles']))};
- locked test (14): {', '.join(map(str, source_ids['locked_test_profiles']))}.

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

{_markdown_table(['Family', 'Candidate', 'Validation RMSE', 'Clips', 'Selected'], tuning_rows)}

The frozen values were Ridge alpha 100 and source-prior penalty 0.1. The selected model bundle,
coefficient table, validation table, configuration, and selection metadata were written before the
locked outcomes. A later fast tree-traversal implementation changed only inference speed for the
already fitted histogram residual comparator; it matched public scikit-learn predictions to
absolute tolerance 10⁻¹⁴ and preceded any test outcome.

# S4. Complete matched-horizon method results

The table contains every locked method. Mean, median, and worst values are complete-profile macro
RMSE. The published LPTN row is external context only because it uses target-specific development
information unavailable to the target-blind methods.

{_markdown_table(['Method', 'Source mean', 'Source median', 'Source worst', 'Source clips', 'External mean', 'External median', 'External worst', 'External clips'], performance_rows)}

The raw source network's 1.867 °C source error and 24.493 °C external error give a 13.1167-fold
transport degradation. The source-prior method's external median (4.291 °C) is much smaller than
its mean (13.610 °C) because profile 14 is catastrophic. Therefore medians alone would conceal a
deployment failure.

## S4.1 Per-node results for the principal thermal models

{_markdown_table(['Dataset', 'Method', 'Node', 'Mean RMSE', 'Mean MAE', 'Mean max error', 'Clips'], node_rows)}

Source permanent-magnet and external rotor temperatures are displayed under the common “Rotor”
label only for the frozen semantic bridge. The large raw-model external winding error should not be
interpreted as a controlled estimate of sensor-location effects.

## S4.2 Complete source-prior paired comparisons

Positive improvement means the candidate source-prior method has lower RMSE than the named
baseline. Intervals and Holm-adjusted values are profile-level descriptions; they do not provide
machine-population inference.

{_markdown_table(['Dataset', 'Horizon', 'Baseline', 'Baseline RMSE', 'Prior RMSE', 'Improvement', '95% interval', 'Holm p'], paired_rows)}

# S5. Commissioning-label budget

Every budget is followed by the same 600-s hidden-label rollout. This prevents later budgets from
receiving an easier endpoint merely because their remaining profile segment is shorter. The
five-minute values here use a 10-minute rollout and therefore differ from the primary five-minute,
20-minute endpoint.

{_markdown_table(['Dataset', 'Prefix (min)', 'Method', 'Mean RMSE', 'Median RMSE', 'Worst RMSE', 'Clips'], budget_rows)}

The 15-minute target-only result is the lowest average error on both recorded machines and has no
guard activation. This does not establish an optimal universal budget; it shows that the source
prior was not needed once these prefixes supplied sufficient local transitions.

# S6. Complete trajectory-band audit

Each source-validation profile contributed one maximum absolute error per node. With 11 calibration
profiles and nominal 90% coverage, rank 11—the maximum calibration score—sets the constant
half-width. “Node coverage” means every second for the named node was inside its band. “Joint” means
all three nodes and all seconds were covered. External values are stress-test outcomes without a
cross-machine guarantee.

{_markdown_table(['Dataset', 'Method', 'Node', 'Half-width', 'Node coverage', 'Joint coverage'], band_rows)}

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

{_markdown_table(['External profile', 'Distance', 'Threshold', 'Decision', 'Nearest source profile'], support_profile_rows)}

Six profiles were accepted and ten rejected. This 62.5% abstention rate is reported beside the
accepted-subset accuracy and prevents the subset from replacing the all-profile result.

## S7.2 Support-stratified performance

{_markdown_table(['Subset', 'Method', 'Profiles', 'Mean RMSE', 'Median RMSE', 'Worst RMSE', 'Clips'], support_aggregate_rows)}

On accepted profiles, source-prior calibration has 3.193 °C RMSE versus 4.565 °C for target-only
fitting. On rejected profiles, the corresponding errors are 19.861 and 6.889 °C. All 999 external
source-prior clips occur in the rejected subset. This supports further prospective study of gated
priors, but one external machine and six accepted profiles cannot certify a deployment rule.

# S8. Numerical guard events

The following are all primary matched-horizon profile/method combinations with at least one clip.
No non-finite prediction occurred. Macro RMSE and maximum absolute error are averages across the
three nodes for the profile; clip count is accumulated over node-seconds.

{_markdown_table(['Dataset', 'Profile', 'Method', 'Macro RMSE', 'Macro max error', 'Clips'], guard_rows)}

Clipping prevents unbounded values from corrupting files; it is not a stability remedy. The guarded
errors remain in all rankings. The unedited external profile-14 source-prior trajectory reaches the
250 °C ceiling in winding and stator-core states and exceeds 200 °C in rotor prediction while the
recorded states remain near ordinary temperatures.

# S9. Reproducibility and immutable identifiers

{_markdown_table(['Artifact', 'SHA-256 or commit'], hash_rows)}

The audit records Python {metadata['python']}, NumPy {metadata['numpy']}, pandas
{metadata['pandas']}, SciPy {metadata['scipy']}, and scikit-learn
{metadata['scikit_learn']}. The evidence validator recomputes the raw-data, protocol, configuration,
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

"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    content = build_content()
    if args.check:
        if not OUTPUT.is_file():
            raise FileNotFoundError(OUTPUT)
        existing = OUTPUT.read_text(encoding="utf-8")
        if existing != content:
            raise AssertionError("Paper 4 supplementary material is stale")
        print(f"current: {OUTPUT} ({_sha256(OUTPUT)})")
        return
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT} ({_sha256(OUTPUT)})")


if __name__ == "__main__":
    main()
