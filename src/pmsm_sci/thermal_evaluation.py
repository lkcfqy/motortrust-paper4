"""Profile-level metrics, uncertainty, and support checks for Paper 4."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from scipy.stats import wilcoxon

from .thermal_models import STATE_COLUMNS

SUPPORT_SIGNALS = (
    "current_magnitude",
    "voltage_magnitude",
    "absolute_speed",
    "absolute_torque",
    "electrical_power_proxy",
    "mechanical_power_proxy",
    "coolant",
    "ambient",
)
SUPPORT_FEATURES = tuple(
    f"{signal}_{statistic}"
    for signal in SUPPORT_SIGNALS
    for statistic in ("median", "p95")
)


@dataclass(frozen=True)
class SupportReference:
    profile_ids: np.ndarray
    summaries: np.ndarray
    center: np.ndarray
    scale: np.ndarray
    threshold: float
    leave_one_out_distances: np.ndarray


def operating_summary(frame: pd.DataFrame, *, prefix_seconds: int = 300) -> np.ndarray:
    """Summarize deployment covariates without accessing temperature targets."""

    prefix = frame.iloc[:prefix_seconds]
    current = np.hypot(prefix["i_d"].to_numpy(float), prefix["i_q"].to_numpy(float))
    voltage = np.hypot(prefix["u_d"].to_numpy(float), prefix["u_q"].to_numpy(float))
    speed = np.abs(prefix["speed_rpm"].to_numpy(float))
    torque = np.abs(prefix["torque_nm"].to_numpy(float))
    electrical = np.abs(
        prefix["u_d"].to_numpy(float) * prefix["i_d"].to_numpy(float)
        + prefix["u_q"].to_numpy(float) * prefix["i_q"].to_numpy(float)
    )
    mechanical = torque * speed * (2.0 * np.pi / 60.0)
    signals = (
        current,
        voltage,
        speed,
        torque,
        electrical,
        mechanical,
        prefix["coolant"].to_numpy(float),
        prefix["ambient"].to_numpy(float),
    )
    values = []
    for signal in signals:
        values.extend([np.median(signal), np.quantile(signal, 0.95)])
    result = np.asarray(values, dtype=float)
    if result.shape != (len(SUPPORT_FEATURES),) or not np.isfinite(result).all():
        raise ValueError("invalid operating-context summary")
    return result


def fit_support_reference(
    profiles: list[pd.DataFrame], *, prefix_seconds: int = 300
) -> SupportReference:
    """Fit the frozen profile-level source-support reference."""

    if len(profiles) < 3:
        raise ValueError("at least three source profiles are required for support")
    profile_ids = np.asarray([int(profile["profile_id"].iloc[0]) for profile in profiles])
    summaries = np.vstack(
        [operating_summary(profile, prefix_seconds=prefix_seconds) for profile in profiles]
    )
    center = np.median(summaries, axis=0)
    mad_scale = 1.4826 * np.median(np.abs(summaries - center), axis=0)
    q25, q75 = np.quantile(summaries, [0.25, 0.75], axis=0)
    iqr_scale = (q75 - q25) / 1.349
    scale = np.where(mad_scale > 1e-12, mad_scale, iqr_scale)
    scale = np.where(scale > 1e-12, scale, 1.0)
    standardized = (summaries - center) / scale
    distances = cdist(standardized, standardized)
    np.fill_diagonal(distances, np.inf)
    leave_one_out = distances.min(axis=1)
    threshold = float(np.quantile(leave_one_out, 0.95, method="higher"))
    return SupportReference(
        profile_ids=profile_ids,
        summaries=summaries,
        center=center,
        scale=scale,
        threshold=threshold,
        leave_one_out_distances=leave_one_out,
    )


def support_score(
    reference: SupportReference,
    frame: pd.DataFrame,
    *,
    prefix_seconds: int = 300,
) -> dict[str, float | int | bool]:
    """Score a complete target profile against source-train prefix support."""

    summary = operating_summary(frame, prefix_seconds=prefix_seconds)
    train = (reference.summaries - reference.center) / reference.scale
    target = ((summary - reference.center) / reference.scale).reshape(1, -1)
    distances = cdist(target, train)[0]
    nearest_index = int(np.argmin(distances))
    distance = float(distances[nearest_index])
    return {
        "support_distance": distance,
        "support_threshold": reference.threshold,
        "supported": bool(distance <= reference.threshold),
        "nearest_source_profile": int(reference.profile_ids[nearest_index]),
    }


def profile_error_rows(
    truth: np.ndarray,
    prediction: np.ndarray,
    *,
    dataset: str,
    role: str,
    profile_id: int,
    method: str,
    horizon: str,
    clip_count: int,
    nonfinite_count: int,
) -> list[dict[str, float | int | str]]:
    """Compute node-specific and macro errors for one physical profile."""

    truth = np.asarray(truth, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    if truth.shape != prediction.shape or truth.ndim != 2 or truth.shape[1] != len(
        STATE_COLUMNS
    ):
        raise ValueError("truth and prediction must be aligned three-node trajectories")
    error = prediction - truth
    rows: list[dict[str, float | int | str]] = []
    node_rmse = []
    node_mae = []
    node_max = []
    for node_index, node in enumerate(STATE_COLUMNS):
        rmse = float(np.sqrt(np.mean(error[:, node_index] ** 2)))
        mae = float(np.mean(np.abs(error[:, node_index])))
        maximum = float(np.max(np.abs(error[:, node_index])))
        node_rmse.append(rmse)
        node_mae.append(mae)
        node_max.append(maximum)
        rows.append(
            {
                "dataset": dataset,
                "role": role,
                "profile_id": profile_id,
                "method": method,
                "horizon": horizon,
                "node": node,
                "rmse_c": rmse,
                "mae_c": mae,
                "max_abs_c": maximum,
                "clip_count": clip_count,
                "nonfinite_count": nonfinite_count,
                "n_seconds": len(truth),
            }
        )
    rows.append(
        {
            "dataset": dataset,
            "role": role,
            "profile_id": profile_id,
            "method": method,
            "horizon": horizon,
            "node": "macro",
            "rmse_c": float(np.mean(node_rmse)),
            "mae_c": float(np.mean(node_mae)),
            "max_abs_c": float(np.mean(node_max)),
            "clip_count": clip_count,
            "nonfinite_count": nonfinite_count,
            "n_seconds": len(truth),
        }
    )
    return rows


def finite_sample_quantile(values: np.ndarray, *, coverage: float) -> tuple[float, int]:
    """Return the split-conformal upper quantile and one-based rank."""

    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or len(values) == 0 or not np.isfinite(values).all():
        raise ValueError("calibration scores must be a finite nonempty vector")
    if not 0 < coverage < 1:
        raise ValueError("coverage must lie strictly between zero and one")
    rank = int(np.ceil((len(values) + 1) * coverage))
    if rank > len(values):
        return float("inf"), rank
    return float(np.sort(values)[rank - 1]), rank


def calibrate_trajectory_bands(
    validation_errors: pd.DataFrame, *, coverage: float = 0.90
) -> pd.DataFrame:
    """Calibrate one simultaneous absolute-error band per method/node/horizon."""

    data = validation_errors.loc[validation_errors["node"].ne("macro")]
    rows = []
    for keys, group in data.groupby(["method", "horizon", "node"], sort=True):
        method, horizon, node = keys
        if group["profile_id"].duplicated().any():
            raise ValueError("each validation profile must contribute one band score")
        threshold, rank = finite_sample_quantile(
            group["max_abs_c"].to_numpy(float), coverage=coverage
        )
        rows.append(
            {
                "method": method,
                "horizon": horizon,
                "node": node,
                "coverage_target": coverage,
                "n_calibration_profiles": len(group),
                "rank": rank,
                "half_width_c": threshold,
            }
        )
    return pd.DataFrame(rows)


def evaluate_trajectory_bands(
    errors: pd.DataFrame, bands: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply frozen bands to profile maximum errors and summarize coverage."""

    node_errors = errors.loc[errors["node"].ne("macro")].copy()
    merged = node_errors.merge(
        bands,
        on=["method", "horizon", "node"],
        how="left",
        validate="many_to_one",
    )
    if merged["half_width_c"].isna().any():
        raise ValueError("missing trajectory band for one or more evaluated rows")
    merged["trajectory_covered"] = merged["max_abs_c"] <= merged["half_width_c"]
    summary = (
        merged.groupby(["dataset", "role", "method", "horizon", "node"], sort=True)
        .agg(
            covered=("trajectory_covered", "sum"),
            profiles=("profile_id", "nunique"),
            empirical_coverage=("trajectory_covered", "mean"),
            half_width_c=("half_width_c", "first"),
        )
        .reset_index()
    )
    return merged, summary


