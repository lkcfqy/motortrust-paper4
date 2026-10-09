from __future__ import annotations

import pandas as pd

from scripts.analyze_paper4_transport_diagnostics import (
    PERSISTENCE,
    PROPOSED,
    SOURCE_NORMALIZED,
    TARGET_ONLY,
    adaptation_differences,
    support_stratified_summary,
    transport_degradation,
)


def error_fixture() -> pd.DataFrame:
    rows = []
    values = {
        ("primary_52kw", "source_test", 1): (2.0, 3.0, 2.5),
        ("primary_52kw", "source_test", 2): (4.0, 3.0, 3.5),
        ("external_ipmsm", "external_test", 1): (8.0, 4.0, 5.0),
        ("external_ipmsm", "external_test", 2): (10.0, 6.0, 7.0),
    }
    for (dataset, role, profile_id), method_values in values.items():
        expanded_values = (*method_values, method_values[1] + 1.0)
        for method, rmse in zip(
            (SOURCE_NORMALIZED, PROPOSED, TARGET_ONLY, PERSISTENCE),
            expanded_values,
            strict=True,
        ):
            rows.append(
                {
                    "dataset": dataset,
                    "role": role,
                    "profile_id": profile_id,
                    "method": method,
                    "horizon": "matched_20min",
                    "node": "macro",
                    "rmse_c": rmse,
                    "clip_count": 0,
                    "nonfinite_count": 0,
                }
            )
    return pd.DataFrame(rows)


def support_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "dataset": ["primary_52kw", "primary_52kw", "external_ipmsm", "external_ipmsm"],
            "role": ["source_test", "source_test", "external_test", "external_test"],
            "profile_id": [1, 2, 1, 2],
            "support_distance": [1.0, 2.0, 3.0, 9.0],
            "supported": [True, True, True, False],
        }
    )


def test_adaptation_difference_direction_is_frozen_minus_proposed() -> None:
    result = adaptation_differences(error_fixture(), support_fixture())
    external_first = result.loc[
        result["dataset"].eq("external_ipmsm") & result["profile_id"].eq(1)
    ].iloc[0]
    assert external_first["normalized_source_minus_proposed_c"] == 4.0


def test_support_stratification_retains_unsupported_profiles() -> None:
    result = support_stratified_summary(error_fixture(), support_fixture())
    external = result.loc[result["dataset"].eq("external_ipmsm")]
    assert set(external["supported"]) == {True, False}
    assert external["profiles"].sum() == 8


def test_transport_ratio_uses_matched_profile_macro_means() -> None:
    result = transport_degradation(error_fixture())
    row = result.loc[result["method"].eq(SOURCE_NORMALIZED)].iloc[0]
    assert row["source_test_mean_rmse_c"] == 3.0
    assert row["external_test_mean_rmse_c"] == 9.0
    assert row["external_to_source_ratio"] == 3.0
