"""
内置工具 - 导入时自动注册。
注意：call_skill 不会在此自动导入，因为它需要在注册前
通过 call_skill.configure() 配置 LLM。
"""

from . import weather  # noqa: F401
from . import calculator  # noqa: F401
from . import time_tool  # noqa: F401
from . import read_file  # noqa: F401
from . import edit_file  # noqa: F401
from . import write_file  # noqa: F401
from . import bash_tool  # noqa: F401
