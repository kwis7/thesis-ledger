#!/usr/bin/env python3
"""Run from a checkout without installing a package or downloading dependencies."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from thesisledger.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
