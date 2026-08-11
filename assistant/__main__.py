"""Redirect to the CLI entry point.

Usage:
    python -m assistant   ->   delegates to python -m cli
"""

import sys
import subprocess

sys.exit(subprocess.call([sys.executable, "-m", "cli"]))

