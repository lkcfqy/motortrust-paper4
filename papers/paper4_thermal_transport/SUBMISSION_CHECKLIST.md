# Paper 4 submission checklist

Updated: 2026-08-21

## Technical package

- [x] Protocol-frozen manuscript retains direct transport failure, the failed source-adaptation
  gate, external numerical failure, 62.5% abstention, and 106.07 °C band width as primary evidence.
- [x] Two raw datasets audited: 1,330,816 source rows/69 profiles and 97,725 external rows/16
  profiles; no nulls, duplicates, or profile fragmentation.
- [x] External published estimate columns blocked from all target-blind fitting, selection, support,
  and evaluation.
- [x] Source split is complete-profile disjoint: 44 train, 11 validation, and 14 locked test.
- [x] Eight frozen methods use the same five-minute prefix boundary and 20-minute recursive rollout;
  the target-specific published LPTN is context only.
- [x] Validation-only selection reproduces Ridge alpha 100 and source-prior penalty 0.1.
- [x] Source-test and external outcomes reproduce all manuscript headline values and predeclared
  gate statuses.
- [x] Five publication figures checked for legibility, clipping, and honest scales.
- [x] Evidence validator passes raw-data, protocol, configuration, selection, result, citation, and
  figure checks.
- [x] Supplementary material is mechanically generated from frozen results and checked for drift.
- [x] Anonymous DOCX structural audit passes with 160 paragraphs, four tables, five inline figures,
  and 21 references.
- [x] Microsoft Word rendering inspected page by page: 16 pages with no clipping, overlap, missing
  figures, broken references, or raw LaTeX tokens.
- [x] Journal-neutral manuscript PDF and seven-page landscape supplement generated and structurally
  audited.
- [x] Reproducibility bundle built from 79 source artifacts; embedded member hashes audited and raw
  third-party data excluded.
- [x] Full repository Ruff gate and all 269 pytest tests passed before the final bundle rebuild; the
  bundle audit was rerun after creation.

## Author and target-journal fields

- [ ] Insert final author names, affiliations, corresponding-author address, and ORCID IDs.
- [ ] Confirm funding, competing-interest language, CRediT contributions, and the generative-AI
  disclosure with every author.
- [ ] Deposit code and the reproducibility bundle; replace repository placeholder text with the
  public URL and archival DOI.
- [ ] Select the target journal and apply its current template, word limit, reference style, figure
  resolution, data-availability, and declaration rules.
- [ ] Re-render and inspect the journal-templated version after pagination changes.
- [ ] Prepare journal-specific highlights, graphical abstract, cover letter, and suggested reviewers
  if required.

Unchecked author/journal items are administrative. They do not authorize changing the frozen
scientific result, excluding unsupported profiles, or describing the accepted external subset as
fleet validation.
