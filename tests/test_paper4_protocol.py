from __future__ import annotations

import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "paper4_thermal_transport.yaml"


def load_protocol() -> dict[str, object]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_paper4_source_profile_roles_are_complete_and_disjoint() -> None:
    config = load_protocol()
    roles = config["source_roles"]
    train = set(roles["train_profiles"])
    validation = set(roles["validation_profiles"])
    test = set(roles["locked_test_profiles"])
    expected = {
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        23,
        24,
        26,
        27,
        29,
        30,
        31,
        32,
        36,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        48,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
        62,
        63,
        64,
        65,
        66,
        67,
        68,
        69,
        70,
        71,
        72,
        73,
        74,
        75,
        76,
        78,
        79,
        80,
        81,
    }
    assert not (train & validation or train & test or validation & test)
    assert train | validation | test == expected
    assert (len(train), len(validation), len(test)) == (44, 11, 14)


def test_paper4_timeline_is_feasible_for_locked_profile_minima() -> None:
    config = load_protocol()
    timeline = config["timeline"]
    total = timeline["commissioning_prefix_seconds"] + timeline["matched_evaluation_seconds"]
    assert total == 1500
    assert total <= math.floor(25.6 * 60)
    assert timeline["commissioning_prefix_seconds"] + timeline[
        "source_long_evaluation_seconds"
    ] == 3600


def test_paper4_trajectory_quantile_is_finite_and_frozen() -> None:
    config = load_protocol()
    uncertainty = config["uncertainty"]
    n = uncertainty["calibration_profiles"]
    coverage = uncertainty["nominal_trajectory_coverage"]
    rank = math.ceil((n + 1) * coverage)
    assert n == 11
    assert rank == uncertainty["quantile_rank"] == 11


def test_paper4_methods_and_forbidden_external_outputs_are_unique() -> None:
    config = load_protocol()
    locked = config["methods"]["locked"]
    forbidden = config["harmonization"]["forbidden_external_columns"]
    assert len(locked) == len(set(locked)) == 8
    assert set(forbidden) == {"active_wind_est", "stator_est", "rotor_est"}

