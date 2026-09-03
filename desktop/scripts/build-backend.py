"""
Build Python backend into standalone executable using PyInstaller.

Usage:
    python scripts/build-backend.py

Output:
    dist-backend/xiaozhushou-backend/
"""

import os
import sys
import shutil
import subprocess


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_src = os.path.join(project_root, "backend")
    dist_dir = os.path.join(project_root, "dist-backend")
    build_dir = os.path.join(project_root, "build-backend")

    # Ensure we're in the right directory
    os.chdir(project_root)

    print("=" * 60)
    print("Building Coco AI Desktop - Python Backend")
    print("=" * 60)

    # Clean previous builds
    for d in [dist_dir, build_dir]:
        if os.path.exists(d):
            print(f"Cleaning {d}...")
            shutil.rmtree(d)

    # PyInstaller arguments
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        # Entry point
        os.path.join(backend_src, "web", "app_electron.py"),
        # Output
        "--name=xiaozhushou-backend",
        "--onedir",
        "--noconfirm",
        "--clean",
        # Hidden imports for uvicorn
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=uvicorn.lifespan",
        "--hidden-import=uvicorn.lifespan.on",
        # Hidden imports for langchain/langgraph
        "--hidden-import=langchain",
        "--hidden-import=langchain_core",
        "--hidden-import=langchain_openai",
        "--hidden-import=langgraph",
        "--hidden-import=langgraph.checkpoint",
        "--hidden-import=langgraph.checkpoint.sqlite",
        "--hidden-import=langgraph.prebuilt",
        # Hidden imports for SQLAlchemy
        "--hidden-import=sqlalchemy.dialects.sqlite",
        "--hidden-import=aiosqlite",
        # Hidden imports for SSE
        "--hidden-import=sse_starlette",
        # Add data files
        f"--add-data={os.path.join(backend_src, 'assistant', 'prompts')};assistant/prompts",
        f"--add-data={os.path.join(project_root, 'skills')};skills",
        # Exclude unnecessary modules
        "--exclude-module=tkinter",
        "--exclude-module=matplotlib",
        "--exclude-module=numpy",
        "--exclude-module=pandas",
        "--exclude-module=PIL",
        "--exclude-module=pytest",
        "--exclude-module=IPython",
        # Output directories
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={os.path.join(project_root, 'scripts')}",
    ]

    # Add .env if it exists
    env_file = os.path.join(project_root, ".env")
    if os.path.exists(env_file):
        args.append(f"--add-data={env_file};.")

    print("\nRunning PyInstaller...")
    print(" ".join(args))
    print()

    result = subprocess.run(args, cwd=project_root)

    if result.returncode != 0:
        print("\nERROR: PyInstaller build failed!")
        sys.exit(1)

    # Copy data directory (database files)
    data_src = os.path.join(project_root, "data")
    data_dst = os.path.join(dist_dir, "xiaozhushou-backend", "data")
    if os.path.exists(data_src):
        print(f"\nCopying data directory...")
        if os.path.exists(data_dst):
            shutil.rmtree(data_dst)
        shutil.copytree(data_src, data_dst)

    # Copy workspace directory
    workspace_src = os.path.join(project_root, "workSpace")
    workspace_dst = os.path.join(dist_dir, "xiaozhushou-backend", "workSpace")
    if os.path.exists(workspace_src):
        print(f"Copying workspace directory...")
        if os.path.exists(workspace_dst):
            shutil.rmtree(workspace_dst)
        shutil.copytree(workspace_src, workspace_dst)

    print("\n" + "=" * 60)
    print("Build complete!")
    print(f"Output: {os.path.join(dist_dir, 'xiaozhushou-backend')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
