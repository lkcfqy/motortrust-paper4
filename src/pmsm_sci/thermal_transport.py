"""Data contracts and preprocessing for the Paper 4 thermal-transport study."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd

PRIMARY_REQUIRED = (
    "ambient",
    "coolant",
    "u_d",
    "u_q",
    "i_d",
    "i_q",
    "motor_speed",
    "torque",
    "pm",
    "stator_yoke",
    "stator_tooth",
    "stator_winding",
    "profile_id",
)

EXTERNAL_REQUIRED = (
    "water_outlet",
    "bearing",
    "ambient",
    "rotor",
    "endwind_1",
    "endwind_2",
    "slotside",
    "slotopen",
    "activewind_1",
    "slotbottom",
    "activewind_2",
    "outer_yoke",
    "endcap",
    "Torque",
    "IdRef",
    "IdFbk",
    "IqRef",
    "IqFbk",
    "speed",
    "Ud",
    "Uq",
    "Pele_PI",
)

HARMONIZED_COLUMNS = (
    "dataset",
    "machine_id",
    "profile_id",
    "sample_idx",
    "ambient",
    "coolant",
    "u_d",
    "u_q",
    "i_d",
    "i_q",
    "speed_rpm",
    "torque_nm",
    "temp_winding",
    "temp_stator_core",
    "temp_rotor",
)


def _require_columns(frame: pd.DataFrame, required: Iterable[str], *, label: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing required columns: {missing}")


def _require_finite(frame: pd.DataFrame, columns: Iterable[str], *, label: str) -> None:
    numeric = frame[list(columns)].apply(pd.to_numeric, errors="coerce")
    bad = ~np.isfinite(numeric.to_numpy(dtype=np.float64))
    if bad.any():
        bad_columns = numeric.columns[bad.any(axis=0)].tolist()
        raise ValueError(f"{label} has missing or non-finite values in: {bad_columns}")


def load_primary_thermal(path: Path) -> pd.DataFrame:
    """Load the 52 kW source data and enforce its immutable row-level contract."""

    frame = pd.read_csv(path)
    _require_columns(frame, PRIMARY_REQUIRED, label="primary thermal data")
    _require_finite(frame, PRIMARY_REQUIRED, label="primary thermal data")
    if frame.duplicated().any():
        raise ValueError("primary thermal data contains exact duplicate rows")
    frame = frame.copy()
    frame["profile_id"] = frame["profile_id"].astype("int64")
    frame["native_sample_idx"] = frame.groupby("profile_id", sort=False).cumcount()
    if int(frame["profile_id"].ne(frame["profile_id"].shift()).sum()) != int(
        frame["profile_id"].nunique()
    ):
        raise ValueError("primary profiles are not each stored as one contiguous run")
    return frame


def load_external_thermal(dataset_dir: Path) -> pd.DataFrame:
    """Load the 16 raw 1 Hz target profiles without model-estimate columns."""

    parts: list[pd.DataFrame] = []
    for profile_id in range(16):
        path = dataset_dir / f"id_{profile_id}.csv"
        if not path.is_file():
            raise FileNotFoundError(f"missing frozen external profile: {path}")
        part = pd.read_csv(path)
        _require_columns(part, EXTERNAL_REQUIRED, label=path.name)
        _require_finite(part, EXTERNAL_REQUIRED, label=path.name)
        part = part.copy()
        part["profile_id"] = profile_id
        part["native_sample_idx"] = np.arange(len(part), dtype=np.int64)
        parts.append(part)
    frame = pd.concat(parts, ignore_index=True)
    if frame[list(EXTERNAL_REQUIRED)].duplicated().any():
        raise ValueError("external thermal data contains exact duplicate raw rows")
    return frame


def verify_external_aggregate(raw: pd.DataFrame, aggregate_path: Path) -> None:
    """Verify that ``temperature.csv`` is a lossless aggregate of the raw profiles.

    The aggregate's three ``*_est`` columns are deliberately excluded because they
    are published model outputs and would leak target-model information.
    """

    aggregate = pd.read_csv(aggregate_path)
    expected_rows = len(raw)
    if len(aggregate) != expected_rows:
        raise ValueError(
            f"external aggregate row mismatch: {len(aggregate)} != {expected_rows}"
        )
    required = list(EXTERNAL_REQUIRED) + ["id", "Unnamed: 0"]
    _require_columns(aggregate, required, label="external aggregate")
    ordered = aggregate.sort_values(["id", "Unnamed: 0"]).reset_index(drop=True)
    raw_ordered = raw.sort_values(["profile_id", "native_sample_idx"]).reset_index(drop=True)
    left = ordered[list(EXTERNAL_REQUIRED)].to_numpy(dtype=np.float64)
    right = raw_ordered[list(EXTERNAL_REQUIRED)].to_numpy(dtype=np.float64)
    if not np.array_equal(left, right):
        max_error = float(np.max(np.abs(left - right)))
        raise ValueError(f"external aggregate differs from raw profiles; max error={max_error}")


def harmonize_primary_1hz(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert the 2 Hz source profiles into profile-preserving 1 s bins.

    Boundary/electrical signals are averaged within each two-row bin. Thermal
    states use the last observation in the bin, matching a one-second state
    transition endpoint. A final single-row bin is retained for odd-length files.
    """

    _require_columns(frame, (*PRIMARY_REQUIRED, "native_sample_idx"), label="primary")
    work = pd.DataFrame(
        {
            "profile_id": frame["profile_id"].astype("int64"),
            "second_idx": frame["native_sample_idx"].floordiv(2).astype("int64"),
            "ambient": frame["ambient"],
            "coolant": frame["coolant"],
            "u_d": frame["u_d"],
            "u_q": frame["u_q"],
            "i_d": frame["i_d"],
            "i_q": frame["i_q"],
            "speed_rpm": frame["motor_speed"],
            "torque_nm": frame["torque"],
            "temp_winding": frame["stator_winding"],
            "temp_stator_core": (frame["stator_tooth"] + frame["stator_yoke"]) / 2.0,
            "temp_rotor": frame["pm"],
        }
    )
    keys = ["profile_id", "second_idx"]
    exogenous = [
        "ambient",
        "coolant",
        "u_d",
        "u_q",
        "i_d",
        "i_q",
        "speed_rpm",
        "torque_nm",
    ]
    targets = ["temp_winding", "temp_stator_core", "temp_rotor"]
    means = work.groupby(keys, sort=False, as_index=False)[exogenous].mean()
    endpoints = work.groupby(keys, sort=False, as_index=False)[targets].last()
    out = means.merge(endpoints, on=keys, validate="one_to_one", sort=False)
    out = out.rename(columns={"second_idx": "sample_idx"})
    out.insert(0, "machine_id", "source_52kw_pmsm")
    out.insert(0, "dataset", "primary_52kw")
    return out[list(HARMONIZED_COLUMNS)]


