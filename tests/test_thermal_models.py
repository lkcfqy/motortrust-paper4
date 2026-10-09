from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from pmsm_sci.thermal_models import (
    MODEL_FEATURE_COUNT,
    STATE_COLUMNS,
    FastHistPredictor,
    MagnitudeFloors,
    PositiveThermalModel,
    fit_positive_source_model,
    fit_prefix_positive_model,
    learn_magnitude_floors,
    normalized_loss_features,
    rollout_persistence,
    rollout_state_model,
)


def stable_profile(profile_id: int, length: int = 500, heat_scale: float = 1.0) -> pd.DataFrame:
    time = np.arange(length, dtype=float)
    frame = pd.DataFrame(
        {
            "dataset": "synthetic",
            "machine_id": "m",
            "profile_id": profile_id,
            "sample_idx": np.arange(length),
            "ambient": 20.0 + 0.001 * time,
            "coolant": 22.0 + 0.002 * time,
            "u_d": 20.0 + 2.0 * np.sin(time / 30),
            "u_q": 30.0 + 2.0 * np.cos(time / 40),
            "i_d": -10.0 - heat_scale * np.sin(time / 25),
            "i_q": 15.0 + heat_scale * np.cos(time / 35),
            "speed_rpm": 1000.0 + 100.0 * np.sin(time / 50),
            "torque_nm": 20.0 + 5.0 * np.cos(time / 45),
        }
    )
    floors = MagnitudeFloors(1.0, 1.0, 1.0, 1.0)
    losses = normalized_loss_features(frame, floors, prefix_seconds=100)
    coefficient = np.zeros((3, MODEL_FEATURE_COUNT))
    coefficient[:, 2] = [0.002, 0.0015, 0.0005]
    coefficient[:, 3] = [0.0002, 0.0003, 0.001]
    coefficient[:, 4] = [0.01, 0.005, 0.002]
    state = np.empty((length, 3))
    state[0] = [25.0, 24.0, 23.0]
    for index in range(1, length):
        previous = state[index - 1]
        for node in range(3):
            others = [candidate for candidate in range(3) if candidate != node]
            design = np.concatenate(
                [
                    previous[others] - previous[node],
                    [
                        frame["coolant"].iloc[index] - previous[node],
                        frame["ambient"].iloc[index] - previous[node],
                    ],
                    losses[index],
                ]
            )
            state[index, node] = previous[node] + design @ coefficient[node]
    frame[list(STATE_COLUMNS)] = state
    return frame


def test_positive_model_recovers_and_rolls_out_stable_synthetic_dynamics() -> None:
    profiles = [stable_profile(1), stable_profile(2, heat_scale=1.2)]
    floors = learn_magnitude_floors(profiles, prefix_seconds=100)
    losses = [normalized_loss_features(p, floors, prefix_seconds=100) for p in profiles]
    fitted = fit_positive_source_model(profiles, losses, loss_mode="normalized")
    rollout = rollout_state_model(fitted, profiles[0], losses[0], start=100, end=300)
    truth = profiles[0][list(STATE_COLUMNS)].iloc[100:300].to_numpy()
    assert np.sqrt(np.mean((rollout.prediction - truth) ** 2)) < 0.02
    assert rollout.clip_count == 0
    assert rollout.nonfinite_count == 0


def test_prefix_fit_does_not_read_post_prefix_temperature_labels() -> None:
    frame = stable_profile(1)
    floors = learn_magnitude_floors([frame], prefix_seconds=100)
    losses = normalized_loss_features(frame, floors, prefix_seconds=100)
    first = fit_prefix_positive_model(frame, losses, prefix_seconds=100)
    changed = frame.copy()
    changed.loc[100:, list(STATE_COLUMNS)] += 1000.0
    second = fit_prefix_positive_model(changed, losses, prefix_seconds=100)
    np.testing.assert_allclose(first.coefficients, second.coefficients)


def test_large_prior_penalty_keeps_prefix_model_near_source_prior() -> None:
    frame = stable_profile(1)
    floors = learn_magnitude_floors([frame], prefix_seconds=100)
    losses = normalized_loss_features(frame, floors, prefix_seconds=100)
    prior = PositiveThermalModel(np.full((3, MODEL_FEATURE_COUNT), 0.003), "source")
    fitted = fit_prefix_positive_model(
        frame,
        losses,
        prefix_seconds=100,
        source_prior=prior,
        prior_penalty=1e8,
    )
    np.testing.assert_allclose(fitted.coefficients, prior.coefficients, atol=1e-6)


def test_persistence_anchors_at_final_observed_prefix_state() -> None:
    frame = stable_profile(1)
    result = rollout_persistence(frame, start=100, end=110, boundary_shift=False)
    expected = frame[list(STATE_COLUMNS)].iloc[99].to_numpy()
    np.testing.assert_allclose(result.prediction, np.repeat(expected[None, :], 10, axis=0))


def test_rollout_guard_is_counted() -> None:
    frame = stable_profile(1, length=20)
    floors = learn_magnitude_floors([frame], prefix_seconds=10)
    losses = normalized_loss_features(frame, floors, prefix_seconds=10)
    coefficients = np.zeros((3, MODEL_FEATURE_COUNT))
    coefficients[:, 4] = 1000.0
    model = PositiveThermalModel(coefficients, "unstable")
    result = rollout_state_model(model, frame, losses, start=10, end=15)
    assert result.clip_count > 0
    assert np.max(result.prediction) == 250.0


def test_fast_hist_single_row_path_matches_public_predict() -> None:
    rng = np.random.default_rng(42)
    x = rng.normal(size=(500, 10))
    y = np.sin(x[:, 0]) + x[:, 1] ** 2
    model = HistGradientBoostingRegressor(
        max_iter=25, max_leaf_nodes=15, random_state=42
    ).fit(x, y)
    fast = FastHistPredictor.from_estimator(model)
    expected = model.predict(x[:50])
    actual = np.asarray([fast.predict_one(row) for row in x[:50]])
    np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-14)
