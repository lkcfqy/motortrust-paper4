from __future__ import annotations

from scripts.validate_paper4_evidence import (
    ROOT,
    build_report,
    validate_hashes,
    validate_manuscript,
    validate_primary_results,
    validate_support_uncertainty_and_budget,
)


def test_paper4_frozen_hashes() -> None:
    observed = validate_hashes(ROOT)
    assert len(observed) == 5


def test_paper4_headline_results() -> None:
    primary = validate_primary_results(ROOT)
    secondary = validate_support_uncertainty_and_budget(ROOT)
    assert primary["external_prior_clips"] == 999
    assert secondary["external_supported_profiles"] == 6
    assert secondary["raw_external_joint_coverage"] == "1/16"


def test_paper4_manuscript_and_figures() -> None:
    result = validate_manuscript(ROOT)
    assert result["word_count_approximate"] > 4_500
    assert result["citation_count"] >= 20
    assert result["figure_count"] == 5
    assert result["table_count"] == 4


def test_paper4_full_report_is_json_ready() -> None:
    report = build_report(ROOT)
    assert report["status"] == "pass"
