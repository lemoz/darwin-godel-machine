#!/usr/bin/env python3
"""Generate the read-only local WebUI status page."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webui.status_page import main


if __name__ == "__main__":
    raise SystemExit(main())
