#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."

if [[ -x "venv312/Scripts/python.exe" ]]; then
	PYTHON="venv312/Scripts/python.exe"
elif [[ -x ".venv/Scripts/python.exe" ]]; then
	PYTHON=".venv/Scripts/python.exe"
else
	PYTHON="python"
fi

echo "Using Python: $PYTHON"
echo "Rebuilding source pinyin assets..."

"$PYTHON" internal_data/pinyin_source_db/rebuild_pinyin_assets.py

echo "Running focused validation suite..."

"$PYTHON" tools/validate_yinyuan_source_consistency.py

"$PYTHON" -m unittest \
	tests/yinjie/test_yinjie_encoder.py \
	tests/yinjie/test_yinjie_decoder.py \
	tests/yinjie/test_pinyin_bidirectional_validation.py \
	tests/yinjie/test_yinjie_roundtrip.py \
	tests/yinjie/test_yinjie_encoder_stages.py \
	tests/yinjie/test_yinjie_entry_manifests.py \
	tests/syllable_analysis/test_encode_ganyin.py \
	tests/pinyin_source_db/test_marked_syllable_to_numeric.py \
	tests/pinyin_source_db/test_export_pinyin_normalized_inventory.py \
	tests/yime/test_char_frequency_policy.py \
	tests/yime/test_blcu_word_frequency_import.py \
	tests/yime/test_unihan_readings_frequency.py \
	tests/test_pinyin_normalizer.py

"$PYTHON" -m pytest \
	tests/test_asset_paths.py \
	tests/input_method/ \
	-q --tb=short