def harmonize_external_1hz(frame: pd.DataFrame) -> pd.DataFrame:
    """Map the native 1 Hz external IPMSM files to the three-node contract."""

    _require_columns(
        frame,
        (*EXTERNAL_REQUIRED, "profile_id", "native_sample_idx"),
        label="external",
    )
    out = pd.DataFrame(
        {
            "dataset": "external_ipmsm",
            "machine_id": "external_lptn_ipmsm",
            "profile_id": frame["profile_id"].astype("int64"),
            "sample_idx": frame["native_sample_idx"].astype("int64"),
            "ambient": frame["ambient"],
            "coolant": frame["water_outlet"],
            "u_d": frame["Ud"],
            "u_q": frame["Uq"],
            "i_d": frame["IdFbk"],
            "i_q": frame["IqFbk"],
            "speed_rpm": frame["speed"],
            "torque_nm": frame["Torque"],
            "temp_winding": (frame["activewind_1"] + frame["activewind_2"]) / 2.0,
            "temp_stator_core": (frame["slotbottom"] + frame["outer_yoke"]) / 2.0,
            "temp_rotor": frame["rotor"],
        }
    )
    return out[list(HARMONIZED_COLUMNS)]


def profile_manifest(frame: pd.DataFrame, *, sample_rate_hz: float) -> pd.DataFrame:
    """Return one auditable row per profile."""

    rows = (
        frame.groupby(["dataset", "machine_id", "profile_id"], sort=True)
        .agg(
            n_rows=("sample_idx", "size"),
            first_sample=("sample_idx", "min"),
            last_sample=("sample_idx", "max"),
            winding_min_c=("temp_winding", "min"),
            winding_max_c=("temp_winding", "max"),
            stator_core_min_c=("temp_stator_core", "min"),
            stator_core_max_c=("temp_stator_core", "max"),
            rotor_min_c=("temp_rotor", "min"),
            rotor_max_c=("temp_rotor", "max"),
        )
        .reset_index()
    )
    rows["sample_rate_hz"] = float(sample_rate_hz)
    rows["duration_seconds"] = rows["n_rows"] / float(sample_rate_hz)
    return rows

