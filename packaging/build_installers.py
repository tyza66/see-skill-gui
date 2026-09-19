#!/usr/bin/env python3
"""Build the SeeGui desktop app and a platform installer from CI."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
INSTALLERS = DIST / "installers"
BUILD = ROOT / "build"


def run(command: list[str], **kwargs: object) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def version() -> str:
    env_version = os.getenv("SEE_VERSION", "").strip()
    if env_version:
        return env_version.lstrip("v")
    try:
        tagged = subprocess.check_output(
            ["git", "describe", "--tags", "--always"],
            cwd=ROOT,
            text=True,
        ).strip().lstrip("v")
        return tagged or "1.0.20260918"
    except Exception:
        return "1.0.20260918"


def build_pyinstaller() -> None:
    ver = version()
    env = dict(os.environ)
    env["SEE_GUI_ROOT"] = str(ROOT)
    env["SEE_GUI_VERSION"] = ver
    marker = BUILD / f"see-skill-{ver}" / ".see-gui-version"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(ver, encoding="utf-8")
    env["SEE_GUI_MARKER"] = str(marker)
    run([
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(ROOT / "packaging" / "see-gui.spec"),
    ], env=env)


def build_nsis(ver: str) -> None:
    binary = DIST / "SeeGui.exe"
    if not binary.is_file():
        raise RuntimeError(f"PyInstaller output not found: {binary}")
    makensis = shutil.which("makensis")
    if not makensis and platform.system() == "Windows":
        candidates = [
            Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
            Path(r"C:\Program Files\NSIS\makensis.exe"),
        ]
        makensis = str(next((path for path in candidates if path.is_file()), "")) or ""
    if not makensis:
        raise RuntimeError("makensis not found; install NSIS before building the installer")
    run([
        makensis,
        f"/DVERSION={ver}",
        str(ROOT / "packaging" / "see-gui.nsi"),
    ], cwd=ROOT / "packaging")
    installer = DIST / f"SeeGui-{ver}-windows-x64-setup.exe"
    INSTALLERS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(installer, INSTALLERS / "SeeGui.exe")


def build_dmg(ver: str) -> None:
    app = DIST / "SeeGui.app"
    if not app.is_dir():
        raise RuntimeError(f"PyInstaller app bundle not found: {app}")
    arch = subprocess.check_output(["uname", "-m"], text=True).strip()
    dmg = DIST / f"SeeGui-{ver}-macos-{arch}.dmg"
    if dmg.exists():
        dmg.unlink()
    run([
        "hdiutil",
        "create",
        "-volname",
        "SeeGui",
        "-srcfolder",
        str(app),
        "-ov",
        "-format",
        "UDZO",
        str(dmg),
    ])
    INSTALLERS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dmg, INSTALLERS / "SeeGui.dmg")


def build_appimage(ver: str) -> None:
    binary = DIST / "SeeGui"
    if not binary.is_file():
        raise RuntimeError(f"PyInstaller output not found: {binary}")

    appdir = BUILD / "SeeGui.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    usr_bin = appdir / "usr" / "bin"
    icons = appdir / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
    apps = appdir / "usr" / "share" / "applications"
    usr_bin.mkdir(parents=True)
    icons.mkdir(parents=True)
    apps.mkdir(parents=True)
    shutil.copy2(binary, usr_bin / "SeeGui")
    shutil.copy2(
        ROOT / "assets" / "readme" / "hero.svg",
        icons / "SeeGui.svg",
    )
    shutil.copy2(icons / "SeeGui.svg", appdir / "SeeGui.svg")
    (apps / "SeeGui.desktop").write_text(
        "\n".join([
            "[Desktop Entry]",
            "Name=SeeGui",
            "Comment=See skill configuration and installation",
            "Exec=SeeGui",
            "Icon=SeeGui",
            "Terminal=false",
            "Type=Application",
            "Categories=Utility;",
            "",
        ]),
        encoding="utf-8",
    )
    shutil.copy2(apps / "SeeGui.desktop", appdir / "SeeGui.desktop")
    (appdir / "AppRun").write_text(
        "#!/bin/sh\n"
        'exec "$(dirname "$0")/usr/bin/SeeGui" "$@"\n',
        encoding="utf-8",
    )
    (appdir / "AppRun").chmod(0o755)

    tool = BUILD / "appimagetool-x86_64.AppImage"
    if not tool.is_file():
        run([
            "curl",
            "-L",
            "-o",
            str(tool),
            "https://github.com/AppImage/AppImageKit/releases/download/continuous/"
            "appimagetool-x86_64.AppImage",
        ])
        tool.chmod(0o755)
    for entry in sorted(appdir.rglob("*.desktop")):
        print(f"AppDir desktop file: {entry}", flush=True)
    output = DIST / f"SeeGui-{ver}-linux-x86_64.AppImage"
    run([
        str(tool),
        "--appimage-extract-and-run",
        str(appdir),
        str(output),
    ])
    INSTALLERS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, INSTALLERS / "SeeGui.AppImage")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build SeeGui installers.")
    parser.add_argument(
        "--installer",
        choices=["nsis", "dmg", "appimage"],
        default={
            "Windows": "nsis",
            "Darwin": "dmg",
            "Linux": "appimage",
        }.get(platform.system(), ""),
    )
    args = parser.parse_args()
    if not args.installer:
        parser.error("unsupported platform; pass --installer explicitly")

    ver = version()
    build_pyinstaller()
    if args.installer == "nsis":
        build_nsis(ver)
    elif args.installer == "dmg":
        build_dmg(ver)
    else:
        build_appimage(ver)
    print(f"SeeGui {ver} build complete in {DIST}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
