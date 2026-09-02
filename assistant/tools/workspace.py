"""
Workspace utilities -- path validation and platform info.

Provides shared helpers for enforcing workspace directory restrictions
across all file-operation tools.

Resolution order for workspace root:
1. data/workspace.json (persisted via web UI)
2. WORKSPACE_ROOT environment variable
3. Project root directory (fallback)
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
from pathlib import Path
from typing import Optional

# Project root: two levels up from this file (assistant/tools/workspace.py -> project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_FILE = _PROJECT_ROOT / "data" / "workspace.json"
_WORKSPACE_ROOT = _PROJECT_ROOT / "workSpace"

# Per-request project context: set by chat_service before tool execution
_current_project_workspace: Optional[Path] = None


def get_project_workspace(project_id: str) -> Path:
    """Return the workspace directory for a specific project.

    Path rule: <project_root>/workSpace/<project_id>/
    """
    return (_WORKSPACE_ROOT / project_id).resolve()


def ensure_project_dir(project_id: str) -> Path:
    """Ensure the project workspace directory exists and return it."""
    p = get_project_workspace(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


@contextlib.contextmanager
def project_context(project_id: str | None):
    """Context manager that sets the active project workspace for tool execution."""
    global _current_project_workspace
    old = _current_project_workspace
    try:
        _current_project_workspace = get_project_workspace(project_id) if project_id else None
        yield
    finally:
        _current_project_workspace = old


def get_workspace_root() -> Path:
    """Return the workspace root directory.

    If a project context is active, returns the project workspace.
    Otherwise falls back to legacy resolution order.
    """
    # 1. Active project context (set by chat_service per request)
    if _current_project_workspace is not None:
        return _current_project_workspace

    # 2. Legacy: persisted config file
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            root = data.get("workspace_root")
            if root:
                return Path(root).resolve()
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Legacy: environment variable
    env = os.getenv("WORKSPACE_ROOT")
    if env:
        return Path(env).resolve()

    # 4. Fallback to project root
    return _PROJECT_ROOT


def set_workspace_root(path: str) -> Path:
    """Persist the workspace root to data/workspace.json.

    Returns the resolved Path.
    Raises ValueError if the path does not exist or is not a directory.
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


def is_within_workspace(path: Path) -> bool:
    """Check whether *path* is inside the workspace root."""
    workspace = get_workspace_root()
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def resolve_path(file_path: str) -> Path:
    """Resolve a file path to an absolute path.

    If *file_path* is relative, it is resolved against the workspace root.
    """
    p = Path(file_path)
    if p.is_absolute():
        return p.resolve()
    return (get_workspace_root() / p).resolve()


def validate_path(file_path: str) -> Path:
    """Resolve and validate that *file_path* is within the workspace.

    Returns the resolved Path on success.
    Raises ValueError if the path is outside the workspace.
    """
    resolved = resolve_path(file_path)
    if not is_within_workspace(resolved):
        workspace = get_workspace_root()
        raise ValueError(
            f"路径 '{file_path}' 超出工作区范围。"
            f"工作区根目录: {workspace}"
        )
    return resolved


def get_platform_info() -> dict:
    """Return current platform information for LLM context."""
    system = platform.system()
    info = {
        "system": system,
        "shell": "cmd.exe / PowerShell" if system == "Windows" else "bash",
        "path_sep": "\\" if system == "Windows" else "/",
    }
    return info


def get_platform_hint() -> str:
    """Return a platform-specific hint string for tool descriptions."""
    system = platform.system()
    if system == "Windows":
        return "当前平台: Windows，请使用 Windows 兼容命令（如 dir 而非 ls，type 而非 cat）。路径使用 \\ 或 / 均可。"
    return f"当前平台: {system}，请使用 POSIX 兼容命令。"