def paired_profile_bootstrap(
    baseline: np.ndarray,
    candidate: np.ndarray,
    *,
    replicates: int = 10_000,
    seed: int = 20260821,
) -> dict[str, float]:
    """Bootstrap profile-mean improvement, defined as baseline minus candidate."""

    baseline = np.asarray(baseline, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if baseline.shape != candidate.shape or baseline.ndim != 1 or len(baseline) < 2:
        raise ValueError("paired profile vectors must have equal one-dimensional shape")
    difference = baseline - candidate
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(difference), size=(replicates, len(difference)))
    bootstrap = difference[indices].mean(axis=1)
    point = float(difference.mean())
    baseline_mean = float(baseline.mean())
    return {
        "improvement_c": point,
        "ci_low_c": float(np.quantile(bootstrap, 0.025)),
        "ci_high_c": float(np.quantile(bootstrap, 0.975)),
        "relative_improvement": point / baseline_mean if baseline_mean != 0 else np.nan,
    }


def paired_method_comparisons(
    errors: pd.DataFrame,
    *,
    candidate_method: str,
    node: str = "macro",
) -> pd.DataFrame:
    """Compare every method with a fixed candidate on aligned physical profiles."""

    selected = errors.loc[errors["node"].eq(node)]
    rows = []
    group_columns = ["dataset", "role", "horizon"]
    for group_keys, group in selected.groupby(group_columns, sort=True):
        dataset, role, horizon = group_keys
        candidate = group.loc[group["method"].eq(candidate_method), ["profile_id", "rmse_c"]]
        if candidate.empty:
            continue
        candidate = candidate.rename(columns={"rmse_c": "candidate_rmse"})
        for method in sorted(set(group["method"]) - {candidate_method}):
            baseline = group.loc[group["method"].eq(method), ["profile_id", "rmse_c"]]
            baseline = baseline.rename(columns={"rmse_c": "baseline_rmse"})
            paired = baseline.merge(candidate, on="profile_id", validate="one_to_one")
            result = paired_profile_bootstrap(
                paired["baseline_rmse"].to_numpy(),
                paired["candidate_rmse"].to_numpy(),
            )
            difference = paired["baseline_rmse"] - paired["candidate_rmse"]
            if np.allclose(difference, 0):
                p_value = 1.0
            else:
                p_value = float(wilcoxon(difference, alternative="two-sided").pvalue)
            rows.append(
                {
                    "dataset": dataset,
                    "role": role,
                    "horizon": horizon,
                    "candidate": candidate_method,
                    "baseline": method,
                    "profiles": len(paired),
                    "baseline_mean_rmse_c": float(paired["baseline_rmse"].mean()),
                    "candidate_mean_rmse_c": float(paired["candidate_rmse"].mean()),
                    **result,
                    "wilcoxon_p": p_value,
                }
            )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result["holm_p"] = np.nan
    for indices in result.groupby(group_columns, sort=True).groups.values():
        family = result.loc[indices, "wilcoxon_p"]
        order = family.sort_values().index.tolist()
        adjusted = {}
        running = 0.0
        count = len(order)
        for rank, index in enumerate(order):
            value = min(1.0, (count - rank) * float(result.loc[index, "wilcoxon_p"]))
            running = max(running, value)
            adjusted[index] = running
        for index, value in adjusted.items():
            result.loc[index, "holm_p"] = value
    return result


def wilson_interval(successes: int, total: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    """Wilson score interval for descriptive coverage reporting."""

    if not 0 <= successes <= total or total <= 0:
        raise ValueError("invalid binomial count")
    proportion = successes / total
    denominator = 1.0 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    radius = (
        z
        * np.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2))
        / denominator
    )
    return float(center - radius), float(center + radius)
