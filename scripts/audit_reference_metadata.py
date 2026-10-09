"""Resolve cited bibliography metadata against Crossref, DataCite, or source URLs.

This is a pre-submission audit. It never edits the bibliography. Network responses are
written as a dated snapshot so that any discrepancy can be reviewed before citation
metadata is changed.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "paper" / "manuscript.md"
BIBLIOGRAPHY = ROOT / "references" / "key_papers.bib"
DEFAULT_JSON = ROOT / "results" / "reference_metadata_audit" / "audit.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "reference_metadata_audit.md"
USER_AGENT = "pmsm-sci-reference-audit/0.1"
TITLE_SIMILARITY_MINIMUM = 0.85


@dataclass(frozen=True)
class BibRecord:
    entry_type: str
    key: str
    fields: dict[str, str]


@dataclass(frozen=True)
class AuditRow:
    key: str
    identifier: str
    provider: str
    resolved: bool
    local_title: str
    remote_title: str
    title_similarity: float
    local_year: int | None
    remote_years: tuple[int, ...]
    local_first_author: str
    remote_first_author: str
    author_match: bool | None
    year_match: bool | None
    status: str
    source_url: str


def parse_bibtex(path: Path) -> dict[str, BibRecord]:
    """Parse brace-delimited fields used by this project's BibTeX file."""

    text = path.read_text(encoding="utf-8")
    records: dict[str, BibRecord] = {}
    index = 0
    while match := re.search(r"@(\w+)\s*\{\s*([^,]+),", text[index:]):
        entry_type = match.group(1).lower()
        key = match.group(2).strip()
        start = index + match.end()
        cursor = start
        depth = 1
        while cursor < len(text) and depth:
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth:
            raise ValueError(f"Unclosed BibTeX entry: {key}")
        body = text[start : cursor - 1]
        fields: dict[str, str] = {}
        position = 0
        while field_match := re.search(r"(\w+)\s*=\s*", body[position:]):
            name = field_match.group(1).lower()
            value_start = position + field_match.end()
            if value_start >= len(body) or body[value_start] != "{":
                position = value_start + 1
                continue
            value_cursor = value_start + 1
            value_depth = 1
            while value_cursor < len(body) and value_depth:
                if body[value_cursor] == "{":
                    value_depth += 1
                elif body[value_cursor] == "}":
                    value_depth -= 1
                value_cursor += 1
            fields[name] = body[value_start + 1 : value_cursor - 1].strip()
            position = value_cursor
        records[key] = BibRecord(entry_type=entry_type, key=key, fields=fields)
        index = cursor
    return records


