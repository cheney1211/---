import { Tray, Menu, nativeImage, app, BrowserWindow } from 'electron';
import path from 'path';
import { setQuitting } from './main';

export function createTray(mainWindow: BrowserWindow): Tray {
  console.log('[Tray] Creating tray...');

  // 创建托盘图标
  const iconPath = path.join(__dirname, '../resources/tray-icon.png');
  console.log('[Tray] Icon path:', iconPath);

  let icon: Electron.NativeImage;

  try {
    icon = nativeImage.createFromPath(iconPath);
    if (icon.isEmpty()) {
      console.warn('[Tray] Icon is empty, using fallback');
      icon = nativeImage.createEmpty();
    } else {
      // 调整图标大小
      if (process.platform === 'win32') {
        icon = icon.resize({ width: 16, height: 16 });
      } else {
        icon = icon.resize({ width: 22, height: 22 });
      }
    }
  } catch (error) {
    console.warn('[Tray] Failed to load icon:', error);
    icon = nativeImage.createEmpty();
  }

  const tray = new Tray(icon);
  console.log('[Tray] Tray created');

  // 创建右键菜单
  const contextMenu = Menu.buildFromTemplate([
    {
      label: '显示主窗口',
      click: () => {
        mainWindow.show();
        mainWindow.focus();
      },
    },
    { type: 'separator' },
    {
      label: '新建对话',
      click: () => {
        mainWindow.show();
        mainWindow.focus();
        mainWindow.webContents.send('new-session');
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        // 设置退出标志，允许窗口真正关闭
        setQuitting(true);
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Coco AI 助手');
  tray.setContextMenu(contextMenu);

  // 点击托盘图标显示/隐藏窗口
  tray.on('click', () => {
    if (mainWindow.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  // 双击托盘图标显示窗口
  tray.on('double-click', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  console.log('[Tray] Tray setup complete');
  return tray;
}
