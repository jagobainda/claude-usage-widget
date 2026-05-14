"""Compatibility entry point. The real code lives in `claude_widget/`."""

from __future__ import annotations

import sys

from claude_widget import main


if __name__ == "__main__":
    sys.exit(main())
