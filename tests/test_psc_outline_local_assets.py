from pathlib import Path

from tools.audit_orthoepy_coverage import DEFAULT_PSC_DB
from tools.audit_psc_pronunciation_source import default_psc_database


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PSC_DB = (
    ROOT / "external_data" / "psc_outline" / "psc_outline_ocr.sqlite3"
)


def test_psc_audit_defaults_use_in_repository_evidence_bundle(monkeypatch) -> None:
    monkeypatch.delenv("PSC_OUTLINE_DB", raising=False)

    assert default_psc_database() == EXPECTED_PSC_DB
    assert DEFAULT_PSC_DB == EXPECTED_PSC_DB


def test_psc_audit_environment_override_is_still_supported(
    monkeypatch, tmp_path: Path
) -> None:
    override = tmp_path / "psc.sqlite3"
    monkeypatch.setenv("PSC_OUTLINE_DB", str(override))

    assert default_psc_database() == override
