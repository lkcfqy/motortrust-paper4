"""Build journal-neutral Paper 4 DOCX and PDF manuscripts from frozen Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_paper2_submission as builder

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "papers/paper4_thermal_transport"
MANUSCRIPT = PAPER_DIR / "manuscript.md"
BIBLIOGRAPHY = ROOT / "references/key_papers.bib"
OUT_DIR = PAPER_DIR / "submission"
DOCX_OUT = OUT_DIR / "Paper4_Manuscript_Anonymous.docx"
PDF_OUT = OUT_DIR / "Paper4_Manuscript_Anonymous.pdf"
METADATA_OUT = OUT_DIR / "build_metadata.json"
SHORT_TITLE = "Electrothermal Model Transport Across PMSMs"

parse_markdown = builder.parse_markdown


def configure_builder() -> None:
    """Point the shared journal-neutral renderer at Paper 4 artifacts."""

    builder.ROOT = ROOT
    builder.PAPER_DIR = PAPER_DIR
    builder.MANUSCRIPT = MANUSCRIPT
    builder.BIBLIOGRAPHY = BIBLIOGRAPHY
    builder.OUT_DIR = OUT_DIR
    builder.DOCX_OUT = DOCX_OUT
    builder.PDF_OUT = PDF_OUT
    builder.METADATA_OUT = METADATA_OUT
    builder.SHORT_TITLE = SHORT_TITLE
    builder.ARTIFACT_LABEL = "Paper 4"
    builder.DOCUMENT_SUBJECT = "Journal-neutral Paper 4 submission draft"
    builder.EXPECTED_FIGURES = 5
    builder.EXPECTED_TABLES = 4


def audit_docx(path: Path) -> dict[str, Any]:
    configure_builder()
    return builder.audit_docx(path)


def build() -> dict[str, Any]:
    configure_builder()
    return builder.build()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_builder()
    if args.check:
        required = (DOCX_OUT, PDF_OUT, METADATA_OUT)
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Missing Paper 4 submission artifacts: {missing}")
        docx_audit = audit_docx(DOCX_OUT)
        reader = PdfReader(PDF_OUT)
        print(
            json.dumps(
                {
                    "status": "pass",
                    "docx": docx_audit,
                    "pdf_pages": len(reader.pages),
                },
                sort_keys=True,
            )
        )
        return
    print(json.dumps(build(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
