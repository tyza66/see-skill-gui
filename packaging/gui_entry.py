#!/usr/bin/env python3
"""PyInstaller entry point that can see the skill's script modules."""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "see" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gui


if __name__ == "__main__":
    raise SystemExit(gui.main())
