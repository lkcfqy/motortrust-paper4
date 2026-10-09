"""Mechanically validate Paper 4 frozen evidence and manuscript artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_reference_metadata import cited_keys, parse_bibtex

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "papers/paper4_thermal_transport"
RESULT_DIR = ROOT / "results/paper4_thermal_transport"
DIAGNOSTIC_DIR = ROOT / "results/paper4_transport_diagnostics"
FIGURE_STEMS = (
    "paper4_transport_performance",
    "paper4_support_adaptation",
    "paper4_budget_sensitivity",
    "paper4_uncertainty_tradeoff",
    "paper4_external_trajectories",
)
EXPECTED_HASHES = {
    "protocol_config": "5e98e959b557b69f2c0d2c0f2b035290751ce135cb3a225f8d6b79a8e5c1bc63",
    "protocol_document": "ad0834d5e5693e9bc210932a9d41bafead580b7d6ddc40a6f2cde5e4ef336620",
    "source_csv": "78f3d150f0f2ad9c5dc7ff24dd12c00d386ad530f48c1589ad24fcd88867d3ad",
    "selection_freeze": "1fa8dc73b38ec597e82862c862062928d33cb0a8272f71788f7df78d854f3bd0",
}
EXPECTED_EXTERNAL_COMMIT = "98e4566b5fb7c70499996fda18dd73179ec16509"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("papers/paper4_thermal_transport/evidence_validation.json"),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_close(actual: float, expected: float, *, tolerance: float = 1e-10) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=tolerance):
        raise AssertionError(f"expected {expected}, got {actual}")


def validate_hashes(root: Path) -> dict[str, str]:
    paths = {
        "protocol_config": root / "configs/paper4_thermal_transport.yaml",
        "protocol_document": root / "docs/paper4_protocol.md",
        "source_csv": root / "data/raw/electric_motor_temperature/measures_v2.csv",
        "selection_freeze": root
        / "results/paper4_thermal_transport/selection_freeze.json",
    }
    observed = {name: sha256(path) for name, path in paths.items()}
    if observed != EXPECTED_HASHES:
        difference = {
            key: {"expected": EXPECTED_HASHES[key], "observed": observed[key]}
            for key in EXPECTED_HASHES
            if observed[key] != EXPECTED_HASHES[key]
        }
        raise AssertionError(f"Paper 4 frozen hash mismatch: {difference}")

    repository = root / "data/raw/lptn_informed_lstm"
    completed = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip()
    if commit != EXPECTED_EXTERNAL_COMMIT:
        raise AssertionError(f"external commit mismatch: {commit}")
    observed["external_repository_commit"] = commit
    return observed


def _aggregate_row(
    aggregate: pd.DataFrame, dataset: str, role: str, method: str
) -> pd.Series:
    row = aggregate.loc[
        aggregate["dataset"].eq(dataset)
        & aggregate["role"].eq(role)
        & aggregate["method"].eq(method)
        & aggregate["horizon"].eq("matched_20min")
        & aggregate["node"].eq("macro")
    ]
    if len(row) != 1:
        raise AssertionError(f"expected one aggregate row for {dataset}/{role}/{method}")
    return row.iloc[0]


def validate_primary_results(root: Path) -> dict[str, Any]:
    aggregate = pd.read_csv(root / "results/paper4_thermal_transport/aggregate_summary.csv")
    source_raw = _aggregate_row(
        aggregate, "primary_52kw", "source_test", "source_positive_thermal_network_raw"
    )
    external_raw = _aggregate_row(
        aggregate, "external_ipmsm", "external_test", "source_positive_thermal_network_raw"
    )
    source_prior = _aggregate_row(
        aggregate,
        "primary_52kw",
        "source_test",
        "source_prior_prefix_calibrated_thermal_network",
    )
    external_prior = _aggregate_row(
        aggregate,
        "external_ipmsm",
        "external_test",
        "source_prior_prefix_calibrated_thermal_network",
    )
    external_target = _aggregate_row(
        aggregate,
        "external_ipmsm",
        "external_test",
        "target_only_prefix_positive_thermal_network",
    )
    external_boundary = _aggregate_row(
        aggregate, "external_ipmsm", "external_test", "boundary_shift_persistence"
    )
    expected = (
        (source_raw, "mean_rmse_c", 1.8672988348161428),
        (external_raw, "mean_rmse_c", 24.492828959871908),
        (source_prior, "mean_rmse_c", 13.507619404576074),
        (external_prior, "mean_rmse_c", 13.61043422354438),
        (external_target, "mean_rmse_c", 6.0175187393077625),
        (external_boundary, "mean_rmse_c", 6.1664022567972),
    )
    for row, column, value in expected:
        assert_close(float(row[column]), value)
    if int(external_prior["total_clip_count"]) != 999:
        raise AssertionError("external source-prior guard count must remain 999")
    if int(source_prior["total_clip_count"]) != 45:
        raise AssertionError("source source-prior guard count must remain 45")

    gates = json.loads(
        (root / "results/paper4_thermal_transport/predeclared_gates.json").read_text(
            encoding="utf-8"
        )
    )
    if gates["source_adaptation"]["pass"] is not False:
        raise AssertionError("source adaptation gate must remain failed")
    if gates["external_adaptation"]["pass"] is not True:
        raise AssertionError("external comparator gate must remain an arithmetic pass")
    if gates["source_uncertainty"]["pass"] is not True:
        raise AssertionError("source uncertainty gate must remain passed")

    return {
        "source_raw_rmse_c": float(source_raw["mean_rmse_c"]),
        "external_raw_rmse_c": float(external_raw["mean_rmse_c"]),
        "raw_transport_ratio": float(external_raw["mean_rmse_c"])
        / float(source_raw["mean_rmse_c"]),
        "source_prior_source_rmse_c": float(source_prior["mean_rmse_c"]),
        "source_prior_external_rmse_c": float(external_prior["mean_rmse_c"]),
        "target_only_external_rmse_c": float(external_target["mean_rmse_c"]),
        "external_prior_clips": int(external_prior["total_clip_count"]),
        "gates": gates,
    }


def validate_support_uncertainty_and_budget(root: Path) -> dict[str, Any]:
    support = pd.read_csv(
        root / "results/paper4_transport_diagnostics/support_stratified_summary.csv"
    )
    external = support.loc[support["dataset"].eq("external_ipmsm")]
    prior = external.loc[
        external["method"].eq("source_prior_prefix_calibrated_thermal_network")
    ]
    if sorted(prior["profiles"].astype(int).tolist()) != [6, 10]:
        raise AssertionError("external support partition must remain 6 supported / 10 unsupported")
    supported = prior.loc[prior["supported"].astype(str).str.lower().eq("true")].iloc[0]
    unsupported = prior.loc[prior["supported"].astype(str).str.lower().eq("false")].iloc[0]
    assert_close(float(supported["mean_rmse_c"]), 3.1933097620965776)
    assert_close(float(unsupported["mean_rmse_c"]), 19.860708900413062)
    if int(unsupported["total_clip_count"]) != 999:
        raise AssertionError("all external prior clips must remain in the unsupported set")

    bands = pd.read_csv(
        root / "results/paper4_thermal_transport/trajectory_band_joint_summary.csv"
    )
    raw_external = bands.loc[
        bands["dataset"].eq("external_ipmsm")
        & bands["method"].eq("source_positive_thermal_network_raw")
    ].iloc[0]
    prior_external = bands.loc[
        bands["dataset"].eq("external_ipmsm")
        & bands["method"].eq("source_prior_prefix_calibrated_thermal_network")
    ].iloc[0]
    if (int(raw_external["covered"]), int(raw_external["profiles"])) != (1, 16):
        raise AssertionError("raw external joint coverage must remain 1/16")
    if (int(prior_external["covered"]), int(prior_external["profiles"])) != (15, 16):
        raise AssertionError("source-prior external joint coverage must remain 15/16")

    diagnostic = json.loads(
        (root / "results/paper4_transport_diagnostics/interpretation.json").read_text(
            encoding="utf-8"
        )
    )
    assert_close(
        float(diagnostic["uncertainty"]["proposed_mean_matched_half_width_c"]),
        106.06874172036748,
    )

    budget = pd.read_csv(
        root / "results/paper4_thermal_transport/budget_sensitivity_summary.csv"
    )
    target_15 = budget.loc[
        budget["dataset"].eq("external_ipmsm")
        & budget["method"].eq("target_only_prefix_positive_thermal_network")
        & budget["budget_seconds"].eq(900)
    ].iloc[0]
    assert_close(float(target_15["mean_macro_rmse_c"]), 2.065306560864155)
    if int(target_15["total_clip_count"]) != 0:
        raise AssertionError("15-minute external target-only result must have zero clips")

    return {
        "external_supported_profiles": 6,
        "external_unsupported_profiles": 10,
        "supported_prior_rmse_c": float(supported["mean_rmse_c"]),
        "unsupported_prior_rmse_c": float(unsupported["mean_rmse_c"]),
        "raw_external_joint_coverage": "1/16",
        "prior_external_joint_coverage": "15/16",
        "prior_mean_half_width_c": float(
            diagnostic["uncertainty"]["proposed_mean_matched_half_width_c"]
        ),
        "target_only_15min_external_rmse_c": float(target_15["mean_macro_rmse_c"]),
    }


def validate_manuscript(root: Path) -> dict[str, Any]:
    manuscript = root / "papers/paper4_thermal_transport/manuscript.md"
    text = manuscript.read_text(encoding="utf-8")
    required = (
        "13.12-fold",
        "1/16",
        "999",
        "62.5%",
        "106.07 °C",
        "target-only",
        "post-reveal",
        "not a distribution-free cross-machine guarantee",
        "Only two physical machines",
    )
    missing = [phrase for phrase in required if phrase not in text]
    if missing:
        raise AssertionError(f"manuscript missing required evidence phrases: {missing}")

    bibliography = parse_bibtex(root / "references/key_papers.bib")
    citations = cited_keys(manuscript)
    missing_citations = sorted(set(citations) - set(bibliography))
    if missing_citations:
        raise AssertionError(f"manuscript citations missing from BibTeX: {missing_citations}")
    if len(citations) < 20:
        raise AssertionError("Paper 4 manuscript must cite at least 20 unique sources")

    figure_hashes: dict[str, dict[str, str]] = {}
    for stem in FIGURE_STEMS:
        paths = {
            suffix: root / "papers/paper4_thermal_transport/figures" / f"{stem}.{suffix}"
            for suffix in ("png", "pdf")
        }
        for path in paths.values():
            if not path.is_file() or path.stat().st_size < 10_000:
                raise AssertionError(f"missing or undersized figure: {path}")
        figure_hashes[stem] = {suffix: sha256(path) for suffix, path in paths.items()}

    return {
        "word_count_approximate": len(text.split()),
        "citation_count": len(citations),
        "figure_count": text.count("![Figure "),
        "table_count": text.count("**Table "),
        "manuscript_sha256": sha256(manuscript),
        "figure_hashes": figure_hashes,
    }


def build_report(root: Path) -> dict[str, Any]:
    return {
        "created_utc": datetime.now(UTC).isoformat(),
        "status": "pass",
        "frozen_hashes": validate_hashes(root),
        "primary_results": validate_primary_results(root),
        "support_uncertainty_budget": validate_support_uncertainty_and_budget(root),
        "manuscript": validate_manuscript(root),
    }


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    payload = build_report(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote validation report to {output}")


if __name__ == "__main__":
    main()
