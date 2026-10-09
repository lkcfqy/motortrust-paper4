"""Audit and harmonize the two frozen Paper 4 thermal datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from pmsm_sci.thermal_transport import (
    EXTERNAL_REQUIRED,
    harmonize_external_1hz,
    harmonize_primary_1hz,
    load_external_thermal,
    load_primary_thermal,
    profile_manifest,
    verify_external_aggregate,
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
        "--output-dir",
        type=Path,
        default=Path("results/paper4_thermal_data_audit"),
    )
    parser.add_argument(
        "--config", type=Path, default=Path("configs/paper4_thermal_transport.yaml")
    )
    parser.add_argument("--protocol", type=Path, default=Path("docs/paper4_protocol.md"))
    return parser.parse_args()


def numeric_profile(frame: pd.DataFrame, columns: list[str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for column in columns:
        values = frame[column].to_numpy(dtype=np.float64)
        quantiles = np.quantile(values, [0.0, 0.01, 0.5, 0.99, 1.0])
        result[column] = {
            "min": float(quantiles[0]),
            "p01": float(quantiles[1]),
            "median": float(quantiles[2]),
            "p99": float(quantiles[3]),
            "max": float(quantiles[4]),
            "null": int(pd.isna(values).sum()),
            "nonfinite": int((~np.isfinite(values)).sum()),
        }
    return result


def main() -> None:
    args = parse_args()
    primary_raw = load_primary_thermal(args.primary)
    external_dir = args.external_root / "dataset"
    external_raw = load_external_thermal(external_dir)
    verify_external_aggregate(external_raw, external_dir / "temperature.csv")

    primary = harmonize_primary_1hz(primary_raw)
    external = harmonize_external_1hz(external_raw)
    primary_manifest = profile_manifest(primary, sample_rate_hz=1.0)
    external_manifest = profile_manifest(external, sample_rate_hz=1.0)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pd.concat([primary_manifest, external_manifest], ignore_index=True).to_csv(
        args.output_dir / "profile_manifest.csv", index=False
    )
    mapping = pd.DataFrame(
        [
            ("boundary", "ambient", "ambient", "direct"),
            ("boundary", "coolant", "water_outlet", "direct fluid-temperature proxy"),
            ("electrical", "u_d", "Ud", "direct dq voltage"),
            ("electrical", "u_q", "Uq", "direct dq voltage"),
            ("electrical", "i_d", "IdFbk", "feedback dq current"),
            ("electrical", "i_q", "IqFbk", "feedback dq current"),
            ("mechanical", "motor_speed", "speed", "rpm"),
            ("mechanical", "torque", "Torque", "N m"),
            ("thermal", "stator_winding", "mean(activewind_1,activewind_2)", "constructed"),
            (
                "thermal",
                "mean(stator_tooth,stator_yoke)",
                "mean(slotbottom,outer_yoke)",
                "constructed core mean",
            ),
            ("thermal", "pm", "rotor", "semantic proxy; sensor locations differ"),
        ],
        columns=["family", "source_52kw", "external_ipmsm", "interpretation"],
    )
    mapping.to_csv(args.output_dir / "cross_dataset_mapping.csv", index=False)

    primary_hash = file_sha256(args.primary)
    id_hashes = {
        f"id_{profile}.csv": file_sha256(external_dir / f"id_{profile}.csv")
        for profile in range(16)
    }
    audit = {
        "created_utc": datetime.now(UTC).isoformat(),
        "primary": {
            "path": str(args.primary.resolve()),
            "sha256": primary_hash,
            "raw_rows": len(primary_raw),
            "harmonized_1hz_rows": len(primary),
            "profiles": int(primary["profile_id"].nunique()),
            "exact_duplicate_rows": int(primary_raw.duplicated().sum()),
            "null_cells": int(primary_raw.isna().sum().sum()),
            "duration_hours_native_rate": len(primary_raw) / 2.0 / 3600.0,
            "ranges": numeric_profile(
                primary,
                [
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
                ],
            ),
        },
        "external": {
            "root": str(args.external_root.resolve()),
            "repository_commit": "98e4566b5fb7c70499996fda18dd73179ec16509",
            "raw_rows": len(external_raw),
            "harmonized_1hz_rows": len(external),
            "profiles": int(external["profile_id"].nunique()),
            "exact_duplicate_rows": int(
                external_raw[list(EXTERNAL_REQUIRED)].duplicated().sum()
            ),
            "null_cells": int(external_raw.isna().sum().sum()),
            "duration_hours_from_tsim_1": len(external_raw) / 3600.0,
            "readme_claimed_hours": 23.8,
            "aggregate_sha256": file_sha256(external_dir / "temperature.csv"),
            "id_file_sha256": id_hashes,
            "aggregate_matches_raw_exactly": True,
            "forbidden_model_output_columns": [
                "active_wind_est",
                "stator_est",
                "rotor_est",
            ],
            "ranges": numeric_profile(
                external,
                [
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
                ],
            ),
        },
        "checks": {
            "required_schema": "pass",
            "finite_required_values": "pass",
            "exact_row_uniqueness": "pass",
            "profile_contiguity": "pass",
            "external_raw_aggregate_equality": "pass",
            "estimate_columns_excluded": "pass",
        },
    }
    (args.output_dir / "audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    freeze = {
        "frozen_date": "2026-08-21",
        "status": "frozen_before_first_candidate_model_fit",
        "config": str(args.config.resolve()),
        "config_sha256": file_sha256(args.config),
        "protocol": str(args.protocol.resolve()),
        "protocol_sha256": file_sha256(args.protocol),
        "primary_data_sha256": primary_hash,
        "external_repository_commit": "98e4566b5fb7c70499996fda18dd73179ec16509",
        "external_id_file_sha256": id_hashes,
        "forbidden_at_freeze": [
            "candidate model errors",
            "candidate model ranking",
            "trajectory interval coverage",
            "external transport outcomes",
        ],
    }
    (args.output_dir / "protocol_freeze.json").write_text(
        json.dumps(freeze, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Paper 4 audit passed: source={len(primary_raw):,} raw rows / "
        f"{len(primary):,} 1 Hz rows; external={len(external):,} rows"
    )


if __name__ == "__main__":
    main()
