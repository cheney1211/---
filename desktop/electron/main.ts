import { app, BrowserWindow, Menu, nativeImage, Tray, ipcMain, dialog } from 'electron';
import path from 'path';
import { PythonManager } from './python-manager';
import { createTray } from './tray';

// 获取常用路径的辅助函数
function getDesktopPath(): string {
  return app.getPath('desktop');
}

function getDocumentsPath(): string {
  return app.getPath('documents');
}

function getUserDataPath(): string {
  return app.getPath('userData');
}

let mainWindow: BrowserWindow | null = null;
let splashWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let pythonManager: PythonManager;

const isDev = !app.isPackaged;

// 标记是否正在退出应用
let isQuitting = false;

// 导出 isQuitting 状态供 tray 使用
export function setQuitting(value: boolean) {
  isQuitting = value;
}

export function getQuitting() {
  return isQuitting;
}

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 400,
    height: 300,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    webPreferences: {
      nodeIntegration: false,
    },
  });

  // 内联启动画面 HTML
  const splashHtml = `
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          background: #0c0c0e;
          border-radius: 12px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          color: #eaeaf0;
        }
        .logo { font-size: 48px; margin-bottom: 16px; }
        .title { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
        .subtitle { font-size: 14px; color: #8e8e9a; margin-bottom: 24px; }
        .spinner {
          width: 24px; height: 24px;
          border: 3px solid #26262e;
          border-top: 3px solid #7c6cff;
          border-radius: 50%;
          animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
    </head>
    <body>
      <div class="logo">🤖</div>
      <div class="title">Coco AI 助手</div>
      <div class="subtitle">正在启动后端服务...</div>
      <div class="spinner"></div>
    </body>
    </html>
  `;

  splashWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(splashHtml)}`);
  return splashWindow;
}

function createMainWindow() {
  console.log('[Main] Creating BrowserWindow...');
  const isMac = process.platform === 'darwin';
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    // macOS 使用原生标题栏，Windows/Linux 使用无边框窗口
    titleBarStyle: isMac ? 'hiddenInset' : undefined,
    frame: isMac,
    icon: path.join(__dirname, '../resources/icon.png'),
  });

  // 加载应用
  if (isDev) {
    console.log('[Main] Loading dev URL: http://localhost:5173');
    mainWindow.loadURL('http://localhost:5173');
  } else {
    console.log('[Main] Loading production file');
    mainWindow.loadFile(path.join(__dirname, '../dist-react/index.html'));
  }

  // 窗口准备好后显示
  mainWindow.once('ready-to-show', () => {
    console.log('[Main] Window ready to show');
    // 关闭启动画面，显示主窗口
    if (splashWindow) {
      splashWindow.close();
      splashWindow = null;
    }
    mainWindow?.show();
  });

  // 点击关闭按钮时隐藏到托盘，而不是退出
  mainWindow.on('close', (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.on('closed', () => {
    console.log('[Main] Window closed');
    mainWindow = null;
  });

  // 添加错误处理
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription) => {
    console.error('[Main] Failed to load:', errorCode, errorDescription);
  });

  // 创建系统托盘
  try {
    tray = createTray(mainWindow);
    console.log('[Main] Tray created');
  } catch (error) {
    console.error('[Main] Failed to create tray:', error);
  }
}

// 注册 IPC 处理器
function registerIpcHandlers() {
  ipcMain.handle('get-app-version', () => app.getVersion());
  ipcMain.handle('get-platform', () => process.platform);

  ipcMain.handle('minimize-window', () => mainWindow?.minimize());
  ipcMain.handle('maximize-window', () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow?.maximize();
    }
  });
  ipcMain.handle('is-maximized', () => mainWindow?.isMaximized() ?? false);
  ipcMain.handle('close-window', () => mainWindow?.close());

  ipcMain.handle('get-api-base-url', () => {
    return pythonManager.getApiBaseUrl();
  });

  ipcMain.handle('show-open-dialog', async (_event, options) => {
    if (!mainWindow) return { canceled: true, filePaths: [] };
    return dialog.showOpenDialog(mainWindow, options);
  });

  ipcMain.handle('show-save-dialog', async (_event, options) => {
    if (!mainWindow) return { canceled: true, filePath: '' };
    return dialog.showSaveDialog(mainWindow, options);
  });

  // 选择文件夹对话框
  ipcMain.handle('select-folder', async () => {
    if (!mainWindow) return { canceled: true, filePaths: [] };
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory'],
      title: '选择工作区文件夹',
    });
    return result;
  });

  // 获取常用路径
  ipcMain.handle('get-desktop-path', () => getDesktopPath());
  ipcMain.handle('get-documents-path', () => getDocumentsPath());
  ipcMain.handle('get-user-data-path', () => getUserDataPath());
}

// 设置应用菜单
function setupAppMenu() {
  const isMac = process.platform === 'darwin';

  const template: Electron.MenuItemConstructorOptions[] = [
    // macOS 应用菜单
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' as const },
              { type: 'separator' as const },
              { role: 'quit' as const },
            ],
          },
        ]
      : []),
    {
      label: 'File',
      submenu: [isMac ? { role: 'close' } : { role: 'quit' }],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(isMac
          ? [{ type: 'separator' as const }, { role: 'front' as const }]
          : [{ role: 'close' as const }]),
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

app.whenReady().then(async () => {
  console.log('[Main] App is ready');
  registerIpcHandlers();
  setupAppMenu();

  // 开发模式下跳过自动启动后端（需要手动启动）
  if (!isDev) {
    // 生产模式：显示启动画面并启动 Python 后端
    createSplashWindow();

    pythonManager = new PythonManager();
    try {
      await pythonManager.start();
      console.log('[Main] Python backend started successfully');
    } catch (error) {
      console.error('[Main] Failed to start Python backend:', error);
      if (splashWindow) {
        splashWindow.close();
        splashWindow = null;
      }
      dialog.showErrorBox(
        '启动失败',
        `无法启动后端服务: ${error instanceof Error ? error.message : String(error)}\n\n请确保 Python 环境已正确配置。`
      );
      app.quit();
      return;
    }
  } else {
    // 开发模式：创建虚拟的 pythonManager
    pythonManager = new PythonManager();
    console.log('[Main] Dev mode: skipping Python backend auto-start');
  }

  console.log('[Main] Creating main window...');
  createMainWindow();
  console.log('[Main] Main window created');
}).catch((error) => {
  console.error('[Main] Error in app.whenReady():', error);
});

app.on('window-all-closed', () => {
  console.log('[Main] All windows closed');
  pythonManager.stop();
  // 在开发模式下不自动退出，方便调试
  if (!isDev && process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createMainWindow();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  pythonManager.stop();
});
