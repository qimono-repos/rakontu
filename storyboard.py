"""Backwards-compatible entry point.

The implementation lives in the warmwind_storyboard package. Prefer the
`rakontu` command, or `python -m warmwind_storyboard`.
"""

import sys

from warmwind_storyboard.cli import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))