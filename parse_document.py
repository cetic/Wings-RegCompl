#!/usr/bin/env python3
"""Run the parser CLI from a source checkout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from regcomply.cli_parse import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
