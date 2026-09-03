"""重定向到 CLI 入口点。

用法：
    python -m assistant   ->   委托给 python -m cli
"""

import sys
import subprocess

sys.exit(subprocess.call([sys.executable, "-m", "cli"]))
