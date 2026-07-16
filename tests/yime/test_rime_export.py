import json
import sqlite3
from pathlib import Path

from yime.utils.rime_export import (
    convert_runtime_code_to_layout_keys,
    export_rime_files,
    load_runtime_symbol_to_layout_key,
)


def _write_minimal_mapping_files(repo_root: Path) -> None:
    internal_data = repo_root / "internal_data"
    internal_data.mkdir()
    (internal_data / "key_to_symbol.json").write_text(
        json.dumps(
            {
                "N01": "X",
                "M01": "Y",
                "M25": "Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (internal_data / "manual_key_layout.json").write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "physical_key": "q",
                        "output_layer": "base",
                        "display_label": "q",
                        "symbol_key": "N01",
                    },
                    {
                        "physical_key": "u",
                        "output_layer": "base",
                        "display_label": "u",
                        "symbol_key": "M01",
                    },
                    {
                        "physical_key": "j",
                        "output_layer": "altgr",
                        "display_label": "AltGr+J",
                        "symbol_key": "M25",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _create_runtime_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE runtime_candidates_materialized (
                entry_type TEXT NOT NULL,
                entry_id TEXT NOT NULL,
                text TEXT NOT NULL,
                pinyin_tone TEXT NOT NULL,
                yime_code TEXT NOT NULL,
                full_yime_code TEXT NOT NULL,
                primary_yime_code TEXT NOT NULL,
                variable_yinyuan_code TEXT NOT NULL,
                input_shorthand_code TEXT NOT NULL,
                sort_weight REAL NOT NULL,
                is_common INTEGER NOT NULL,
                text_length INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            INSERT INTO runtime_candidates_materialized (
                entry_type, entry_id, text, pinyin_tone, yime_code,
                full_yime_code, primary_yime_code, variable_yinyuan_code,
                input_shorthand_code, sort_weight, is_common, text_length, updated_at
            ) VALUES
                ('char', '1', '一', 'yi1', 'WXY', 'WXY', 'XY', 'XY', 'X', 120.4, 1, 1, '2026-06-30'),
                ('phrase', '2', '一二', 'yi1 er4', 'WXYZ', 'WXYZ', 'XYZ', 'XYZ', 'XZ', 80.0, 1, 2, '2026-06-30');
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_load_runtime_symbol_to_layout_key_uses_manual_layout_and_altgr_fallback(tmp_path: Path) -> None:
    _write_minimal_mapping_files(tmp_path)

    symbol_to_key = load_runtime_symbol_to_layout_key(tmp_path)

    assert symbol_to_key["X"] == "q"
    assert symbol_to_key["Y"] == "u"
    assert symbol_to_key["Z"] == "!"
    assert convert_runtime_code_to_layout_keys("XYZ", symbol_to_key) == "qu!"


def test_export_rime_files_writes_schema_dict_and_metadata(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _write_minimal_mapping_files(repo_root)
    db_path = tmp_path / "runtime.db"
    output_dir = tmp_path / "rime"
    _create_runtime_db(db_path)

    result = export_rime_files(
        db_path=db_path,
        output_dir=output_dir,
        mode="variable",
        code_form="layout-key",
        schema_id="yime_variable_test",
        repo_root=repo_root,
    )

    assert result.row_count == 2
    assert result.code_count == 2
    dict_text = result.paths.dict_path.read_text(encoding="utf-8")
    schema_text = result.paths.schema_path.read_text(encoding="utf-8")
    metadata = json.loads(result.paths.metadata_path.read_text(encoding="utf-8"))

    assert "name: yime_variable_test" in dict_text
    assert "一\tqu\t120" in dict_text
    assert "一二\tqu!\t80" in dict_text
    assert "schema_id: yime_variable_test" in schema_text
    assert 'dictionary: yime_variable_test' in schema_text
    assert metadata["mode"] == "variable"
    assert metadata["code_form"] == "layout-key"
    assert metadata["row_count"] == 2