def cited_keys(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    return tuple(sorted(set(re.findall(r"@([A-Za-z0-9_:-]+)", text))))


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\\[\"'`^~=.uvHckbdtr]\s*\{?([A-Za-z])\}?", r"\1", value)
    value = re.sub(r"\\[A-Za-z]+", " ", value)
    value = value.replace("{", "").replace("}", "")
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def normalize_person(value: str) -> str:
    return normalize_text(value).replace(" ", "")


def first_author_family(value: str) -> str:
    first = value.split(" and ", 1)[0].strip()
    family = first.split(",", 1)[0] if "," in first else first.split()[-1]
    return normalize_person(family)


def title_similarity(local: str, remote: str) -> float:
    return SequenceMatcher(None, normalize_text(local), normalize_text(remote)).ratio()


def _year_parts(message: dict[str, Any]) -> tuple[int, ...]:
    years: set[int] = set()
    for field in ("published", "published-print", "published-online", "issued"):
        parts = message.get(field, {}).get("date-parts", [])
        if parts and parts[0]:
            years.add(int(parts[0][0]))
    return tuple(sorted(years))


def _get(url: str, *, timeout: float) -> requests.Response:
    for attempt in range(4):
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if response.status_code not in {429, 500, 502, 503, 504}:
            return response
        retry_after = response.headers.get("Retry-After", "")
        delay = float(retry_after) if retry_after.isdigit() else 1.5 * (attempt + 1)
        time.sleep(min(delay, 10.0))
    return response


def _crossref(doi: str, timeout: float) -> dict[str, Any] | None:
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    response = _get(url, timeout=timeout)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    message = response.json()["message"]
    authors = message.get("author", [])
    return {
        "provider": "Crossref",
        "title": (message.get("title") or [""])[0],
        "years": _year_parts(message),
        "first_author": normalize_person(authors[0].get("family", "")) if authors else "",
        "url": message.get("URL", f"https://doi.org/{doi}"),
    }


def _datacite(doi: str, timeout: float) -> dict[str, Any] | None:
    url = f"https://api.datacite.org/dois/{quote(doi, safe='')}"
    response = _get(url, timeout=timeout)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    attributes = response.json()["data"]["attributes"]
    titles = attributes.get("titles") or []
    creators = attributes.get("creators") or []
    year = attributes.get("publicationYear")
    return {
        "provider": "DataCite",
        "title": titles[0].get("title", "") if titles else "",
        "years": (int(year),) if year else (),
        "first_author": normalize_text(creators[0].get("name", "")) if creators else "",
        "url": attributes.get("url", f"https://doi.org/{doi}"),
    }


def _url_metadata(url: str, local_title: str, timeout: float) -> dict[str, Any]:
    response = _get(url, timeout=timeout)
    response.raise_for_status()
    body = normalize_text(response.text)
    normalized_title = normalize_text(local_title)
    title_match = normalized_title in body
    return {
        "provider": "Publisher URL",
        "title": local_title if title_match else "",
        "years": (),
        "first_author": "",
        "url": response.url,
    }


def audit_record(record: BibRecord, *, timeout: float = 30.0) -> AuditRow:
    fields = record.fields
    local_title = fields.get("title", "")
    local_year = int(fields["year"]) if fields.get("year", "").isdigit() else None
    local_author = first_author_family(fields.get("author", ""))
    doi = fields.get("doi", "").strip()
    url = fields.get("url", "").strip()
    identifier = doi or url
    try:
        remote = _crossref(doi, timeout) if doi else None
        if doi and remote is None:
            remote = _datacite(doi, timeout)
        if not doi:
            remote = _url_metadata(url, local_title, timeout)
        if remote is None:
            raise LookupError("identifier did not resolve")
        similarity = title_similarity(local_title, remote["title"])
        remote_years = tuple(remote["years"])
        remote_author = remote["first_author"]
        remote_author_tokens = {normalize_person(token) for token in remote_author.split()}
        author_match = None if not local_author or not remote_author else (
            local_author == normalize_person(remote_author) or local_author in remote_author_tokens
        )
        year_match = (
            None
            if not remote_years or local_year is None
            else any(abs(local_year - remote_year) <= 1 for remote_year in remote_years)
        )
        checks = [similarity >= TITLE_SIMILARITY_MINIMUM]
        if author_match is not None:
            checks.append(author_match)
        if year_match is not None:
            checks.append(year_match)
        status = "pass" if all(checks) else "review"
        return AuditRow(
            key=record.key,
            identifier=identifier,
            provider=remote["provider"],
            resolved=True,
            local_title=local_title,
            remote_title=remote["title"],
            title_similarity=similarity,
            local_year=local_year,
            remote_years=remote_years,
            local_first_author=local_author,
            remote_first_author=remote_author,
            author_match=author_match,
            year_match=year_match,
            status=status,
            source_url=remote["url"],
        )
    except (LookupError, requests.RequestException, KeyError, ValueError) as exc:
        return AuditRow(
            key=record.key,
            identifier=identifier,
            provider="unresolved",
            resolved=False,
            local_title=local_title,
            remote_title="",
            title_similarity=0.0,
            local_year=local_year,
            remote_years=(),
            local_first_author=local_author,
            remote_first_author="",
            author_match=None,
            year_match=None,
            status=f"error: {type(exc).__name__}: {exc}",
            source_url=f"https://doi.org/{doi}" if doi else url,
        )


def markdown_report(rows: list[AuditRow], *, as_of: str) -> str:
    passed = sum(row.status == "pass" for row in rows)
    resolved = sum(row.resolved for row in rows)
    lines = [
        "# Cited-reference metadata audit",
        "",
        f"As of: {as_of}",
        "",
        (
            f"The anonymous manuscript cites {len(rows)} unique references. "
            f"{resolved}/{len(rows)} identifiers resolved and {passed}/{len(rows)} "
            "passed title, first-author, and available year checks."
        ),
        "",
        (
            "This is a metadata-resolution audit, not a judgment of scientific quality. "
            "Crossref and DataCite records are preferred; the two DOI-free PMLR entries "
            "are checked against their publisher pages. A `review` row must be inspected "
            "before submission rather than changed automatically."
        ),
        "",
        "| Citation key | Provider | Identifier | Title similarity | Year | Status |",
        "|---|---|---|---:|---|---|",
    ]
    for row in rows:
        remote_years = ", ".join(str(year) for year in row.remote_years) or "n/a"
        year_text = f"{row.local_year} / {remote_years}"
        identifier = row.identifier.replace("|", "\\|")
        lines.append(
            f"| `{row.key}` | {row.provider} | `{identifier}` | "
            f"{row.title_similarity:.3f} | {year_text} | {row.status} |"
        )
    lines.extend(
        [
            "",
            "## Evidence boundary",
            "",
            (
                "- Resolution confirms that an identifier and closely matching metadata "
                "exist; it does not confirm that every narrative claim accurately summarizes "
                "the paper."
            ),
            (
                "- Year checks allow a one-year online-first versus issue-year difference; "
                "the local and remote years remain visible in the table."
            ),
            "- Publisher metadata can change. Re-run this audit on the submission date.",
            "- No bibliography field is modified automatically.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuscript", type=Path, default=MANUSCRIPT)
    parser.add_argument("--bibliography", type=Path, default=BIBLIOGRAPHY)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30.0)
    current_date = datetime.now(tz=ZoneInfo("Asia/Shanghai")).date().isoformat()
    parser.add_argument("--as-of", default=current_date)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = parse_bibtex(args.bibliography)
    keys = cited_keys(args.manuscript)
    missing = sorted(set(keys).difference(records))
    if missing:
        raise ValueError(f"Cited keys missing from bibliography: {missing}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(
            pool.map(
                lambda key: audit_record(records[key], timeout=args.timeout),
                keys,
            )
        )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": args.as_of,
        "cited_references": len(rows),
        "resolved": sum(row.resolved for row in rows),
        "passed": sum(row.status == "pass" for row in rows),
        "rows": [asdict(row) for row in rows],
    }
    args.json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    args.markdown.write_text(markdown_report(rows, as_of=args.as_of), encoding="utf-8")
    failed = [row.key for row in rows if row.status != "pass"]
    print(json.dumps({key: payload[key] for key in ("cited_references", "resolved", "passed")}))
    if failed:
        raise SystemExit(f"Reference metadata requires review: {failed}")


if __name__ == "__main__":
    main()
