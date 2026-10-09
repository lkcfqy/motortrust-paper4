"""Run the protocol-frozen Paper 4 electrothermal transport benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
import yaml

from pmsm_sci.thermal_evaluation import (
    SUPPORT_FEATURES,
    calibrate_trajectory_bands,
    evaluate_trajectory_bands,
    fit_support_reference,
    paired_method_comparisons,
    profile_error_rows,
    support_score,
    wilson_interval,
)
from pmsm_sci.thermal_models import (
    LOSS_FEATURES,
    STATE_COLUMNS,
    HybridThermalModel,
    PositiveThermalModel,
    RawLossScales,
    RidgeThermalModel,
    RolloutResult,
    fit_hybrid_source_model,
    fit_positive_source_model,
    fit_prefix_positive_model,
    fit_ridge_source_model,
    learn_magnitude_floors,
    learn_raw_loss_scales,
    normalized_loss_features,
    raw_loss_features,
    rollout_persistence,
    rollout_state_model,
)
from pmsm_sci.thermal_transport import (
    harmonize_external_1hz,
    harmonize_primary_1hz,
    load_external_thermal,
    load_primary_thermal,
    verify_external_aggregate,
)

PERSISTENCE = "initial_state_persistence"
BOUNDARY_PERSISTENCE = "boundary_shift_persistence"
RIDGE = "source_ridge_arx"
SOURCE_RAW = "source_positive_thermal_network_raw"
SOURCE_NORMALIZED = "source_positive_thermal_network_normalized"
TARGET_ONLY = "target_only_prefix_positive_thermal_network"
PROPOSED = "source_prior_prefix_calibrated_thermal_network"
HYBRID = "source_thermal_network_plus_hist_gradient_residual"
PUBLISHED_ORACLE = "published_target_specific_lptn_estimates"

LOCKED_METHODS = (
    PERSISTENCE,
    BOUNDARY_PERSISTENCE,
    RIDGE,
    SOURCE_RAW,
    SOURCE_NORMALIZED,
    TARGET_ONLY,
    PROPOSED,
    HYBRID,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/paper4_thermal_transport.yaml")
    )
    parser.add_argument(
        "--protocol", type=Path, default=Path("docs/paper4_protocol.md")
    )
    parser.add_argument(
        "--freeze",
        type=Path,
        default=Path("results/paper4_thermal_data_audit/protocol_freeze.json"),
    )
    parser.add_argument(
        "--primary",
        type=Path,
        default=Path("data/raw/electric_motor_temperature/measures_v2.csv"),
    )
    parser.add_argument(
        "--external-root",
        type=Path,
        default=Path("data/raw/lptn_informed_lstm"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/paper4_thermal_transport")
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_freeze(args: argparse.Namespace, config: dict[str, object]) -> dict[str, object]:
    freeze = json.loads(args.freeze.read_text(encoding="utf-8"))
    checks = {
        "config_sha256": file_sha256(args.config),
        "protocol_sha256": file_sha256(args.protocol),
        "primary_data_sha256": file_sha256(args.primary),
    }
    for key, actual in checks.items():
        if freeze[key] != actual:
            raise RuntimeError(f"frozen {key} mismatch: {freeze[key]} != {actual}")
    locked = tuple(config["methods"]["locked"])
    if locked != LOCKED_METHODS:
        raise RuntimeError(f"locked method order changed: {locked}")
    return freeze


def profiles_by_id(frame: pd.DataFrame, ids: list[int]) -> dict[int, pd.DataFrame]:
    result = {}
    for profile_id in ids:
        profile = frame.loc[frame["profile_id"].eq(profile_id)].reset_index(drop=True)
        if profile.empty:
            raise ValueError(f"missing profile {profile_id}")
        expected = np.arange(len(profile))
        if not np.array_equal(profile["sample_idx"].to_numpy(), expected):
            raise ValueError(f"non-contiguous 1 Hz sample index for profile {profile_id}")
        result[int(profile_id)] = profile
    return result


def macro_rmse(truth: np.ndarray, prediction: np.ndarray) -> float:
    return float(np.sqrt(np.mean((prediction - truth) ** 2, axis=0)).mean())


def validation_rollout_score(
    model: RidgeThermalModel,
    profiles: dict[int, pd.DataFrame],
    losses: dict[int, np.ndarray],
    *,
    start: int,
    end: int,
    guard: tuple[float, float],
) -> tuple[float, int, int]:
    values = []
    clip_count = 0
    nonfinite_count = 0
    for profile_id, profile in profiles.items():
        rollout = rollout_state_model(
            model, profile, losses[profile_id], start=start, end=end, temperature_guard=guard
        )
        truth = profile[list(STATE_COLUMNS)].iloc[start:end].to_numpy(float)
        values.append(macro_rmse(truth, rollout.prediction))
        clip_count += rollout.clip_count
        nonfinite_count += rollout.nonfinite_count
    return float(np.mean(values)), clip_count, nonfinite_count


def validation_prior_score(
    source_model: PositiveThermalModel,
    penalty: float,
    profiles: dict[int, pd.DataFrame],
    losses: dict[int, np.ndarray],
    *,
    prefix: int,
    end: int,
    guard: tuple[float, float],
) -> tuple[float, int, int]:
    values = []
    clip_count = 0
    nonfinite_count = 0
    for profile_id, profile in profiles.items():
        adapted = fit_prefix_positive_model(
            profile,
            losses[profile_id],
            prefix_seconds=prefix,
            source_prior=source_model,
            prior_penalty=penalty,
        )
        rollout = rollout_state_model(
            adapted,
            profile,
            losses[profile_id],
            start=prefix,
            end=end,
            temperature_guard=guard,
        )
        truth = profile[list(STATE_COLUMNS)].iloc[prefix:end].to_numpy(float)
        values.append(macro_rmse(truth, rollout.prediction))
        clip_count += rollout.clip_count
        nonfinite_count += rollout.nonfinite_count
    return float(np.mean(values)), clip_count, nonfinite_count


def coefficient_rows(
    source_raw: PositiveThermalModel,
    source_normalized: PositiveThermalModel,
    ridge: RidgeThermalModel,
) -> pd.DataFrame:
    rows = []
    for method, model in (
        (SOURCE_RAW, source_raw),
        (SOURCE_NORMALIZED, source_normalized),
        (RIDGE, ridge),
    ):
        for node_index, node in enumerate(STATE_COLUMNS):
            other_nodes = [candidate for candidate in STATE_COLUMNS if candidate != node]
            feature_names = [
                f"coupling_from_{other_nodes[0]}",
                f"coupling_from_{other_nodes[1]}",
                "coolant_boundary",
                "ambient_boundary",
                *LOSS_FEATURES,
            ]
            for feature_index, feature in enumerate(feature_names):
                rows.append(
                    {
                        "method": method,
                        "node": node,
                        "feature": feature,
                        "coefficient": float(model.coefficients[node_index, feature_index]),
                    }
                )
            rows.append(
                {
                    "method": method,
                    "node": node,
                    "feature": "intercept",
                    "coefficient": (
                        float(model.intercepts[node_index])
                        if isinstance(model, RidgeThermalModel)
                        else 0.0
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_profile_models(
    profile: pd.DataFrame,
    normalized_losses: np.ndarray,
    *,
    source_raw: PositiveThermalModel,
    source_normalized: PositiveThermalModel,
    ridge: RidgeThermalModel,
    hybrid: HybridThermalModel,
    prefix: int,
    prior_penalty: float,
) -> dict[str, PositiveThermalModel | RidgeThermalModel | HybridThermalModel]:
    target_only = fit_prefix_positive_model(
        profile, normalized_losses, prefix_seconds=prefix
    )
    proposed = fit_prefix_positive_model(
        profile,
        normalized_losses,
        prefix_seconds=prefix,
        source_prior=source_normalized,
        prior_penalty=prior_penalty,
    )
    return {
        RIDGE: ridge,
        SOURCE_RAW: source_raw,
        SOURCE_NORMALIZED: source_normalized,
        TARGET_ONLY: target_only,
        PROPOSED: proposed,
        HYBRID: hybrid,
    }


def rollouts_for_profile(
    profile: pd.DataFrame,
    normalized_losses: np.ndarray,
    raw_losses: np.ndarray,
    models: dict[str, PositiveThermalModel | RidgeThermalModel | HybridThermalModel],
    *,
    start: int,
    end: int,
    guard: tuple[float, float],
) -> dict[str, RolloutResult]:
    result = {
        PERSISTENCE: rollout_persistence(
            profile, start=start, end=end, boundary_shift=False, temperature_guard=guard
        ),
        BOUNDARY_PERSISTENCE: rollout_persistence(
            profile, start=start, end=end, boundary_shift=True, temperature_guard=guard
        ),
    }
    for method in (RIDGE, SOURCE_RAW, SOURCE_NORMALIZED, TARGET_ONLY, PROPOSED, HYBRID):
        losses = raw_losses if method == SOURCE_RAW else normalized_losses
        result[method] = rollout_state_model(
            models[method],
            profile,
            losses,
            start=start,
            end=end,
            temperature_guard=guard,
        )
    if tuple(result) != LOCKED_METHODS:
        raise AssertionError(f"method execution order changed: {tuple(result)}")
    return result


def append_error_rows(
    rows: list[dict[str, object]],
    profile: pd.DataFrame,
    rollouts: dict[str, RolloutResult],
    *,
    dataset: str,
    role: str,
    profile_id: int,
    start: int,
    end: int,
    horizon: str,
) -> None:
    truth = profile[list(STATE_COLUMNS)].iloc[start:end].to_numpy(float)
    for method, rollout in rollouts.items():
        rows.extend(
            profile_error_rows(
                truth,
                rollout.prediction,
                dataset=dataset,
                role=role,
                profile_id=profile_id,
                method=method,
                horizon=horizon,
                clip_count=rollout.clip_count,
                nonfinite_count=rollout.nonfinite_count,
            )
        )


def trajectory_frame(
    profile: pd.DataFrame,
    rollouts: dict[str, RolloutResult],
    *,
    dataset: str,
    role: str,
    profile_id: int,
    start: int,
    end: int,
) -> pd.DataFrame:
    truth = profile[list(STATE_COLUMNS)].iloc[start:end].to_numpy(float)
    frames = []
    for method, rollout in rollouts.items():
        frames.append(
            pd.DataFrame(
                {
                    "dataset": dataset,
                    "role": role,
                    "profile_id": profile_id,
                    "method": method,
                    "time_second": np.arange(start, end),
                    "true_winding_c": truth[:, 0],
                    "true_stator_core_c": truth[:, 1],
                    "true_rotor_c": truth[:, 2],
                    "pred_winding_c": rollout.prediction[:, 0],
                    "pred_stator_core_c": rollout.prediction[:, 1],
                    "pred_rotor_c": rollout.prediction[:, 2],
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def aggregate_errors(errors: pd.DataFrame) -> pd.DataFrame:
    return (
        errors.groupby(["dataset", "role", "method", "horizon", "node"], sort=True)
        .agg(
            profiles=("profile_id", "nunique"),
            mean_rmse_c=("rmse_c", "mean"),
            median_rmse_c=("rmse_c", "median"),
            p90_rmse_c=("rmse_c", lambda values: values.quantile(0.90)),
            worst_profile_rmse_c=("rmse_c", "max"),
            mean_mae_c=("mae_c", "mean"),
            mean_max_abs_c=("max_abs_c", "mean"),
            total_clip_count=("clip_count", "sum"),
            total_nonfinite_count=("nonfinite_count", "sum"),
        )
        .reset_index()
    )


def published_external_estimates(path: Path) -> dict[int, np.ndarray]:
    aggregate = pd.read_csv(path)
    required = ["id", "Unnamed: 0", "active_wind_est", "stator_est", "rotor_est"]
    missing = sorted(set(required) - set(aggregate.columns))
    if missing:
        raise ValueError(f"published aggregate is missing estimate columns: {missing}")
    result = {}
    for profile_id, group in aggregate.sort_values(["id", "Unnamed: 0"]).groupby("id"):
        values = group[["active_wind_est", "stator_est", "rotor_est"]].to_numpy(float)
        if not np.isfinite(values).all():
            raise ValueError(f"published estimates are non-finite for profile {profile_id}")
        result[int(profile_id)] = values
    return result


def append_published_oracle(
    errors: list[dict[str, object]],
    trajectories: list[pd.DataFrame],
    profile: pd.DataFrame,
    estimates: np.ndarray,
    *,
    profile_id: int,
    start: int,
    end: int,
) -> None:
    prediction = estimates[start:end]
    truth = profile[list(STATE_COLUMNS)].iloc[start:end].to_numpy(float)
    errors.extend(
        profile_error_rows(
            truth,
            prediction,
            dataset="external_ipmsm",
            role="external_test",
            profile_id=profile_id,
            method=PUBLISHED_ORACLE,
            horizon="matched_20min",
            clip_count=0,
            nonfinite_count=0,
        )
    )
    trajectories.append(
        trajectory_frame(
            profile,
            {PUBLISHED_ORACLE: RolloutResult(prediction, 0, 0)},
            dataset="external_ipmsm",
            role="external_test",
            profile_id=profile_id,
            start=start,
            end=end,
        )
    )


def add_wilson_bounds(summary: pd.DataFrame) -> pd.DataFrame:
    summary = summary.copy()
    intervals = [
        wilson_interval(int(row.covered), int(row.profiles))
        for row in summary.itertuples(index=False)
    ]
    summary["wilson_low"] = [interval[0] for interval in intervals]
    summary["wilson_high"] = [interval[1] for interval in intervals]
    return summary


def joint_band_summary(applied: pd.DataFrame) -> pd.DataFrame:
    per_profile = (
        applied.groupby(
            ["dataset", "role", "method", "horizon", "profile_id"], sort=True
        )["trajectory_covered"]
        .all()
        .reset_index(name="all_nodes_covered")
    )
    summary = (
        per_profile.groupby(["dataset", "role", "method", "horizon"], sort=True)
        .agg(
            covered=("all_nodes_covered", "sum"),
            profiles=("profile_id", "nunique"),
            empirical_coverage=("all_nodes_covered", "mean"),
        )
        .reset_index()
    )
    return add_wilson_bounds(summary)


def run_budget_sensitivity(
    source_test: dict[int, pd.DataFrame],
    external: dict[int, pd.DataFrame],
    floors,
    raw_scales: RawLossScales,
    source_normalized: PositiveThermalModel,
    *,
    prior_penalty: float,
    budgets: list[int],
    evaluation_seconds: int,
    guard: tuple[float, float],
) -> pd.DataFrame:
    rows = []
    for dataset, role, profiles in (
        ("primary_52kw", "source_test", source_test),
        ("external_ipmsm", "external_test", external),
    ):
        for profile_id, profile in profiles.items():
            for budget in budgets:
                end = budget + evaluation_seconds
                normalized = normalized_loss_features(
                    profile, floors, prefix_seconds=budget
                )
                target_only = fit_prefix_positive_model(
                    profile, normalized, prefix_seconds=budget
                )
                proposed = fit_prefix_positive_model(
                    profile,
                    normalized,
                    prefix_seconds=budget,
                    source_prior=source_normalized,
                    prior_penalty=prior_penalty,
                )
                methods = {
                    SOURCE_NORMALIZED: source_normalized,
                    TARGET_ONLY: target_only,
                    PROPOSED: proposed,
                }
                truth = profile[list(STATE_COLUMNS)].iloc[budget:end].to_numpy(float)
                for method, model in methods.items():
                    rollout = rollout_state_model(
                        model,
                        profile,
                        normalized,
                        start=budget,
                        end=end,
                        temperature_guard=guard,
                    )
                    rows.append(
                        {
                            "dataset": dataset,
                            "role": role,
                            "profile_id": profile_id,
                            "budget_seconds": budget,
                            "evaluation_seconds": evaluation_seconds,
                            "method": method,
                            "macro_rmse_c": macro_rmse(truth, rollout.prediction),
                            "clip_count": rollout.clip_count,
                            "nonfinite_count": rollout.nonfinite_count,
                        }
                    )
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    freeze = verify_freeze(args, config)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    roles = config["source_roles"]
    timeline = config["timeline"]
    prefix = int(timeline["commissioning_prefix_seconds"])
    matched_end = prefix + int(timeline["matched_evaluation_seconds"])
    long_end = prefix + int(timeline["source_long_evaluation_seconds"])
    cap = int(timeline["source_training_cap_seconds_per_profile"])
    guard = tuple(map(float, timeline["numerical_temperature_guard_c"]))

    print("[1/7] Loading and harmonizing the source machine", flush=True)
    primary = harmonize_primary_1hz(load_primary_thermal(args.primary))
    train = profiles_by_id(primary, list(roles["train_profiles"]))
    validation = profiles_by_id(primary, list(roles["validation_profiles"]))
    train_list = list(train.values())

    floors = learn_magnitude_floors(train_list, prefix_seconds=prefix)
    raw_scales = learn_raw_loss_scales(train_list, cap_seconds=cap)
    train_normalized = {
        profile_id: normalized_loss_features(profile, floors, prefix_seconds=prefix)
        for profile_id, profile in train.items()
    }
    train_raw = {
        profile_id: raw_loss_features(profile, raw_scales)
        for profile_id, profile in train.items()
    }
    validation_normalized = {
        profile_id: normalized_loss_features(profile, floors, prefix_seconds=prefix)
        for profile_id, profile in validation.items()
    }

    print("[2/7] Fitting frozen source grey-box models and validation-only tuning", flush=True)
    source_raw = fit_positive_source_model(
        train_list,
        [train_raw[profile_id] for profile_id in train],
        loss_mode="raw_source_scaled",
        cap_seconds=cap,
    )
    source_normalized = fit_positive_source_model(
        train_list,
        [train_normalized[profile_id] for profile_id in train],
        loss_mode="prefix_capacity_normalized",
        cap_seconds=cap,
    )

    tuning_rows = []
    ridge_candidates: dict[float, RidgeThermalModel] = {}
    for alpha in map(float, config["methods"]["tuning"]["ridge_alpha_grid"]):
        ridge_candidate = fit_ridge_source_model(
            train_list,
            [train_normalized[profile_id] for profile_id in train],
            alpha=alpha,
            cap_seconds=cap,
        )
        score, clips, nonfinite = validation_rollout_score(
            ridge_candidate,
            validation,
            validation_normalized,
            start=prefix,
            end=matched_end,
            guard=guard,
        )
        ridge_candidates[alpha] = ridge_candidate
        tuning_rows.append(
            {
                "family": "ridge_alpha",
                "candidate": alpha,
                "validation_profile_macro_rmse_c": score,
                "clip_count": clips,
                "nonfinite_count": nonfinite,
            }
        )
    ridge_alpha = min(
        ridge_candidates,
        key=lambda value: next(
            row["validation_profile_macro_rmse_c"]
            for row in tuning_rows
            if row["family"] == "ridge_alpha" and row["candidate"] == value
        ),
    )
    ridge = ridge_candidates[ridge_alpha]

    prior_scores = {}
    for penalty in map(float, config["methods"]["tuning"]["source_prior_penalty_grid"]):
        score, clips, nonfinite = validation_prior_score(
            source_normalized,
            penalty,
            validation,
            validation_normalized,
            prefix=prefix,
            end=matched_end,
            guard=guard,
        )
        prior_scores[penalty] = score
        tuning_rows.append(
            {
                "family": "source_prior_penalty",
                "candidate": penalty,
                "validation_profile_macro_rmse_c": score,
                "clip_count": clips,
                "nonfinite_count": nonfinite,
            }
        )
    prior_penalty = min(prior_scores, key=prior_scores.get)
    hybrid = fit_hybrid_source_model(
        train_list,
        [train_normalized[profile_id] for profile_id in train],
        source_normalized,
        cap_seconds=cap,
    )

    tuning = pd.DataFrame(tuning_rows)
    tuning["selected"] = (
        (tuning["family"].eq("ridge_alpha") & tuning["candidate"].eq(ridge_alpha))
        | (
            tuning["family"].eq("source_prior_penalty")
            & tuning["candidate"].eq(prior_penalty)
        )
    )
    tuning.to_csv(args.output_dir / "validation_tuning.csv", index=False)
    coefficients = coefficient_rows(source_raw, source_normalized, ridge)
    coefficients.to_csv(args.output_dir / "source_model_coefficients.csv", index=False)

    model_bundle = {
        "magnitude_floors": floors,
        "raw_loss_scales": raw_scales,
        "source_raw": source_raw,
        "source_normalized": source_normalized,
        "ridge": ridge,
        "hybrid": hybrid,
        "selected_ridge_alpha": ridge_alpha,
        "selected_prior_penalty": prior_penalty,
    }
    model_path = args.output_dir / "source_model_bundle.joblib"
    joblib.dump(model_bundle, model_path)
    selection_freeze = {
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "locked_before_source_test_and_external_outcomes",
        "protocol_config_sha256": freeze["config_sha256"],
        "selected_ridge_alpha": ridge_alpha,
        "selected_prior_penalty": prior_penalty,
        "model_bundle_sha256": file_sha256(model_path),
        "validation_tuning_sha256": file_sha256(args.output_dir / "validation_tuning.csv"),
        "source_coefficients_sha256": file_sha256(
            args.output_dir / "source_model_coefficients.csv"
        ),
    }
    (args.output_dir / "selection_freeze.json").write_text(
        json.dumps(selection_freeze, indent=2), encoding="utf-8"
    )
    print(
        f"Selection frozen: ridge alpha={ridge_alpha:g}; source-prior penalty={prior_penalty:g}",
        flush=True,
    )

    errors: list[dict[str, object]] = []
    trajectories: list[pd.DataFrame] = []

    print("[3/7] Calibrating trajectory bands on source-validation profiles", flush=True)
    for profile_id, profile in validation.items():
        normalized = validation_normalized[profile_id]
        raw = raw_loss_features(profile, raw_scales)
        models = build_profile_models(
            profile,
            normalized,
            source_raw=source_raw,
            source_normalized=source_normalized,
            ridge=ridge,
            hybrid=hybrid,
            prefix=prefix,
            prior_penalty=prior_penalty,
        )
        matched_rollouts = rollouts_for_profile(
            profile,
            normalized,
            raw,
            models,
            start=prefix,
            end=matched_end,
            guard=guard,
        )
        append_error_rows(
            errors,
            profile,
            matched_rollouts,
            dataset="primary_52kw",
            role="validation",
            profile_id=profile_id,
            start=prefix,
            end=matched_end,
            horizon="matched_20min",
        )
        long_rollouts = rollouts_for_profile(
            profile,
            normalized,
            raw,
            models,
            start=prefix,
            end=long_end,
            guard=guard,
        )
        append_error_rows(
            errors,
            profile,
            long_rollouts,
            dataset="primary_52kw",
            role="validation",
            profile_id=profile_id,
            start=prefix,
            end=long_end,
            horizon="long_55min",
        )

    validation_errors = pd.DataFrame(errors)
    bands = calibrate_trajectory_bands(
        validation_errors.loc[validation_errors["role"].eq("validation")], coverage=0.90
    )
    bands.to_csv(args.output_dir / "trajectory_bands.csv", index=False)

    print("[4/7] Revealing the 14 locked source-test profiles", flush=True)
    source_test = profiles_by_id(primary, list(roles["locked_test_profiles"]))
    support_reference = fit_support_reference(train_list, prefix_seconds=prefix)
    support_rows = []
    standardized_train = (
        support_reference.summaries - support_reference.center
    ) / support_reference.scale
    train_distances = np.linalg.norm(
        standardized_train[:, None, :] - standardized_train[None, :, :], axis=2
    )
    np.fill_diagonal(train_distances, np.inf)
    for index, profile_id in enumerate(support_reference.profile_ids):
        nearest_index = int(np.argmin(train_distances[index]))
        distance = float(support_reference.leave_one_out_distances[index])
        support_rows.append(
            {
                "dataset": "primary_52kw",
                "role": "train",
                "profile_id": int(profile_id),
                "support_distance": distance,
                "support_threshold": support_reference.threshold,
                "supported": bool(distance <= support_reference.threshold),
                "nearest_source_profile": int(support_reference.profile_ids[nearest_index]),
            }
        )
    for role, profiles in (("validation", validation), ("source_test", source_test)):
        for profile_id, profile in profiles.items():
            support_rows.append(
                {
                    "dataset": "primary_52kw",
                    "role": role,
                    "profile_id": profile_id,
                    **support_score(support_reference, profile, prefix_seconds=prefix),
                }
            )

    for profile_id, profile in source_test.items():
        normalized = normalized_loss_features(profile, floors, prefix_seconds=prefix)
        raw = raw_loss_features(profile, raw_scales)
        models = build_profile_models(
            profile,
            normalized,
            source_raw=source_raw,
            source_normalized=source_normalized,
            ridge=ridge,
            hybrid=hybrid,
            prefix=prefix,
            prior_penalty=prior_penalty,
        )
        matched_rollouts = rollouts_for_profile(
            profile,
            normalized,
            raw,
            models,
            start=prefix,
            end=matched_end,
            guard=guard,
        )
        append_error_rows(
            errors,
            profile,
            matched_rollouts,
            dataset="primary_52kw",
            role="source_test",
            profile_id=profile_id,
            start=prefix,
            end=matched_end,
            horizon="matched_20min",
        )
        long_rollouts = rollouts_for_profile(
            profile,
            normalized,
            raw,
            models,
            start=prefix,
            end=long_end,
            guard=guard,
        )
        append_error_rows(
            errors,
            profile,
            long_rollouts,
            dataset="primary_52kw",
            role="source_test",
            profile_id=profile_id,
            start=prefix,
            end=long_end,
            horizon="long_55min",
        )
        trajectories.append(
            trajectory_frame(
                profile,
                long_rollouts,
                dataset="primary_52kw",
                role="source_test",
                profile_id=profile_id,
                start=prefix,
                end=long_end,
            )
        )

    print("[5/7] One-time reveal of all 16 external-machine profiles", flush=True)
    external_dir = args.external_root / "dataset"
    external_raw = load_external_thermal(external_dir)
    verify_external_aggregate(external_raw, external_dir / "temperature.csv")
    external_frame = harmonize_external_1hz(external_raw)
    external = profiles_by_id(external_frame, list(range(16)))
    oracle = published_external_estimates(external_dir / "temperature.csv")
    for profile_id, profile in external.items():
        support_rows.append(
            {
                "dataset": "external_ipmsm",
                "role": "external_test",
                "profile_id": profile_id,
                **support_score(support_reference, profile, prefix_seconds=prefix),
            }
        )
        normalized = normalized_loss_features(profile, floors, prefix_seconds=prefix)
        raw = raw_loss_features(profile, raw_scales)
        models = build_profile_models(
            profile,
            normalized,
            source_raw=source_raw,
            source_normalized=source_normalized,
            ridge=ridge,
            hybrid=hybrid,
            prefix=prefix,
            prior_penalty=prior_penalty,
        )
        rollouts = rollouts_for_profile(
            profile,
            normalized,
            raw,
            models,
            start=prefix,
            end=matched_end,
            guard=guard,
        )
        append_error_rows(
            errors,
            profile,
            rollouts,
            dataset="external_ipmsm",
            role="external_test",
            profile_id=profile_id,
            start=prefix,
            end=matched_end,
            horizon="matched_20min",
        )
        trajectories.append(
            trajectory_frame(
                profile,
                rollouts,
                dataset="external_ipmsm",
                role="external_test",
                profile_id=profile_id,
                start=prefix,
                end=matched_end,
            )
        )
        append_published_oracle(
            errors,
            trajectories,
            profile,
            oracle[profile_id],
            profile_id=profile_id,
            start=prefix,
            end=matched_end,
        )

    print("[6/7] Computing profile-level inference, coverage, support, and budgets", flush=True)
    error_frame = pd.DataFrame(errors)
    error_frame.to_csv(args.output_dir / "per_profile_errors.csv", index=False)
    aggregate = aggregate_errors(error_frame)
    aggregate.to_csv(args.output_dir / "aggregate_summary.csv", index=False)
    pd.DataFrame(support_rows).to_csv(args.output_dir / "support_scores.csv", index=False)
    pd.DataFrame(
        {
            "support_feature": SUPPORT_FEATURES,
            "source_center": support_reference.center,
            "source_scale": support_reference.scale,
        }
    ).to_csv(args.output_dir / "support_reference.csv", index=False)

    evaluation_errors = error_frame.loc[
        error_frame["role"].isin(["source_test", "external_test"])
        & error_frame["method"].isin(LOCKED_METHODS)
    ]
    band_applied, band_summary = evaluate_trajectory_bands(evaluation_errors, bands)
    band_applied.to_csv(args.output_dir / "trajectory_band_profile_coverage.csv", index=False)
    band_summary = add_wilson_bounds(band_summary)
    band_summary.to_csv(args.output_dir / "trajectory_band_summary.csv", index=False)
    joint_band_summary(band_applied).to_csv(
        args.output_dir / "trajectory_band_joint_summary.csv", index=False
    )

    comparisons = paired_method_comparisons(
        evaluation_errors, candidate_method=PROPOSED, node="macro"
    )
    comparisons.to_csv(args.output_dir / "paired_method_comparisons.csv", index=False)

    sensitivity = run_budget_sensitivity(
        source_test,
        external,
        floors,
        raw_scales,
        source_normalized,
        prior_penalty=prior_penalty,
        budgets=list(map(int, timeline["sensitivity_prefix_seconds"])),
        evaluation_seconds=int(timeline["sensitivity_evaluation_seconds"]),
        guard=guard,
    )
    sensitivity.to_csv(args.output_dir / "budget_sensitivity_per_profile.csv", index=False)
    (
        sensitivity.groupby(["dataset", "role", "budget_seconds", "method"], sort=True)
        .agg(
            profiles=("profile_id", "nunique"),
            mean_macro_rmse_c=("macro_rmse_c", "mean"),
            median_macro_rmse_c=("macro_rmse_c", "median"),
            worst_macro_rmse_c=("macro_rmse_c", "max"),
            total_clip_count=("clip_count", "sum"),
            total_nonfinite_count=("nonfinite_count", "sum"),
        )
        .reset_index()
        .to_csv(args.output_dir / "budget_sensitivity_summary.csv", index=False)
    )

    source_gate = comparisons.loc[
        comparisons["dataset"].eq("primary_52kw")
        & comparisons["role"].eq("source_test")
        & comparisons["horizon"].eq("matched_20min")
        & comparisons["baseline"].eq(SOURCE_NORMALIZED)
    ].iloc[0]
    external_gate = comparisons.loc[
        comparisons["dataset"].eq("external_ipmsm")
        & comparisons["role"].eq("external_test")
        & comparisons["horizon"].eq("matched_20min")
        & comparisons["baseline"].eq(SOURCE_NORMALIZED)
    ].iloc[0]
    uncertainty_rows = band_summary.loc[
        band_summary["dataset"].eq("primary_52kw")
        & band_summary["role"].eq("source_test")
        & band_summary["method"].eq(PROPOSED)
        & band_summary["horizon"].eq("matched_20min")
    ]
    min_node_coverage = float(uncertainty_rows["empirical_coverage"].min())
    gates = {
        "source_adaptation": {
            "relative_improvement": float(source_gate["relative_improvement"]),
            "ci_low_c": float(source_gate["ci_low_c"]),
            "pass": bool(
                source_gate["relative_improvement"] >= 0.10 and source_gate["ci_low_c"] > 0
            ),
        },
        "external_adaptation": {
            "relative_improvement": float(external_gate["relative_improvement"]),
            "ci_low_c": float(external_gate["ci_low_c"]),
            "pass": bool(
                external_gate["relative_improvement"] >= 0.10
                and external_gate["ci_low_c"] > 0
            ),
        },
        "source_uncertainty": {
            "minimum_nodewise_trajectory_coverage": min_node_coverage,
            "pass": bool(min_node_coverage >= 0.80),
        },
    }
    (args.output_dir / "predeclared_gates.json").write_text(
        json.dumps(gates, indent=2), encoding="utf-8"
    )

    print("[7/7] Writing trajectories and immutable run metadata", flush=True)
    pd.concat(trajectories, ignore_index=True).to_csv(
        args.output_dir / "trajectory_predictions.csv.gz", index=False, compression="gzip"
    )
    metadata = {
        "created_utc": datetime.now(UTC).isoformat(),
        "protocol_config_sha256": freeze["config_sha256"],
        "protocol_document_sha256": freeze["protocol_sha256"],
        "selection_freeze_sha256": file_sha256(args.output_dir / "selection_freeze.json"),
        "primary_data_sha256": freeze["primary_data_sha256"],
        "external_repository_commit": freeze["external_repository_commit"],
        "selected_ridge_alpha": ridge_alpha,
        "selected_prior_penalty": prior_penalty,
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "output_sha256": {
            path.name: file_sha256(path)
            for path in sorted(args.output_dir.iterdir())
            if path.is_file() and path.name != "run_metadata.json"
        },
    }
    (args.output_dir / "run_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(gates, indent=2), flush=True)


if __name__ == "__main__":
    main()

