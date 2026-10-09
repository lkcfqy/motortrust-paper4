"""Build and audit the anonymous landscape PDF supplement for Paper 4."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_jeet_pdfs as pdf_builder
import build_jeet_submission as shared

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "papers/paper4_thermal_transport"
SOURCE = PAPER_DIR / "supplementary_material.md"
OUTPUT = PAPER_DIR / "submission/Paper4_Supplementary_Material.pdf"


def configure() -> None:
    """Configure the shared deterministic PDF renderer for this paper."""

    shared.ROOT = ROOT
    shared.BIBLIOGRAPHY = ROOT / "references/key_papers.bib"
    shared.TITLE = "Do Electrothermal Models Transport Across PMSMs?"
    shared.SHORT_TITLE = "Electrothermal Model Transport Across PMSMs"
    shared.JOURNAL = "journal-neutral review"


def build() -> dict[str, object]:
    configure()
    pdf_builder.register_fonts()
    return pdf_builder.build_pdf(SOURCE, OUTPUT, supplement=True)


def audit() -> dict[str, object]:
    configure()
    pdf_builder.register_fonts()
    if not OUTPUT.is_file():
        raise FileNotFoundError(f"Missing Paper 4 supplementary PDF: {OUTPUT}")
    return pdf_builder.audit_pdf(OUTPUT, supplement=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = audit() if args.check else build()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
