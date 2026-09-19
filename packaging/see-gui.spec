# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(os.environ.get("SEE_GUI_ROOT", "")).resolve() or Path(SPECPATH).resolve().parent.parent
SCRIPT_DIR = ROOT / "see" / "scripts"


def collect_skill_data():
    """Bundle the whole skill so the GUI can install it globally."""
    source = ROOT / "see"
    entries = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        parts = path.relative_to(source).parts
        if any(part in {"node_modules", "__pycache__", ".git"} for part in parts):
            continue
        destination = Path("see") / Path(*parts[:-1]) if parts[:-1] else Path("see")
        entries.append((str(path), str(destination)))
    marker = os.environ.get("SEE_GUI_MARKER", "")
    if marker and Path(marker).is_file():
        entries.append((marker, "see"))
    return entries


datas = [
    (str(SCRIPT_DIR / "ocr_macos.js"), "."),
    (str(SCRIPT_DIR / "ocr_macos.swift"), "."),
    (str(SCRIPT_DIR / "ocr_windows.ps1"), "."),
    *collect_skill_data(),
]
binaries = []
try:
    keyring_datas, keyring_binaries, keyring_hidden = collect_all("keyring")
except Exception:
    keyring_datas, keyring_binaries, keyring_hidden = [], [], []
datas += keyring_datas
binaries += keyring_binaries
hiddenimports = [
    "onboard",
    "parse_media",
    "secure_credentials",
    *collect_submodules("keyring"),
    *keyring_hidden,
]

a = Analysis(
    [str(ROOT / "packaging" / "gui_entry.py")],
    pathex=[str(SCRIPT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SeeGui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="SeeGui.app",
        icon=None,
        bundle_identifier="org.oiloil.see-gui",
    )
