"""Electron专用入口：绑定127.0.0.1，禁用reload，适合打包后运行。"""

from web.app import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )
