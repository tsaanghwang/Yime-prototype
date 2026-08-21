# -*- mode: python ; coding: utf-8 -*-
# cSpell:words pathlib SPECPATH datas hiddenimports pathex hookspath hooksconfig noarchive

from pathlib import Path
import json

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH)
datas = collect_data_files("yime")
datas = [
    item for item in datas
    if not (
        Path(item[0]).resolve().parent == (project_root / "yime").resolve()
        and Path(item[0]).name.startswith("pinyin_hanzi.db")
    )
]
datas += collect_data_files("syllable")
datas += collect_data_files("syllable_codec")

parity_dir = project_root / ".generated" / "prototype_windows_parity"
parity_database = parity_dir / "pinyin_hanzi.db"
parity_manifest = parity_dir / "prototype_runtime_manifest.json"
if not parity_database.is_file() or not parity_manifest.is_file():
    raise SystemExit(
        "Windows-parity prototype runtime is missing; run "
        "tools/prepare_prototype_windows_parity.py first."
    )
parity_payload = json.loads(parity_manifest.read_text(encoding="utf-8"))
if parity_payload.get("status") != "passed":
    raise SystemExit("Windows-parity prototype runtime manifest did not pass.")
datas.append((str(parity_database), "yime"))
datas.append((str(parity_manifest), "yime"))

internal_data_dir = project_root / "internal_data"
if internal_data_dir.exists():
    datas.append((str(internal_data_dir), "internal_data"))

hiddenimports = collect_submodules("pynput")


a = Analysis(
    [str(project_root / "run_input_method.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Yime",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Yime",
)
