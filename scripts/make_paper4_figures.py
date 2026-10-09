"""Create the five protocol-aligned Paper 4 submission figures."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROPOSED = "source_prior_prefix_calibrated_thermal_network"
SOURCE_NORMALIZED = "source_positive_thermal_network_normalized"
SOURCE_RAW = "source_positive_thermal_network_raw"
TARGET_ONLY = "target_only_prefix_positive_thermal_network"
RIDGE = "source_ridge_arx"
HYBRID = "source_thermal_network_plus_hist_gradient_residual"
PERSISTENCE = "initial_state_persistence"
BOUNDARY = "boundary_shift_persistence"
ORACLE = "published_target_specific_lptn_estimates"

METHOD_ORDER = (
    SOURCE_RAW,
    SOURCE_NORMALIZED,
    RIDGE,
    HYBRID,
    PROPOSED,
    TARGET_ONLY,
    PERSISTENCE,
    BOUNDARY,
    ORACLE,
)

METHOD_LABELS = {
    SOURCE_RAW: "Frozen thermal net (raw)",
    SOURCE_NORMALIZED: "Frozen thermal net (norm.)",
    RIDGE: "Source Ridge ARX",
    HYBRID: "Source thermal + residual",
    PROPOSED: "Source-prior calibration",
    TARGET_ONLY: "Target-only prefix",
    PERSISTENCE: "Initial-state persistence",
    BOUNDARY: "Boundary persistence",
    ORACLE: "Published target LPTN",
}

METHOD_ABBREVIATIONS = {
    SOURCE_RAW: "Raw",
    SOURCE_NORMALIZED: "Norm",
    RIDGE: "Ridge",
    HYBRID: "Hybrid",
    PROPOSED: "Prior",
    TARGET_ONLY: "Target",
    PERSISTENCE: "Persist",
    BOUNDARY: "Boundary",
}

BLUE = "#2F6690"
BLUE_LIGHT = "#8DB3CF"
ORANGE = "#D97706"
GREY = "#8A9199"
LIGHT_GREY = "#D6DADE"
DARK = "#22262B"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir", type=Path, default=Path("results/paper4_thermal_transport")
    )
    parser.add_argument(
        "--diagnostics-dir",
        type=Path,
        default=Path("results/paper4_transport_diagnostics"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("papers/paper4_thermal_transport/figures")
    )
    return parser.parse_args()


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9,
            "axes.edgecolor": "#555B61",
            "axes.linewidth": 0.8,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def method_color(method: str) -> str:
    if method == PROPOSED:
        return ORANGE
    if method in {SOURCE_RAW, TARGET_ONLY}:
        return BLUE
    if method == ORACLE:
        return DARK
    return GREY


def save_figure(figure: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_dir / f"{stem}.png", dpi=300, bbox_inches="tight")
    figure.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(figure)


def make_performance_figure(errors: pd.DataFrame, output_dir: Path) -> None:
    data = errors.loc[
        errors["role"].isin(["source_test", "external_test"])
        & errors["horizon"].eq("matched_20min")
        & errors["node"].eq("macro")
    ]
    figure, axes = plt.subplots(1, 2, figsize=(11.0, 5.2), sharex=True, sharey=True)
    panels = (
        ("primary_52kw", "Source test: one 52 kW PMSM (14 profiles)"),
        ("external_ipmsm", "External test: second IPMSM (16 profiles)"),
    )
    for axis, (dataset, title) in zip(axes, panels, strict=True):
        subset = data.loc[data["dataset"].eq(dataset)]
        methods = [method for method in METHOD_ORDER if method in set(subset["method"])]
        for position, method in enumerate(methods):
            values = subset.loc[subset["method"].eq(method)].sort_values("profile_id")
            jitter = ((values["profile_id"].to_numpy() * 17) % 19 - 9) / 85.0
            guard = values["clip_count"].gt(0) | values["nonfinite_count"].gt(0)
            normal = values.loc[~guard]
            normal_jitter = jitter[~guard.to_numpy()]
            axis.scatter(
                normal["rmse_c"],
                position + normal_jitter,
                s=19,
                color=method_color(method),
                alpha=0.68,
                edgecolor="white",
                linewidth=0.35,
                zorder=2,
            )
            if guard.any():
                axis.scatter(
                    values.loc[guard, "rmse_c"],
                    position + jitter[guard.to_numpy()],
                    s=34,
                    facecolor="none",
                    edgecolor=ORANGE,
                    marker="^",
                    linewidth=1.2,
                    zorder=4,
                )
            axis.scatter(
                [values["rmse_c"].mean()],
                [position],
                marker="D",
                s=48,
                color=method_color(method),
                edgecolor=DARK,
                linewidth=0.7,
                zorder=3,
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xscale("log")
        axis.set_xlim(0.5, 220)
        axis.grid(axis="x", color="#E5E7E9", linewidth=0.7, which="both")
        axis.set_axisbelow(True)
        axis.set_yticks(range(len(methods)))
        axis.set_yticklabels([METHOD_LABELS[method] for method in methods])
        axis.invert_yaxis()
        axis.set_xlabel("Profile-macro RMSE (°C, logarithmic scale)")
    figure.suptitle(
        "Matched-horizon electrothermal prediction error",
        x=0.07,
        y=1.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    figure.text(
        0.07,
        0.955,
        "One point per complete profile; diamonds are arithmetic means. Open triangles mark numerical guard activation.",
        fontsize=9,
        color="#555B61",
    )
    figure.subplots_adjust(left=0.28, right=0.98, bottom=0.12, top=0.87, wspace=0.08)
    save_figure(figure, output_dir, "paper4_transport_performance")


def make_support_figure(
    differences: pd.DataFrame, support_scores: pd.DataFrame, output_dir: Path
) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10.4, 4.3), sharex=True, sharey=True)
    panels = (
        ("primary_52kw", "Source test (n=14)"),
        ("external_ipmsm", "External test (n=16)"),
    )
    for axis, (dataset, title) in zip(axes, panels, strict=True):
        subset = differences.loc[differences["dataset"].eq(dataset)].copy()
        threshold = float(subset["support_distance"].max())
        threshold = float(
            support_scores.loc[
                support_scores["dataset"].eq(dataset)
                & support_scores["role"].isin(["source_test", "external_test"]),
                "support_threshold",
            ].iloc[0]
        )
        supported = subset["supported"]
        axis.scatter(
            subset.loc[supported, "support_distance"],
            subset.loc[supported, "normalized_source_minus_proposed_c"],
            s=44,
            color=BLUE,
            edgecolor=DARK,
            linewidth=0.5,
            label="Supported",
            zorder=3,
        )
        axis.scatter(
            subset.loc[~supported, "support_distance"],
            subset.loc[~supported, "normalized_source_minus_proposed_c"],
            s=48,
            facecolor="white",
            edgecolor=ORANGE,
            linewidth=1.3,
            label="Unsupported",
            zorder=3,
        )
        guard_ids = {11, 45} if dataset == "primary_52kw" else {14}
        labelled = subset.loc[subset["profile_id"].isin(guard_ids)]
        for row in labelled.itertuples(index=False):
            axis.annotate(
                f"P{row.profile_id}",
                (row.support_distance, row.normalized_source_minus_proposed_c),
                xytext=(5, -11),
                textcoords="offset points",
                fontsize=7.5,
                color=DARK,
            )
        axis.axhline(0, color=DARK, linewidth=0.9)
        axis.axvline(threshold, color="#666C72", linewidth=1.0, linestyle="--")
        axis.text(
            threshold + 0.25,
            48,
            "support threshold",
            rotation=90,
            va="top",
            fontsize=7.5,
            color="#666C72",
        )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Distance to nearest source-train profile")
        axis.grid(color="#E7E9EB", linewidth=0.7)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("RMSE improvement: frozen normalized − source-prior (°C)")
    axes[0].set_xlim(0, 26)
    axes[0].set_ylim(-62, 52)
    handles, labels = axes[1].get_legend_handles_labels()
    figure.legend(handles[:2], labels[:2], loc="upper right", frameon=False, ncol=2)
    figure.suptitle(
        "Predeclared support distance and source-prior adaptation effect",
        x=0.08,
        y=1.02,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    figure.text(
        0.08,
        0.955,
        "Positive values favor prefix calibration; labelled profiles are numerical/failure diagnostics.",
        fontsize=9,
        color="#555B61",
    )
    figure.subplots_adjust(left=0.1, right=0.98, bottom=0.15, top=0.84, wspace=0.12)
    save_figure(figure, output_dir, "paper4_support_adaptation")


def bootstrap_budget_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rng = np.random.default_rng(20260821)
    for keys, group in data.groupby(["dataset", "budget_seconds", "method"], sort=True):
        dataset, budget, method = keys
        values = group.sort_values("profile_id")["macro_rmse_c"].to_numpy(float)
        indices = rng.integers(0, len(values), size=(10_000, len(values)))
        means = values[indices].mean(axis=1)
        rows.append(
            {
                "dataset": dataset,
                "budget_seconds": budget,
                "method": method,
                "profiles": len(values),
                "mean_rmse_c": float(values.mean()),
                "ci_low_c": float(np.quantile(means, 0.025)),
                "ci_high_c": float(np.quantile(means, 0.975)),
            }
        )
    return pd.DataFrame(rows)


def make_budget_figure(data: pd.DataFrame, output_dir: Path) -> None:
    summary = bootstrap_budget_summary(data)
    figure, axes = plt.subplots(1, 2, figsize=(9.8, 4.2), sharex=True, sharey=True)
    panels = (
        ("primary_52kw", "Source test (14 profiles)"),
        ("external_ipmsm", "External test (16 profiles)"),
    )
    styles = {
        SOURCE_NORMALIZED: (GREY, "--", "o"),
        TARGET_ONLY: (BLUE, "-", "s"),
        PROPOSED: (ORANGE, "-", "D"),
    }
    for axis, (dataset, title) in zip(axes, panels, strict=True):
        subset = summary.loc[summary["dataset"].eq(dataset)]
        for method in (SOURCE_NORMALIZED, TARGET_ONLY, PROPOSED):
            values = subset.loc[subset["method"].eq(method)].sort_values("budget_seconds")
            color, linestyle, marker = styles[method]
            minutes = values["budget_seconds"] / 60
            axis.errorbar(
                minutes,
                values["mean_rmse_c"],
                yerr=np.vstack(
                    [
                        values["mean_rmse_c"] - values["ci_low_c"],
                        values["ci_high_c"] - values["mean_rmse_c"],
                    ]
                ),
                label=METHOD_LABELS[method],
                color=color,
                linestyle=linestyle,
                marker=marker,
                markersize=5,
                linewidth=1.7,
                capsize=2.5,
            )
        axis.set_yscale("log")
        axis.set_xticks([1, 5, 15])
        axis.set_xlabel("Commissioning labels (min)")
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(color="#E7E9EB", linewidth=0.7, which="both")
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Mean profile-macro RMSE (°C, log scale)")
    axes[0].set_ylim(1.3, 65)
    handles, labels = axes[1].get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper right", frameon=False, ncol=3)
    figure.suptitle(
        "Commissioning-budget sensitivity",
        x=0.08,
        y=1.02,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    figure.text(
        0.08,
        0.955,
        "Means and 95% profile-bootstrap intervals; every budget is followed by the same 10-minute hidden-label rollout.",
        fontsize=9,
        color="#555B61",
    )
    figure.subplots_adjust(left=0.1, right=0.98, bottom=0.15, top=0.82, wspace=0.1)
    save_figure(figure, output_dir, "paper4_budget_sensitivity")


def make_uncertainty_figure(
    bands: pd.DataFrame, joint: pd.DataFrame, output_dir: Path
) -> None:
    matched_bands = bands.loc[bands["horizon"].eq("matched_20min")]
    widths = (
        matched_bands.groupby("method", sort=True)["half_width_c"]
        .mean()
        .reset_index(name="mean_half_width_c")
    )
    data = joint.loc[joint["horizon"].eq("matched_20min")].merge(
        widths, on="method", validate="many_to_one"
    )
    figure, axes = plt.subplots(1, 2, figsize=(10.0, 4.2), sharex=True, sharey=True)
    panels = (
        ("primary_52kw", "Source test (n=14)"),
        ("external_ipmsm", "External test (n=16)"),
    )
    offsets = {
        "Raw": (5, -11),
        "Norm": (5, 4),
        "Ridge": (5, -10),
        "Hybrid": (5, 5),
        "Prior": (-35, 5),
        "Target": (5, -11),
        "Persist": (-38, 4),
        "Boundary": (5, 5),
    }
    for axis, (dataset, title) in zip(axes, panels, strict=True):
        subset = data.loc[data["dataset"].eq(dataset)]
        for row in subset.itertuples(index=False):
            abbreviation = METHOD_ABBREVIATIONS[row.method]
            axis.scatter(
                row.mean_half_width_c,
                row.empirical_coverage,
                s=54 if row.method in {PROPOSED, SOURCE_RAW, TARGET_ONLY} else 35,
                color=method_color(row.method),
                marker="D" if row.method == PROPOSED else "o",
                edgecolor=DARK,
                linewidth=0.5,
                zorder=3,
            )
            axis.annotate(
                abbreviation,
                (row.mean_half_width_c, row.empirical_coverage),
                xytext=offsets[abbreviation],
                textcoords="offset points",
                fontsize=7.5,
            )
        axis.axhline(0.90, color=DARK, linestyle="--", linewidth=1.0)
        axis.text(108, 0.905, "90% target", ha="right", va="bottom", fontsize=7.5)
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Mean trajectory-band half-width across nodes (°C)")
        axis.grid(color="#E7E9EB", linewidth=0.7)
        axis.set_axisbelow(True)
    axes[0].set_ylabel("Joint all-node trajectory coverage")
    axes[0].set_xlim(0, 112)
    axes[0].set_ylim(0, 1.05)
    figure.suptitle(
        "Trajectory coverage–width trade-off",
        x=0.08,
        y=1.02,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    figure.text(
        0.08,
        0.955,
        "Bands use one maximum-error score per source-validation profile; external coverage has no cross-machine guarantee.",
        fontsize=9,
        color="#555B61",
    )
    figure.subplots_adjust(left=0.1, right=0.98, bottom=0.15, top=0.84, wspace=0.12)
    save_figure(figure, output_dir, "paper4_uncertainty_tradeoff")


def make_trajectory_figure(
    trajectories: pd.DataFrame, support: pd.DataFrame, errors: pd.DataFrame, output_dir: Path
) -> None:
    external_support = support.loc[
        support["dataset"].eq("external_ipmsm")
        & support["role"].eq("external_test")
        & support["supported"]
    ]
    supported_profile = int(
        external_support.sort_values(["support_distance", "profile_id"]).iloc[0]["profile_id"]
    )
    guard_profiles = errors.loc[
        errors["dataset"].eq("external_ipmsm")
        & errors["role"].eq("external_test")
        & errors["horizon"].eq("matched_20min")
        & errors["node"].eq("macro")
        & errors["method"].eq(PROPOSED)
        & errors["clip_count"].gt(0),
        "profile_id",
    ]
    if len(guard_profiles) != 1:
        raise ValueError("expected exactly one external proposed guard-event profile")
    failure_profile = int(guard_profiles.iloc[0])
    profiles = (
        (supported_profile, "Nearest supported profile"),
        (failure_profile, "Post-reveal numerical failure"),
    )
    nodes = (
        ("winding", "Winding temperature (°C)"),
        ("stator_core", "Stator-core temperature (°C)"),
        ("rotor", "Rotor temperature (°C)"),
    )
    methods = (SOURCE_RAW, TARGET_ONLY, PROPOSED)
    styles = {
        SOURCE_RAW: (GREY, "--", 1.25),
        TARGET_ONLY: (BLUE, "-", 1.35),
        PROPOSED: (ORANGE, "-", 1.55),
    }
    figure, axes = plt.subplots(2, 3, figsize=(11.2, 6.0), sharex=True)
    for row_index, (profile_id, row_label) in enumerate(profiles):
        profile = trajectories.loc[
            trajectories["dataset"].eq("external_ipmsm")
            & trajectories["profile_id"].eq(profile_id)
        ]
        for column_index, (node, y_label) in enumerate(nodes):
            axis = axes[row_index, column_index]
            truth = profile.loc[profile["method"].eq(PROPOSED)].sort_values("time_second")
            minutes = (truth["time_second"] - 300) / 60
            axis.plot(
                minutes,
                truth[f"true_{node}_c"],
                color=DARK,
                linewidth=1.6,
                label="Measured",
            )
            for method in methods:
                values = profile.loc[profile["method"].eq(method)].sort_values("time_second")
                color, linestyle, width = styles[method]
                axis.plot(
                    minutes,
                    values[f"pred_{node}_c"],
                    color=color,
                    linestyle=linestyle,
                    linewidth=width,
                    label=METHOD_LABELS[method],
                )
            axis.set_title(y_label, loc="left", fontweight="bold")
            axis.grid(color="#E7E9EB", linewidth=0.65)
            axis.set_axisbelow(True)
            if column_index == 0:
                distance = float(
                    support.loc[
                        support["dataset"].eq("external_ipmsm")
                        & support["profile_id"].eq(profile_id),
                        "support_distance",
                    ].iloc[0]
                )
                axis.set_ylabel(f"{row_label}\nProfile {profile_id}; distance {distance:.2f}")
            if row_index == 1:
                axis.set_xlabel("Minutes after commissioning prefix")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="upper right", frameon=False, ncol=4)
    figure.suptitle(
        "External-machine closed-loop trajectories",
        x=0.07,
        y=1.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
    )
    figure.text(
        0.07,
        0.952,
        "The plotted origin follows five minutes of observed target temperatures; subsequent labels are hidden for 20 minutes.",
        fontsize=9,
        color="#555B61",
    )
    figure.subplots_adjust(left=0.12, right=0.99, bottom=0.1, top=0.85, wspace=0.18, hspace=0.28)
    save_figure(figure, output_dir, "paper4_external_trajectories")


def main() -> None:
    args = parse_args()
    configure_style()
    errors = pd.read_csv(args.results_dir / "per_profile_errors.csv")
    support = pd.read_csv(args.results_dir / "support_scores.csv")
    budget = pd.read_csv(args.results_dir / "budget_sensitivity_per_profile.csv")
    bands = pd.read_csv(args.results_dir / "trajectory_bands.csv")
    joint = pd.read_csv(args.results_dir / "trajectory_band_joint_summary.csv")
    trajectories = pd.read_csv(args.results_dir / "trajectory_predictions.csv.gz")
    differences = pd.read_csv(args.diagnostics_dir / "adaptation_profile_differences.csv")

    make_performance_figure(errors, args.output_dir)
    make_support_figure(differences, support, args.output_dir)
    make_budget_figure(budget, args.output_dir)
    make_uncertainty_figure(bands, joint, args.output_dir)
    make_trajectory_figure(trajectories, support, errors, args.output_dir)
    print(f"Wrote five Paper 4 figures to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
