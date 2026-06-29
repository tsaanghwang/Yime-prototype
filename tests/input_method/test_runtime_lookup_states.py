from __future__ import annotations

from typing import Any, cast

from yime.input_method.core.char_code_index import CharCodeIndex
from yime.input_method.core.decoders import RuntimeCandidateDecoder
from yime.input_method.core.runtime_lookup import (
    build_phrase_tree_lookup,
    build_runtime_lookup_plan,
)
from yime.input_method.core.sqlite_char_store import SQLiteCharCandidateStore
from yime.input_method.core.sqlite_phrase_store import SQLitePhraseCandidateStore
from yime.input_method.core.sqlite_runtime_source import SQLiteRuntimeSource


def _build_runtime_decoder() -> RuntimeCandidateDecoder:
    runtime_decoder = RuntimeCandidateDecoder.__new__(RuntimeCandidateDecoder)
    runtime_decoder.bmp_to_canonical = {}
    runtime_decoder.numeric_to_marked_pinyin = {}
    cast(Any, runtime_decoder)._user_freq_by_candidate = {}
    cast(Any, runtime_decoder)._local_phrase_priority_rules = {}
    cast(Any, runtime_decoder)._continuous_input_priority_rules = {}
    by_code: dict[str, list[dict[str, Any]]] = {}
    runtime_decoder.by_code = by_code
    cast(Any, runtime_decoder)._char_sort_weight_by_text = {}
    cast(Any, runtime_decoder)._phrase_prefix_index = {}
    runtime_decoder.char_code_index = CharCodeIndex.from_runtime_candidates(by_code)
    return runtime_decoder


def test_build_runtime_lookup_plan_marks_continuous_input_states() -> None:
    plan_a = build_runtime_lookup_plan("abc")
    assert plan_a.stage == "A"
    assert plan_a.phrase_prefix_pool == ""
    assert plan_a.phrase_prefix_limit == 0

    plan_b = build_runtime_lookup_plan("abcd")
    assert plan_b.stage == "B"
    assert plan_b.phrase_prefix_pool == "recent-syllable-prefix"
    assert plan_b.phrase_prefix_limit == 64

    plan_c = build_runtime_lookup_plan("abcdxy")
    assert plan_c.stage == "C"
    assert plan_c.lookup_code == "abcd"
    assert plan_c.context_code == "abcdxy"
    assert plan_c.phrase_prefix_pool == "long-context-prefix-1"
    assert plan_c.phrase_prefix_limit == 32

    plan_c2 = build_runtime_lookup_plan("abcdefghxy")
    assert plan_c2.stage == "C"
    assert plan_c2.lookup_code == "efgh"
    assert plan_c2.context_code == "abcdefghxy"
    assert plan_c2.phrase_prefix_pool == "long-context-prefix-2"
    assert plan_c2.phrase_prefix_limit == 24

    plan_c3 = build_runtime_lookup_plan("abcdefghijklxy")
    assert plan_c3.stage == "C"
    assert plan_c3.lookup_code == "ijkl"
    assert plan_c3.context_code == "abcdefghijklxy"
    assert plan_c3.phrase_prefix_pool == "long-context-prefix-3"
    assert plan_c3.phrase_prefix_limit == 16

    plan_d = build_runtime_lookup_plan("abcdefgh")
    assert plan_d.stage == "D"
    assert plan_d.lookup_code == "abcdefgh"
    assert plan_d.phrase_prefix_pool == ""
    assert plan_d.phrase_prefix_limit == 0


def test_build_runtime_lookup_plan_supports_variable_length_primary_syllables() -> None:
    inventory = frozenset({"ab", "cde", "fg"})

    plan_a = build_runtime_lookup_plan("a", inventory)
    assert plan_a.stage == "A"
    assert plan_a.trailing_code_count == 1

    plan_c = build_runtime_lookup_plan("abx", inventory)
    assert plan_c.stage == "C"
    assert plan_c.lookup_code == "ab"
    assert plan_c.context_code == "abx"
    assert plan_c.trailing_code_count == 1

    plan_d = build_runtime_lookup_plan("abcde", inventory)
    assert plan_d.stage == "D"
    assert plan_d.lookup_code == "abcde"
    assert plan_d.syllable_count == 2


def test_phrase_tree_lookup_uses_variable_length_inventory_boundaries() -> None:
    inventory = frozenset({"ab", "cde", "fg"})

    plan_c = build_runtime_lookup_plan("abx", inventory)
    assert build_phrase_tree_lookup("abx", plan_c, inventory) == "abx"

    plan_d = build_runtime_lookup_plan("abcde", inventory)
    assert build_phrase_tree_lookup("abcde", plan_d, inventory) == ""


