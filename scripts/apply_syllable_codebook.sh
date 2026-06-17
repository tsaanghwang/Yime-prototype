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

echo "Phase 2: rebuild syllable codebook and encoding assets..."
echo "Run this only after lexicon export and unittest gate are green."
echo

"$PYTHON" tools/rebuild_encoding_assets.py

"$PYTHON" -m unittest \
	tests/yinjie/test_pinyin_bidirectional_validation.py \
	tests/yinjie/test_yinjie_roundtrip.py
