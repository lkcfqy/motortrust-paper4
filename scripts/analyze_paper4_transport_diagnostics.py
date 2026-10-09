"""Post-reveal diagnostics for the frozen Paper 4 thermal experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from pmsm_sci.thermal_evaluation import paired_profile_bootstrap

PROPOSED = "source_prior_prefix_calibrated_thermal_network"
SOURCE_NORMALIZED = "source_positive_thermal_network_normalized"
SOURCE_RAW = "source_positive_thermal_network_raw"
TARGET_ONLY = "target_only_prefix_positive_thermal_network"
PERSISTENCE = "initial_state_persistence"
ORACLE = "published_target_specific_lptn_estimates"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=Path("results/paper4_thermal_transport")
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/paper4_transport_diagnostics"),
    )
    return parser.parse_args()


def matched_macro(errors: pd.DataFrame) -> pd.DataFrame:
    return errors.loc[
        errors["role"].isin(["source_test", "external_test"])
        & errors["horizon"].eq("matched_20min")
        & errors["node"].eq("macro")
    ].copy()


def support_stratified_summary(errors: pd.DataFrame, support: pd.DataFrame) -> pd.DataFrame:
    merged = matched_macro(errors).merge(
        support[["dataset", "role", "profile_id", "support_distance", "supported"]],
        on=["dataset", "role", "profile_id"],
        validate="many_to_one",
    )
    return (
        merged.groupby(["dataset", "role", "supported", "method"], sort=True)
        .agg(
            profiles=("profile_id", "nunique"),
            mean_rmse_c=("rmse_c", "mean"),
            median_rmse_c=("rmse_c", "median"),
            worst_rmse_c=("rmse_c", "max"),
            total_clip_count=("clip_count", "sum"),
            mean_support_distance=("support_distance", "mean"),
        )
        .reset_index()
    )


def adaptation_differences(errors: pd.DataFrame, support: pd.DataFrame) -> pd.DataFrame:
    selected = matched_macro(errors)
    wide = selected.pivot(
        index=["dataset", "role", "profile_id"], columns="method", values="rmse_c"
    ).reset_index()
    wide = wide.merge(
        support[["dataset", "role", "profile_id", "support_distance", "supported"]],
        on=["dataset", "role", "profile_id"],
        validate="one_to_one",
    )
    wide["normalized_source_minus_proposed_c"] = wide[SOURCE_NORMALIZED] - wide[PROPOSED]
    wide["target_only_minus_proposed_c"] = wide[TARGET_ONLY] - wide[PROPOSED]
    wide["persistence_minus_proposed_c"] = wide[PERSISTENCE] - wide[PROPOSED]
    return wide


def supported_external_comparisons(differences: pd.DataFrame) -> pd.DataFrame:
    external = differences.loc[
        differences["dataset"].eq("external_ipmsm") & differences["supported"]
    ]
    rows = []
    for baseline in (SOURCE_NORMALIZED, TARGET_ONLY, PERSISTENCE, ORACLE):
        result = paired_profile_bootstrap(
            external[baseline].to_numpy(float), external[PROPOSED].to_numpy(float)
        )
        rows.append(
            {
                "subset": "external_supported",
                "profiles": len(external),
                "baseline": baseline,
                "candidate": PROPOSED,
                "baseline_mean_rmse_c": float(external[baseline].mean()),
                "candidate_mean_rmse_c": float(external[PROPOSED].mean()),
                **result,
            }
        )
    return pd.DataFrame(rows)


def transport_degradation(errors: pd.DataFrame) -> pd.DataFrame:
    selected = matched_macro(errors)
    means = (
        selected.groupby(["dataset", "method"], sort=True)["rmse_c"].mean().unstack("dataset")
    )
    methods = means.dropna().index
    result = means.loc[methods].reset_index()
    result["external_minus_source_c"] = (
        result["external_ipmsm"] - result["primary_52kw"]
    )
    result["external_to_source_ratio"] = (
        result["external_ipmsm"] / result["primary_52kw"]
    )
    return result.rename(
        columns={
            "primary_52kw": "source_test_mean_rmse_c",
            "external_ipmsm": "external_test_mean_rmse_c",
        }
    )


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    errors = pd.read_csv(args.results_dir / "per_profile_errors.csv")
    support = pd.read_csv(args.results_dir / "support_scores.csv")
    bands = pd.read_csv(args.results_dir / "trajectory_band_summary.csv")
    gates = json.loads((args.results_dir / "predeclared_gates.json").read_text())

    stratified = support_stratified_summary(errors, support)
    stratified.to_csv(args.output_dir / "support_stratified_summary.csv", index=False)
    differences = adaptation_differences(errors, support)
    differences.to_csv(args.output_dir / "adaptation_profile_differences.csv", index=False)
    supported_comparisons = supported_external_comparisons(differences)
    supported_comparisons.to_csv(
        args.output_dir / "supported_external_comparisons.csv", index=False
    )
    degradation = transport_degradation(errors)
    degradation.to_csv(args.output_dir / "transport_degradation.csv", index=False)

    guard_events = matched_macro(errors).loc[
        lambda frame: frame["clip_count"].gt(0) | frame["nonfinite_count"].gt(0)
    ]
    guard_events.to_csv(args.output_dir / "numerical_guard_events.csv", index=False)

    external = differences.loc[differences["dataset"].eq("external_ipmsm")]
    source = differences.loc[differences["dataset"].eq("primary_52kw")]
    supported_external = external.loc[external["supported"]]
    unsupported_external = external.loc[~external["supported"]]
    proposed_bands = bands.loc[
        bands["method"].eq(PROPOSED) & bands["horizon"].eq("matched_20min")
    ]
    raw_external_joint = pd.read_csv(
        args.results_dir / "trajectory_band_joint_summary.csv"
    ).loc[
        lambda frame: frame["dataset"].eq("external_ipmsm")
        & frame["method"].eq(SOURCE_RAW)
        & frame["horizon"].eq("matched_20min")
    ]

    raw_transport = degradation.loc[degradation["method"].eq(SOURCE_RAW)].iloc[0]
    interpretation = {
        "analysis_status": "post_reveal_diagnostic_without_refitting_or_rethresholding",
        "direct_raw_source_transport": {
            "source_mean_rmse_c": float(raw_transport["source_test_mean_rmse_c"]),
            "external_mean_rmse_c": float(raw_transport["external_test_mean_rmse_c"]),
            "external_to_source_ratio": float(raw_transport["external_to_source_ratio"]),
            "external_joint_band_coverage": float(raw_external_joint["empirical_coverage"].iloc[0]),
        },
        "source_prior_adaptation": {
            "source_gate": gates["source_adaptation"],
            "external_gate": gates["external_adaptation"],
            "source_mean_improvement_c": float(
                source["normalized_source_minus_proposed_c"].mean()
            ),
            "external_mean_improvement_c": float(
                external["normalized_source_minus_proposed_c"].mean()
            ),
            "external_supported_profiles": len(supported_external),
            "external_unsupported_profiles": len(unsupported_external),
            "supported_proposed_mean_rmse_c": float(supported_external[PROPOSED].mean()),
            "unsupported_proposed_mean_rmse_c": float(unsupported_external[PROPOSED].mean()),
            "supported_target_only_mean_rmse_c": float(supported_external[TARGET_ONLY].mean()),
            "unsupported_clip_count": int(
                guard_events.loc[
                    guard_events["dataset"].eq("external_ipmsm")
                    & guard_events["method"].eq(PROPOSED),
                    "clip_count",
                ].sum()
            ),
        },
        "uncertainty": {
            "coverage_gate": gates["source_uncertainty"],
            "proposed_mean_matched_half_width_c": float(
                proposed_bands["half_width_c"].mean()
            ),
            "interpretation": "coverage passes but the band is operationally very wide",
        },
        "claim_boundary": [
            "No model or threshold changed after reveal.",
            "Supported-subset results are secondary and retain only 6 of 16 external profiles.",
            "The external gate alone does not establish numerical reliability.",
            "Two physical machines cannot support fleet-population inference.",
        ],
    }
    (args.output_dir / "interpretation.json").write_text(
        json.dumps(interpretation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(interpretation, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