def test_continuous_input_prefers_context_prefix_before_single_syllable_bucket() -> None:
    runtime_decoder = _build_runtime_decoder()
    by_code: dict[str, list[dict[str, Any]]] = {
        "abcd": [
            {
                "text": "你",
                "entry_type": "char",
                "pinyin_tone": "ni3",
                "yime_code": "abcd",
                "sort_weight": 999.0,
                "text_length": 1,
                "is_common": 1,
            }
        ]
    }
    runtime_decoder.by_code = by_code
    cast(Any, runtime_decoder)._phrase_prefix_index = {
        "abcdxy": [
            {
                "text": "你好啊",
                "entry_type": "phrase",
                "pinyin_tone": "ni3 hao3 a5",
                "yime_code": "abcdxywv",
                "sort_weight": 280.0,
                "text_length": 3,
                "is_common": 1,
            }
        ]
    }
    runtime_decoder.char_code_index = CharCodeIndex.from_runtime_candidates(by_code)

    _canonical, _active, _pinyin, candidates, _status = runtime_decoder.decode_text("abcdxy")

    assert candidates == ["你好啊"]


def test_runtime_decoder_uses_variable_length_context_prefix_lookup() -> None:
    runtime_decoder = _build_runtime_decoder()
    runtime_decoder.single_syllable_codes = frozenset({"ab", "cde", "fg"})
    runtime_decoder.by_code = {
        "ab": [
            {
                "text": "甲",
                "entry_type": "char",
                "pinyin_tone": "jia3",
                "yime_code": "ab",
                "sort_weight": 900.0,
                "text_length": 1,
                "is_common": 1,
            }
        ]
    }
    cast(Any, runtime_decoder)._phrase_prefix_index = {
        "abx": [
            {
                "text": "甲乙",
                "entry_type": "phrase",
                "pinyin_tone": "jia3 yi3",
                "yime_code": "abxy",
                "sort_weight": 1000.0,
                "text_length": 2,
                "is_common": 1,
            }
        ]
    }
    runtime_decoder.char_code_index = CharCodeIndex.from_runtime_candidates(
        runtime_decoder.by_code
    )

    _canonical, active, _pinyin, candidates, status = runtime_decoder.decode_text("abx")

    assert active == "ab"
    assert candidates == ["甲乙"]
    assert "当前第 2 个音节未完成" in status


