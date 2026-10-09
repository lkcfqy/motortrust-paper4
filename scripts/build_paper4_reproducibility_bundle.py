"""Create and verify the anonymous, hash-audited Paper 4 reproducibility bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "papers/paper4_thermal_transport"
OUT_DIR = PAPER_DIR / "submission"
ZIP_OUT = OUT_DIR / "Paper4_Reproducibility_Bundle.zip"
MANIFEST_OUT = OUT_DIR / "Paper4_Reproducibility_Bundle_manifest.json"
BUNDLE_ROOT = "paper4_reproducibility"
TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_DRIVE = b"c:"
_BACKSLASH = b"\\"
_FORWARD_SLASH = b"/"
FORBIDDEN_BYTES = (
    _DRIVE + _BACKSLASH + b"users",
    _DRIVE + _FORWARD_SLASH + b"users",
    _DRIVE + _BACKSLASH + b"lkc" + _BACKSLASH + b"phd sci",
    _DRIVE + _FORWARD_SLASH + b"lkc/phd sci",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _explicit_files() -> list[tuple[str, Path]]:
    return [
        ("environment", ROOT / "pyproject.toml"),
        ("bibliography", ROOT / "references/key_papers.bib"),
        ("configuration", ROOT / "configs/paper4_thermal_transport.yaml"),
        ("paper", PAPER_DIR / "manuscript.md"),
        ("paper", PAPER_DIR / "supplementary_material.md"),
        ("paper", PAPER_DIR / "evidence_validation.json"),
        ("paper", PAPER_DIR / "README_REPRODUCE.md"),
        ("paper", PAPER_DIR / "SUBMISSION_CHECKLIST.md"),
        ("paper", PAPER_DIR / "outline.md"),
        ("submission", OUT_DIR / "Paper4_Manuscript_Anonymous.docx"),
        ("submission", OUT_DIR / "Paper4_Manuscript_Anonymous.pdf"),
        ("submission", OUT_DIR / "Paper4_Supplementary_Material.pdf"),
        ("submission", OUT_DIR / "build_metadata.json"),
    ]


def bundle_sources(root: Path = ROOT) -> list[tuple[str, Path]]:
    paper_dir = root / "papers/paper4_thermal_transport"
    explicit = _explicit_files() if root == ROOT else [
        (category, root / path.relative_to(ROOT)) for category, path in _explicit_files()
    ]
    documentation = [
        ("documentation", path)
        for path in sorted((root / "docs").glob("paper4_*.md"))
    ]
    scripts = [
        ("script", path)
        for path in sorted((root / "scripts").glob("*.py"))
        if "paper4" in path.name or "thermal" in path.name
    ]
    tests = [
        ("test", path)
        for path in sorted((root / "tests").glob("*.py"))
        if "paper4" in path.name or "thermal" in path.name
    ]
    modules = [
        ("module", path)
        for path in sorted((root / "src/pmsm_sci").glob("thermal*.py"))
    ]
    figures = [
        ("figure", path)
        for path in sorted((paper_dir / "figures").glob("paper4_*.*"))
    ]
    result_dirs = (
        root / "results/paper4_thermal_data_audit",
        root / "results/paper4_thermal_transport",
        root / "results/paper4_transport_diagnostics",
    )
    results = [
        ("result", path)
        for directory in result_dirs
        if directory.is_dir()
        for path in sorted(item for item in directory.rglob("*") if item.is_file())
    ]
    combined = explicit + documentation + scripts + tests + modules + figures + results
    deduplicated: dict[Path, str] = {}
    for category, path in combined:
        deduplicated.setdefault(path.resolve(), category)
    ordered = sorted(
        ((category, path) for path, category in deduplicated.items()),
        key=lambda item: str(item[1].relative_to(root)).replace("\\", "/"),
    )
    missing = [str(path) for _, path in ordered if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing bundle inputs: {missing}")
    for _, path in ordered:
        relative = str(path.relative_to(root)).replace("\\", "/").lower()
        if relative.startswith(("data/raw/", "tmp/")):
            raise AssertionError(f"raw or temporary input must not enter bundle: {relative}")
        if relative.endswith(("measures_v2.csv", "temperature.csv")):
            raise AssertionError(f"raw third-party dataset must not enter bundle: {relative}")
    return ordered


def archive_payload(path: Path, root: Path = ROOT) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return data
    text = data.decode("utf-8")
    root_windows = str(root)
    replacements = {
        root_windows.replace("\\", "\\\\"),
        root_windows,
        root_windows.replace("\\", "/"),
    }
    for local_root in sorted(replacements, key=len, reverse=True):
        text = text.replace(local_root, ".")
    payload = text.encode("utf-8")
    lowered = payload.lower()
    if any(token in lowered for token in FORBIDDEN_BYTES):
        raise AssertionError(f"identity-bearing local path remains in {path}")
    return payload


def source_manifest(root: Path = ROOT) -> tuple[dict[str, Any], dict[str, bytes]]:
    files: list[dict[str, Any]] = []
    payloads: dict[str, bytes] = {}
    for category, path in bundle_sources(root):
        relative = str(path.relative_to(root)).replace("\\", "/")
        payload = archive_payload(path, root)
        payloads[relative] = payload
        files.append(
            {
                "path": relative,
                "category": category,
                "bytes": len(payload),
                "sha256": sha256_bytes(payload),
            }
        )
    categories: dict[str, int] = {}
    for item in files:
        category = str(item["category"])
        categories[category] = categories.get(category, 0) + 1
    manifest = {
        "bundle": "Paper 4 electrothermal transport reproducibility companion",
        "source_data_doi": "10.34740/KAGGLE/DSV/2161054",
        "external_article_doi": "10.1109/TPEL.2024.3409388",
        "external_repository_commit": "98e4566b5fb7c70499996fda18dd73179ec16509",
        "raw_third_party_data_included": False,
        "file_count": len(files),
        "categories": dict(sorted(categories.items())),
        "files": files,
    }
    return manifest, payloads


def manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def add_bytes(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(2026, 8, 21, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_bundle() -> dict[str, Any]:
    manifest, payloads = source_manifest()
    embedded = manifest_bytes(manifest)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_OUT, mode="w") as archive:
        for item in manifest["files"]:
            relative = str(item["path"])
            add_bytes(archive, f"{BUNDLE_ROOT}/{relative}", payloads[relative])
        add_bytes(archive, f"{BUNDLE_ROOT}/MANIFEST.json", embedded)
    result = {
        "status": "built",
        "path": str(ZIP_OUT.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(ZIP_OUT),
        "bytes": ZIP_OUT.stat().st_size,
        "source_manifest_sha256": sha256_bytes(embedded),
        "source_file_count": manifest["file_count"],
        "categories": manifest["categories"],
        "raw_third_party_data_included": False,
    }
    MANIFEST_OUT.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def audit_bundle() -> dict[str, Any]:
    if not ZIP_OUT.is_file() or not MANIFEST_OUT.is_file():
        raise FileNotFoundError("bundle or external manifest is missing")
    external = json.loads(MANIFEST_OUT.read_text(encoding="utf-8"))
    if external["sha256"] != sha256(ZIP_OUT):
        raise AssertionError("bundle hash does not match external manifest")
    with zipfile.ZipFile(ZIP_OUT) as archive:
        names = archive.namelist()
        manifest_name = f"{BUNDLE_ROOT}/MANIFEST.json"
        if names.count(manifest_name) != 1:
            raise AssertionError("bundle must contain exactly one embedded manifest")
        embedded = archive.read(manifest_name)
        if sha256_bytes(embedded) != external["source_manifest_sha256"]:
            raise AssertionError("embedded manifest hash mismatch")
        manifest = json.loads(embedded)
        expected_names = {manifest_name}
        for item in manifest["files"]:
            name = f"{BUNDLE_ROOT}/{item['path']}"
            expected_names.add(name)
            payload = archive.read(name)
            if len(payload) != item["bytes"] or sha256_bytes(payload) != item["sha256"]:
                raise AssertionError(f"bundle member failed integrity audit: {name}")
            if any(token in payload.lower() for token in FORBIDDEN_BYTES):
                raise AssertionError(f"local identity-bearing path in bundle member: {name}")
        if set(names) != expected_names:
            raise AssertionError("bundle inventory differs from embedded manifest")
        normalized = [name.lower().replace("\\", "/") for name in names]
        if any("/data/raw/" in name or "/tmp/" in name for name in normalized):
            raise AssertionError("bundle unexpectedly contains raw or temporary data")
        if manifest["file_count"] != external["source_file_count"]:
            raise AssertionError("bundle file count mismatch")
    return {
        "status": "pass",
        "path": str(ZIP_OUT.relative_to(ROOT)).replace("\\", "/"),
        "sha256": external["sha256"],
        "source_file_count": external["source_file_count"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = audit_bundle() if args.check else build_bundle()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
