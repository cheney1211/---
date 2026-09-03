"""
工作区工具模块 — 路径校验与平台信息。

为所有文件操作工具提供统一的工作区目录限制。

工作区根目录的解析优先级：
1. data/workspace.json（通过 Web UI 持久化）
2. WORKSPACE_ROOT 环境变量
3. 项目根目录（兜底）
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import platform
from pathlib import Path
from typing import Optional

# 项目根目录：从此文件向上两级（assistant/tools/workspace.py -> 项目根）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_FILE = _PROJECT_ROOT / "data" / "workspace.json"
_WORKSPACE_ROOT = _PROJECT_ROOT / "workSpace"

# 每次请求的项目上下文：由 chat_service 在工具执行前设置，对并发 async 任务安全
_current_project_workspace: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "_current_project_workspace", default=None,
)


def get_project_workspace(project_id: str) -> Path:
    """返回指定项目的工作区目录。

    路径规则：<project_root>/workSpace/<project_id>/
    """
    return (_WORKSPACE_ROOT / project_id).resolve()


def ensure_project_dir(project_id: str) -> Path:
    """确保项目工作区目录存在并返回该路径。"""
    p = get_project_workspace(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextlib.contextmanager
def project_context(project_id: str | None, root_path: str | None = None):
    """设置工具执行时的活跃项目工作区的上下文管理器。

    若提供了 *root_path*（用户在数据库中设置的实际项目目录），
    则优先使用该路径，而非内部的 ``workSpace/<project_id>/`` 目录。

    使用 ``contextvars.ContextVar`` 确保并发 async 请求各自看到
    自己的工作区，互不干扰。
    """
    if project_id and root_path:
        value: Optional[Path] = Path(root_path).resolve()
    elif project_id:
        value = get_project_workspace(project_id)
    else:
        value = None
    token = _current_project_workspace.set(value)
    try:
        yield
    finally:
        _current_project_workspace.reset(token)


def get_workspace_root() -> Path:
    """返回工作区根目录。

    若有活跃的项目上下文，返回项目工作区；
    否则返回默认的 workSpace 目录。
    """
    # 1. 活跃项目上下文（由 chat_service 每次请求设置）
    ws = _current_project_workspace.get()
    if ws is not None:
        return ws

    # 2. 默认：项目根目录下的 workSpace 目录
    _WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    return _WORKSPACE_ROOT


def set_workspace_root(path: str) -> Path:
    """将工作区根目录持久化到 data/workspace.json。

    返回解析后的 Path。
    若路径不存在或不是目录，抛出 ValueError。
    """
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise ValueError(f"路径不存在: {path}")
    if not resolved.is_dir():
        raise ValueError(f"路径不是目录: {path}")

    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(
        json.dumps({"workspace_root": str(resolved)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return resolved


def _is_under_root(path: Path, root: Path) -> bool:
    """检查 *path* 是否严格在 *root* 目录下（组件级比较）。

    使用 ``os.path.commonpath`` 替代 ``PurePath.relative_to``，避免
    前缀歧义问题（如 ``/a/bc`` 与 ``/a/b``）。
    两个参数必须是已解析的绝对路径。
    """
    try:
        common = Path(os.path.commonpath([str(path), str(root)]))
        return common == root
    except ValueError:
        # Windows 上不同盘符 → 一定不在 root 下
        return False


def is_within_workspace(path: Path) -> bool:
    """检查 *path* 是否在工作区根目录内。

    路径和工作区根目录都会先经过 resolve（解析符号链接、折叠 ``..``）。
    """
    workspace = get_workspace_root()
    return _is_under_root(path.resolve(), workspace.resolve())


def resolve_path(file_path: str) -> Path:
    """将文件路径解析为绝对路径。

    若 *file_path* 是相对路径，则相对于工作区根目录解析。
    ``Path.resolve()`` 会归一化 ``..`` / ``.`` 并解析符号链接。
    """
    p = Path(file_path)
    if p.is_absolute():
        return p.resolve()
    return (get_workspace_root() / p).resolve()


def validate_path(file_path: str) -> Path:
    """解析并校验 *file_path* 是否在工作区内。

    执行的安全检查：
    1. ``Path.resolve()`` — 归一化 ``..`` / ``.`` 并解析符号链接，
       因此 ``../../etc/passwd`` 和指向外部的符号链接都会被解析为
       超出边界的路径。
    2. ``_is_under_root()`` — 通过 ``os.path.commonpath`` 进行
       组件级前缀检查，不受字符串前缀歧义影响。
    3. 符号链接逃逸检测 — 遍历路径的每个组件，确保中间的符号链接
       不指向工作区外。

    成功时返回解析后的 Path。
    若路径在工作区外，抛出 ValueError。
    """
    resolved = resolve_path(file_path)
    workspace = get_workspace_root().resolve()

    # --- 第一关：解析后的路径必须在工作区下 ---
    if not _is_under_root(resolved, workspace):
        raise ValueError(
            f"路径 '{file_path}' 超出工作区范围。"
            f"工作区根目录: {workspace}"
        )

    # --- 第二关：中间符号链接不得逃逸工作区 ---
    # 遍历每个组件，即使最终目标恰好在工作区内，
    # 途中的符号链接指向外部也会被拦截。
    check = Path(file_path if Path(file_path).is_absolute()
                 else str(get_workspace_root() / file_path))
    accumulated = Path()
    for part in check.parts:
        accumulated = accumulated / part
        if accumulated.is_symlink():
            target = accumulated.resolve()
            if not _is_under_root(target, workspace):
                raise ValueError(
                    f"路径 '{file_path}' 中的符号链接 '{accumulated}' "
                    f"指向工作区外 ({target})，操作被拒绝。"
                )

    return resolved


def get_platform_info() -> dict:
    """返回当前平台信息，供 LLM 上下文使用。"""
    system = platform.system()
    info = {
        "system": system,
        "shell": "cmd.exe / PowerShell" if system == "Windows" else "bash",
        "path_sep": "\\" if system == "Windows" else "/",
    }
    return info


def get_platform_hint() -> str:
    """返回平台相关的提示字符串，用于工具描述。"""
    system = platform.system()
    if system == "Windows":
        return "当前平台: Windows，请使用 Windows 兼容命令（如 dir 而非 ls，type 而非 cat）。路径使用 \\ 或 / 均可。"
    return f"当前平台: {system}，请使用 POSIX 兼容命令。"
