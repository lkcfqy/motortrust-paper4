from __future__ import annotations

from scripts.build_paper4_reproducibility_bundle import (
    ZIP_OUT,
    audit_bundle,
    bundle_sources,
    source_manifest,
)


def test_paper4_bundle_sources_exclude_raw_data() -> None:
    sources = bundle_sources()
    relatives = [str(path).lower().replace("\\", "/") for _, path in sources]
    assert not any("/data/raw/" in path for path in relatives)
    assert any(path.endswith("paper4_manuscript_anonymous.pdf") for path in relatives)
    assert any(path.endswith("trajectory_predictions.csv.gz") for path in relatives)


def test_paper4_source_manifest_is_complete() -> None:
    manifest, payloads = source_manifest()
    assert manifest["raw_third_party_data_included"] is False
    assert manifest["file_count"] == len(payloads)
    assert manifest["file_count"] >= 45


def test_generated_paper4_bundle_audits_when_present() -> None:
    if ZIP_OUT.is_file():
        result = audit_bundle()
        assert result["status"] == "pass"
