from __future__ import annotations

from scripts.build_paper4_supplementary_pdf import OUTPUT, SOURCE, audit


def test_paper4_supplement_source_is_present() -> None:
    assert SOURCE.is_file()
    assert SOURCE.stat().st_size > 20_000


def test_paper4_supplement_pdf_audit_when_present() -> None:
    if OUTPUT.is_file():
        result = audit()
        assert result["pages"] >= 5
