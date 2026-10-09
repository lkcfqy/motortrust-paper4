from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pmsm_sci.thermal_transport import (
    EXTERNAL_REQUIRED,
    PRIMARY_REQUIRED,
    harmonize_external_1hz,
    harmonize_primary_1hz,
    load_external_thermal,
    load_primary_thermal,
    profile_manifest,
    verify_external_aggregate,
)


def primary_fixture() -> pd.DataFrame:
    rows = []
    for profile_id, length in [(2, 3), (3, 4)]:
        for index in range(length):
            value = float(profile_id * 10 + index)
            rows.append(
                {
                    "ambient": 20.0 + index,
                    "coolant": 21.0 + index,
                    "u_d": value,
                    "u_q": value + 1,
                    "i_d": -value,
                    "i_q": value + 2,
                    "motor_speed": value + 3,
                    "torque": value + 4,
                    "pm": value + 30,
                    "stator_yoke": value + 20,
                    "stator_tooth": value + 22,
                    "stator_winding": value + 25,
                    "profile_id": profile_id,
                }
            )
    return pd.DataFrame(rows, columns=PRIMARY_REQUIRED)


def external_fixture(profile_id: int, length: int = 3) -> pd.DataFrame:
    data: dict[str, np.ndarray] = {}
    for column_index, column in enumerate(EXTERNAL_REQUIRED):
        data[column] = np.arange(length, dtype=float) + column_index + profile_id * 100
    return pd.DataFrame(data)


def test_primary_harmonization_preserves_profiles_and_bin_endpoint(tmp_path: Path) -> None:
    path = tmp_path / "primary.csv"
    primary_fixture().to_csv(path, index=False)
    raw = load_primary_thermal(path)
    out = harmonize_primary_1hz(raw)
    assert out.groupby("profile_id").size().to_dict() == {2: 2, 3: 2}
    first = out.loc[(out["profile_id"] == 2) & (out["sample_idx"] == 0)].iloc[0]
    assert first["u_d"] == pytest.approx(20.5)
    assert first["temp_winding"] == pytest.approx(46.0)
    assert first["temp_stator_core"] == pytest.approx(42.0)


def test_primary_loader_rejects_nonfinite_values(tmp_path: Path) -> None:
    frame = primary_fixture()
    frame.loc[0, "pm"] = np.nan
    path = tmp_path / "primary.csv"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="non-finite"):
        load_primary_thermal(path)


def test_external_harmonization_uses_raw_measurements(tmp_path: Path) -> None:
    for profile_id in range(16):
        external_fixture(profile_id).to_csv(tmp_path / f"id_{profile_id}.csv", index=False)
    raw = load_external_thermal(tmp_path)
    out = harmonize_external_1hz(raw)
    first_raw = raw.iloc[0]
    first = out.iloc[0]
    assert first["temp_winding"] == pytest.approx(
        (first_raw["activewind_1"] + first_raw["activewind_2"]) / 2
    )
    assert first["temp_stator_core"] == pytest.approx(
        (first_raw["slotbottom"] + first_raw["outer_yoke"]) / 2
    )
    assert "active_wind_est" not in out.columns


def test_external_aggregate_verification_rejects_changed_raw_value(tmp_path: Path) -> None:
    parts = []
    for profile_id in range(16):
        part = external_fixture(profile_id)
        part.to_csv(tmp_path / f"id_{profile_id}.csv", index=False)
        tagged = part.copy()
        tagged["id"] = profile_id
        tagged["Unnamed: 0"] = np.arange(len(part))
        parts.append(tagged)
    raw = load_external_thermal(tmp_path)
    aggregate = pd.concat(parts, ignore_index=True)
    aggregate.loc[0, EXTERNAL_REQUIRED[0]] += 1
    path = tmp_path / "temperature.csv"
    aggregate.to_csv(path, index=False)
    with pytest.raises(ValueError, match="differs"):
        verify_external_aggregate(raw, path)


def test_profile_manifest_has_one_row_per_profile(tmp_path: Path) -> None:
    path = tmp_path / "primary.csv"
    primary_fixture().to_csv(path, index=False)
    harmonized = harmonize_primary_1hz(load_primary_thermal(path))
    manifest = profile_manifest(harmonized, sample_rate_hz=1.0)
    assert len(manifest) == 2
    assert manifest["duration_seconds"].tolist() == [2.0, 2.0]
