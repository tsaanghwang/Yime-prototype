from __future__ import annotations

import csv
import json
from pathlib import Path

from yime.lexicon_bundle.builder import BundleInputs, build_bundle


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
        "---\nname: test\n...\n翻页\tfān yè\t321\n新词\txīn cí\t8\n错配\tcuò\t4\n",
    )
    bcc_words = _write(
        tmp_path / "words.csv",
        "word,freq\n翻页,99\n无拼音,7\n新词,0\n",
    )
    bcc_chars = _write(tmp_path / "chars.csv", "char,freq\n中,1000\n")
    inventory = Path(__file__).resolve().parents[2] / "yime" / "pinyin_normalized.json"

    result = build_bundle(
        BundleInputs(
            unihan=unihan,
            pypinyin_phrases=phrases,
            bcc_words=bcc_words,
            bcc_chars=bcc_chars,
            wanxiang_files=(wanxiang,),
            decoder_inventory=inventory,
        ),
        tmp_path / "bundle",
    )

    rows = _rows(result.entries)
    by_key = {(row["text"], row["pinyin_marked"]): row for row in rows}
    assert by_key[("翻页", "fān yè")]["bcc_frequency"] == "99"
    assert by_key[("翻页", "fān yè")]["wanxiang_weight"] == "321"
    assert by_key[("翻页", "fān yè")]["pinyin_sources"] == "pypinyin,wanxiang"
    assert by_key[("新词", "xīn cí")]["bcc_frequency"] == "0"
    assert by_key[("中", "zhōng")]["bcc_frequency"] == "1000"
    assert "无拼音" in result.unresolved_bcc.read_text(encoding="utf-8")
    rejected = result.rejections.read_text(encoding="utf-8")
    assert "𱿅" in rejected
    assert "syllable_count_mismatch" in rejected
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "yime-gated-source-lexicon-v1"


def test_cjk_compatibility_supplement_is_not_dropped() -> None:
    from yime.lexicon_bundle.gate import is_han_text

    assert is_han_text("灰")
