from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from yime.lexicon_bundle.builder import BundleInputs, CategorizedPath, build_bundle
from yime.utils.prototype_phrase_import import import_bundle_phrases_and_mappings


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_build_bundle_keeps_frequency_semantics_and_reports_gates(tmp_path: Path) -> None:
    unihan = _write(
        tmp_path / "unihan.tsv",
        "codepoint\thanzi\tcommon_reading\treadings\tcommon_reading_source\tis_single\n"
        "U+4E2D\t中\tzhōng\tzhōng,zhòng\tkMandarin\t0\n"
        "U+31FC5\t𱿅\tbòng\tbòng\tkMandarin\t1\n",
    )
    phrases = _write(
        tmp_path / "phrases.tsv",
        "phrase\tphrase_len\tcommon_reading\treadings\n"
        "翻页\t2\tfān yè\tfān yè\n",
    )
    wanxiang = _write(
        tmp_path / "jichu.dict.yaml",
        "---\nname: test\n...\n翻页\tfān yè\t321\n新词\txīn cí\t8\n爱词\taì cí\t6\n错配\tcuò\t4\n",
    )
    bcc_modern_words = _write(
        tmp_path / "modern_words.csv",
        "word,freq\n翻页,99\n无拼音,7\n新词,0\n",
    )
    bcc_classical_words = _write(
        tmp_path / "classical_words.csv",
        "word,freq\n翻页,120\n古词,8\n",
    )
    bcc_chars = _write(tmp_path / "modern_chars.csv", "char,freq\n中,1000\n")
    inventory = Path(__file__).resolve().parents[2] / "yime" / "pinyin_normalized.json"

    result = build_bundle(
        BundleInputs(
            unihan=unihan,
            pypinyin_phrases=phrases,
            bcc_word_files=(
                CategorizedPath("modern_chinese", "word", bcc_modern_words),
                CategorizedPath("classical_chinese", "word", bcc_classical_words),
            ),
            bcc_char_files=(CategorizedPath("modern_chinese", "char", bcc_chars),),
            wanxiang_files=(wanxiang,),
            decoder_inventory=inventory,
        ),
        tmp_path / "bundle",
    )

    rows = _rows(result.entries)
    by_key = {(row["text"], row["pinyin_marked"]): row for row in rows}
    assert by_key[("翻页", "fān yè")]["bcc_frequency"] == "120"
    assert by_key[("翻页", "fān yè")]["bcc_modern_chinese"] == "99"
    assert by_key[("翻页", "fān yè")]["bcc_classical_chinese"] == "120"
    assert by_key[("翻页", "fān yè")]["bcc_categories"] == "modern_chinese,classical_chinese"
    assert by_key[("翻页", "fān yè")]["wanxiang_weight"] == "321"
    assert by_key[("翻页", "fān yè")]["wanxiang_categories"] == "jichu"
    assert by_key[("翻页", "fān yè")]["pinyin_sources"] == "pypinyin,wanxiang"
    assert by_key[("新词", "xīn cí")]["bcc_frequency"] == "0"
    assert by_key[("中", "zhōng")]["bcc_frequency"] == "1000"
    assert by_key[("爱词", "ài cí")]["pinyin_numeric"] == "ai4 ci2"
    assert "无拼音" in result.unresolved_bcc.read_text(encoding="utf-8")
    rejected = result.rejections.read_text(encoding="utf-8")
    assert "𱿅" in rejected
    assert "syllable_count_mismatch" in rejected
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "yime-gated-source-lexicon-v1"
    with sqlite3.connect(result.database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM char_readings").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM phrase_readings").fetchone()[0] == 3
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'source_role'"
        ).fetchone()[0] == "canonical_lexicon_and_encoding_source"
        assert connection.execute(
            "SELECT source_marked FROM accepted_readings WHERE text = '爱词'"
        ).fetchone()[0] == "aì cí"

    runtime_db = tmp_path / "runtime.sqlite3"
    schema = (
        Path(__file__).resolve().parents[2]
        / "yime"
        / "create_prototype_schema_additions.sql"
    ).read_text(encoding="utf-8")
    with sqlite3.connect(runtime_db) as connection:
        connection.executescript(schema)
        phrase_count, mapping_count, _ = import_bundle_phrases_and_mappings(
            connection,
            result.database,
            batch_size=2,
        )
        assert phrase_count == 3
        assert mapping_count == 3
        assert connection.execute(
            "SELECT phrase_frequency FROM phrase_inventory WHERE phrase = '翻页'"
        ).fetchone()[0] == 120


def test_cjk_compatibility_supplement_is_not_dropped() -> None:
    from yime.lexicon_bundle.gate import is_han_text

    assert is_han_text("灰")


def test_generated_bcc_files_cannot_be_used_as_source_evidence(tmp_path: Path) -> None:
    generated = _write(tmp_path / "merged_word_freq.txt", "word,freq\n测试,1\n")
    inventory = Path(__file__).resolve().parents[2] / "yime" / "pinyin_normalized.json"
    empty_unihan = _write(
        tmp_path / "unihan.tsv",
        "codepoint\thanzi\tcommon_reading\treadings\tcommon_reading_source\tis_single\n",
    )
    empty_phrases = _write(
        tmp_path / "phrases.tsv",
        "phrase\tphrase_len\tcommon_reading\treadings\n",
    )
    empty_wanxiang = _write(tmp_path / "zi.dict.yaml", "---\nname: empty\n...\n")

    import pytest

    with pytest.raises(ValueError, match="secondary BCC"):
        build_bundle(
            BundleInputs(
                unihan=empty_unihan,
                pypinyin_phrases=empty_phrases,
                bcc_word_files=(CategorizedPath("modern_chinese", "word", generated),),
                bcc_char_files=(),
                wanxiang_files=(empty_wanxiang,),
                decoder_inventory=inventory,
            ),
            tmp_path / "bundle",
        )
