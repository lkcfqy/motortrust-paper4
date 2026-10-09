from __future__ import annotations

from scripts.build_paper4_supplementary_material import OUTPUT, build_content


def test_paper4_supplement_contains_complete_evidence() -> None:
    content = build_content()
    for phrase in (
        "# S1. Dataset contract",
        "# S4. Complete matched-horizon method results",
        "13.1167-fold",
        "# S6. Complete trajectory-band audit",
        "1/16",
        "# S7. Support and abstention",
        "62.5%",
        "# S8. Numerical guard events",
        "999",
        "# S9. Reproducibility and immutable identifiers",
    ):
        assert phrase in content
    assert len(content.split()) > 2_000


def test_checked_in_paper4_supplement_is_current_when_present() -> None:
    if OUTPUT.is_file():
        assert OUTPUT.read_text(encoding="utf-8") == build_content()