def test_sqlite_stores_query_materialized_primary_yime_code(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE runtime_candidates_materialized (
                entry_type TEXT NOT NULL,
                entry_id TEXT NOT NULL,
                text TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                primary_yime_code TEXT NOT NULL,
                sort_weight REAL NOT NULL,
                is_common INTEGER NOT NULL,
                text_length INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entry_type, entry_id)
            );
            CREATE TABLE char_lexicon (
                hanzi TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                usage_tier TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO runtime_candidates_materialized
            VALUES ('phrase', 'p1', '发展', 'fa1 zhan3', 'FULLPHRASE', 'ab', 1000.0, 1, 2, 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO runtime_candidates_materialized
            VALUES ('char', 'c1', '发', 'fa1', 'FULLCHAR', 'xy', 900.0, 1, 1, 'now')
            """
        )
        conn.execute(
            "INSERT INTO char_lexicon VALUES ('发', 'fa1', 'FULLCHAR', 'common_high')"
        )

    runtime_source = SQLiteRuntimeSource(db_path)
    phrase_store = SQLitePhraseCandidateStore(
        runtime_source,
        "runtime_candidates_materialized",
    )
    char_store = SQLiteCharCandidateStore(
        runtime_source,
        "runtime_candidates_materialized",
    )

    exact_phrases = phrase_store.load_runtime_candidates_for_code("ab", {})
    assert [candidate["text"] for candidate in exact_phrases] == ["发展"]

    prefix_phrases = phrase_store.load_phrase_prefix_candidates("a", {}, limit=10)
    assert [candidate["text"] for candidate in prefix_phrases] == ["发展"]

    exact_chars = char_store.get_char_candidates("xy")
    assert [candidate.text for candidate in exact_chars] == ["发"]
    assert exact_chars[0].code == "xy"

    prefix_chars = char_store.get_char_candidates_by_prefix("x", limit=10)
    assert [(code, [candidate.text for candidate in candidates]) for code, candidates in prefix_chars] == [
        ("xy", ["发"])
    ]


def test_sqlite_stores_fall_back_when_materialized_primary_yime_code_is_missing(tmp_path) -> None:
    db_path = tmp_path / "runtime_old.db"
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE runtime_candidates_materialized (
                entry_type TEXT NOT NULL,
                entry_id TEXT NOT NULL,
                text TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                sort_weight REAL NOT NULL,
                is_common INTEGER NOT NULL,
                text_length INTEGER NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (entry_type, entry_id)
            );
            CREATE TABLE char_lexicon (
                hanzi TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                usage_tier TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO runtime_candidates_materialized
            VALUES ('phrase', 'p1', '发展', 'fa1 zhan3', 'FULLPHRASE', 1000.0, 1, 2, 'now')
            """
        )
        conn.execute(
            """
            INSERT INTO runtime_candidates_materialized
            VALUES ('char', 'c1', '发', 'fa1', 'FULLCHAR', 900.0, 1, 1, 'now')
            """
        )
        conn.execute(
            "INSERT INTO char_lexicon VALUES ('发', 'fa1', 'FULLCHAR', 'common_high')"
        )

    runtime_source = SQLiteRuntimeSource(db_path)
    phrase_store = SQLitePhraseCandidateStore(
        runtime_source,
        "runtime_candidates_materialized",
    )
    char_store = SQLiteCharCandidateStore(
        runtime_source,
        "runtime_candidates_materialized",
    )

    exact_phrases = phrase_store.load_runtime_candidates_for_code("FULLPHRASE", {})
    assert [candidate["text"] for candidate in exact_phrases] == ["发展"]

    exact_chars = char_store.get_char_candidates("FULLCHAR")
    assert [candidate.text for candidate in exact_chars] == ["发"]
    assert exact_chars[0].code == "FULLCHAR"


def test_phrase_prefix_pool_limits_differ_between_recent_and_long_context() -> None:
    runtime_decoder = _build_runtime_decoder()
    cast(Any, runtime_decoder)._phrase_prefix_index = {
        "abcd": [
            {
                "text": f"词{index:02d}",
                "entry_type": "phrase",
                "pinyin_tone": f"ci2 {index}",
                "yime_code": f"abcd{index:04d}",
                "sort_weight": float(1000 - index),
                "text_length": 2,
                "is_common": 1,
            }
            for index in range(70)
        ],
        "abcdxy": [
            {
                "text": f"长词{index:02d}",
                "entry_type": "phrase",
                "pinyin_tone": f"chang2 ci2 {index}",
                "yime_code": f"abcdxy{index:04d}",
                "sort_weight": float(1000 - index),
                "text_length": 3,
                "is_common": 1,
            }
            for index in range(40)
        ],
        "abcdefghxy": [
            {
                "text": f"中长词{index:02d}",
                "entry_type": "phrase",
                "pinyin_tone": f"zhong1 chang2 ci2 {index}",
                "yime_code": f"abcdefghxy{index:04d}",
                "sort_weight": float(1000 - index),
                "text_length": 3,
                "is_common": 1,
            }
            for index in range(40)
        ],
        "abcdefghijklxy": [
            {
                "text": f"超长词{index:02d}",
                "entry_type": "phrase",
                "pinyin_tone": f"chao1 chang2 ci2 {index}",
                "yime_code": f"abcdefghijklxy{index:04d}",
                "sort_weight": float(1000 - index),
                "text_length": 4,
                "is_common": 1,
            }
            for index in range(40)
        ],
    }

    _canonical_b, _active_b, _pinyin_b, candidates_b, _status_b = runtime_decoder.decode_text("abcd")
    _canonical_c1, _active_c1, _pinyin_c1, candidates_c1, _status_c1 = runtime_decoder.decode_text("abcdxy")
    _canonical_c2, _active_c2, _pinyin_c2, candidates_c2, _status_c2 = runtime_decoder.decode_text("abcdefghxy")
    _canonical_c3, _active_c3, _pinyin_c3, candidates_c3, _status_c3 = runtime_decoder.decode_text("abcdefghijklxy")

    assert len(candidates_b) == 64
    assert candidates_b[0] == "词00"
    assert candidates_b[-1] == "词63"
    assert len(candidates_c1) == 32
    assert candidates_c1[0] == "长词00"
    assert candidates_c1[-1] == "长词31"
    assert len(candidates_c2) == 24
    assert candidates_c2[0] == "中长词00"
    assert candidates_c2[-1] == "中长词23"
    assert len(candidates_c3) == 16
    assert candidates_c3[0] == "超长词00"
    assert candidates_c3[-1] == "超长词15"


def test_stage_b_keeps_a_rare_char_representative_on_second_page_for_dense_exact_bucket() -> None:
    runtime_decoder = _build_runtime_decoder()
    cast(Any, runtime_decoder)._phrase_prefix_index = {
        "abcd": [
            {
                "text": f"词{index:02d}",
                "entry_type": "phrase",
                "pinyin_tone": f"ci2 {index}",
                "yime_code": f"abcd{index:04d}",
                "sort_weight": float(1000 - index),
                "text_length": 2,
                "is_common": 1,
            }
            for index in range(5)
        ]
    }
    by_code: dict[str, list[dict[str, Any]]] = {
        "abcd": [
            {
                "text": chr(0x4E00 + index),
                "entry_type": "char",
                "pinyin_tone": f"zi4 {index}",
                "yime_code": "abcd",
                "sort_weight": float(500 - index),
                "text_length": 1,
                "is_common": 1,
                "usage_tier": "common_high",
            }
            for index in range(70)
        ]
        + [
            {
                "text": "龘",
                "entry_type": "char",
                "pinyin_tone": "da2",
                "yime_code": "abcd",
                "sort_weight": 1.0,
                "text_length": 1,
                "is_common": 0,
                "usage_tier": "rare",
            }
        ]
    }
    runtime_decoder.by_code = by_code
    runtime_decoder.char_code_index = CharCodeIndex.from_runtime_candidates(
        by_code
    )

    _canonical, _active, _pinyin, candidates, _status = runtime_decoder.decode_text("abcd")

    assert candidates[:5] == ["词00", "词01", "词02", "词03", "词04"]
    assert candidates[6] == "龘"
