from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pmsm_sci.thermal_evaluation import (
    SUPPORT_FEATURES,
    calibrate_trajectory_bands,
    evaluate_trajectory_bands,
    finite_sample_quantile,
    fit_support_reference,
    operating_summary,
    paired_profile_bootstrap,
    profile_error_rows,
    support_score,
    wilson_interval,
)
from pmsm_sci.thermal_models import STATE_COLUMNS


def profile(profile_id: int, offset: float = 0.0, length: int = 400) -> pd.DataFrame:
    time = np.arange(length, dtype=float)
    frame = pd.DataFrame(
        {
            "profile_id": profile_id,
            "i_d": -10.0 - offset + np.sin(time),
            "i_q": 20.0 + offset + np.cos(time),
            "u_d": 30.0 + offset + np.sin(time / 2),
            "u_q": 40.0 + offset + np.cos(time / 2),
            "speed_rpm": 1000.0 + 20 * offset + time,
            "torque_nm": 30.0 + offset + 0.1 * time,
            "coolant": 20.0 + 0.01 * time,
            "ambient": 19.0 + 0.005 * time,
        }
    )
    for node_index, node in enumerate(STATE_COLUMNS):
        frame[node] = 25.0 + node_index + 0.02 * time
    return frame


def test_operating_summary_has_frozen_shape_and_ignores_temperatures() -> None:
    frame = profile(1)
    first = operating_summary(frame)
    changed = frame.copy()
    changed[list(STATE_COLUMNS)] += 1000
    second = operating_summary(changed)
    assert first.shape == (len(SUPPORT_FEATURES),)
    np.testing.assert_allclose(first, second)


def test_support_reference_flags_large_operating_shift() -> None:
    training = [profile(index, offset=float(index)) for index in range(1, 6)]
    reference = fit_support_reference(training)
    near = support_score(reference, profile(20, offset=3.0))
    far = support_score(reference, profile(21, offset=100.0))
    assert near["supported"]
    assert not far["supported"]
    assert far["support_distance"] > near["support_distance"]


def test_profile_error_rows_use_profile_macro_not_pooled_nodes() -> None:
    truth = np.zeros((10, 3))
    prediction = np.column_stack([np.ones(10), np.full(10, 2.0), np.full(10, 3.0)])
    rows = profile_error_rows(
        truth,
        prediction,
        dataset="d",
        role="test",
        profile_id=1,
        method="m",
        horizon="matched",
        clip_count=0,
        nonfinite_count=0,
    )
    macro = next(row for row in rows if row["node"] == "macro")
    assert macro["rmse_c"] == pytest.approx(2.0)
    assert macro["mae_c"] == pytest.approx(2.0)


def test_eleven_profile_ninety_percent_band_uses_maximum() -> None:
    values = np.arange(1, 12, dtype=float)
    threshold, rank = finite_sample_quantile(values, coverage=0.90)
    assert rank == 11
    assert threshold == 11


def test_band_calibration_and_application_are_profile_level() -> None:
    rows = []
    for profile_id in range(11):
        rows.extend(
            profile_error_rows(
                np.zeros((2, 3)),
                np.full((2, 3), profile_id / 10),
                dataset="source",
                role="validation",
                profile_id=profile_id,
                method="m",
                horizon="matched",
                clip_count=0,
                nonfinite_count=0,
            )
        )
    errors = pd.DataFrame(rows)
    bands = calibrate_trajectory_bands(errors)
    applied, summary = evaluate_trajectory_bands(errors, bands)
    assert len(bands) == 3
    assert applied["trajectory_covered"].all()
    assert (summary["empirical_coverage"] == 1).all()


def test_paired_bootstrap_improvement_direction_is_baseline_minus_candidate() -> None:
    result = paired_profile_bootstrap(np.array([3.0, 4.0]), np.array([1.0, 2.0]))
    assert result["improvement_c"] == pytest.approx(2.0)
    assert result["relative_improvement"] == pytest.approx(2.0 / 3.5)


def test_wilson_interval_contains_observed_fraction() -> None:
    lower, upper = wilson_interval(8, 10)
    assert lower < 0.8 < upper
