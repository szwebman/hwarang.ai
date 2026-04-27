"""`python -m agent` 진입점 — cli.main 으로 위임."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
