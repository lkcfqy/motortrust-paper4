from __future__ import annotations

from scripts.build_paper4_submission import DOCX_OUT, MANUSCRIPT, audit_docx, parse_markdown


def test_paper4_markdown_parser_finds_submission_structure() -> None:
    title, blocks = parse_markdown(MANUSCRIPT)
    assert title.startswith("Do Electrothermal Models Transport")
    assert sum(block.kind == "image" for block in blocks) == 5
    assert sum(block.kind == "table" for block in blocks) == 4
    assert sum(block.kind == "number" for block in blocks) >= 7


def test_generated_paper4_docx_structural_audit_when_artifact_exists() -> None:
    if DOCX_OUT.is_file():
        result = audit_docx(DOCX_OUT)
        assert result["tables"] == 4
        assert result["inline_drawings"] == 5
