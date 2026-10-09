from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.make_paper4_figures import bootstrap_budget_summary

ROOT = Path(__file__).resolve().parents[1]
FIGURE_DIR = ROOT / "papers" / "paper4_thermal_transport" / "figures"
STEMS = (
    "paper4_transport_performance",
    "paper4_support_adaptation",
    "paper4_budget_sensitivity",
    "paper4_uncertainty_tradeoff",
    "paper4_external_trajectories",
)


def test_budget_summary_bootstraps_complete_profile_means() -> None:
    data = pd.DataFrame(
        {
            "dataset": ["d"] * 4,
            "budget_seconds": [60] * 4,
            "method": ["m"] * 4,
            "profile_id": [1, 2, 3, 4],
            "macro_rmse_c": [1.0, 2.0, 3.0, 4.0],
        }
    )
    result = bootstrap_budget_summary(data).iloc[0]
    assert result["profiles"] == 4
    assert result["mean_rmse_c"] == 2.5
    assert result["ci_low_c"] < result["mean_rmse_c"] < result["ci_high_c"]


def test_paper4_exported_figures_exist_and_have_expected_headers() -> None:
    for stem in STEMS:
        png = FIGURE_DIR / f"{stem}.png"
        pdf = FIGURE_DIR / f"{stem}.pdf"
        assert png.stat().st_size > 50_000
        assert pdf.stat().st_size > 5_000
        assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert pdf.read_bytes()[:4] == b"%PDF"


def test_no_export_is_suspiciously_identical() -> None:
    sizes = np.asarray([(FIGURE_DIR / f"{stem}.png").stat().st_size for stem in STEMS])
    assert len(set(sizes.tolist())) == len(STEMS)

