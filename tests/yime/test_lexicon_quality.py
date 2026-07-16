from __future__ import annotations

from yime.utils.lexicon_quality import (
    finalize_report,
    lint_runtime_json_payload,
    make_report,
    ends_with_particle,
    is_placeholder_phrase,
    is_whitelisted_phrase,
)


def test_suffix_particle_detects_non_whitelisted_phrase() -> None:
    assert ends_with_particle("走了吗")
    assert not is_whitelisted_phrase("走了吗")


def test_suffix_particle_whitelist_skips_common_phrase() -> None:
    assert ends_with_particle("你的")
    assert is_whitelisted_phrase("你的")


def test_placeholder_phrase_detection() -> None:
    assert is_placeholder_phrase("phrase", "zhong1 guo2", "zhong1 guo2")
    assert not is_placeholder_phrase("phrase", "abc", "zhong1 guo2")
    assert not is_placeholder_phrase("char", "zhong1", "zhong1")


def test_lint_runtime_json_flags_suffix_and_placeholder() -> None:
    report = make_report(sample_limit=10, inputs={"runtime_json": "memory"})
    payload = {
        "by_code": {
            "code-a": [
                {
                    "text": "走了吗",
                    "entry_type": "phrase",
                    "entry_id": "1",
                    "pinyin_tone": "zou3 le5 ma5",
                    "yime_code": "code-a",
                    "sort_weight": 10.0,
                    "is_common": 1,
                    "text_length": 3,
                    "updated_at": "2026-01-01 00:00:00",
                }
            ],
            "zhong1 guo2": [
                {
                    "text": "中国",
                    "entry_type": "phrase",
                    "entry_id": "2",
                    "pinyin_tone": "zhong1 guo2",
                    "yime_code": "zhong1 guo2",
                    "sort_weight": 100.0,
                    "is_common": 1,
                    "text_length": 2,
                    "updated_at": "2026-01-01 00:00:00",
                }
            ],
        }
    }
    lint_runtime_json_payload(payload, report, source_label="memory")
    finalized = finalize_report(report)

    assert finalized["summary"]["candidate_rows"] == 2
    assert finalized["summary"]["suffix_particle_count"] == 1
    assert finalized["summary"]["placeholder_phrase_count"] == 1
    assert "suffix_particle" in finalized["warnings"]
    assert "placeholder_phrase_code" in finalized["warnings"]


def test_lint_runtime_json_reports_code_key_mismatch_as_error() -> None:
    report = make_report(sample_limit=5, inputs={})
    payload = {
        "by_code": {
            "expected-code": [
                {
                    "text": "测试",
                    "entry_type": "phrase",
                    "entry_id": "9",
                    "pinyin_tone": "ce4 shi4",
                    "yime_code": "other-code",
                    "sort_weight": 3.0,
                    "is_common": 0,
                    "text_length": 2,
                    "updated_at": "2026-01-01 00:00:00",
                }
            ]
        }
    }
    lint_runtime_json_payload(payload, report, source_label="memory")
    finalized = finalize_report(report)
    assert finalized["summary"]["error_count"] == 1
    assert "json_code_key_mismatch" in finalized["errors"]
