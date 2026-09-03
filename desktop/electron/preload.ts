import { contextBridge, ipcRenderer } from 'electron';

// 暴露安全的 API 给渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
  // 应用信息
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getPlatform: () => ipcRenderer.invoke('get-platform'),

  // 窗口控制
  minimizeWindow: () => ipcRenderer.invoke('minimize-window'),
  maximizeWindow: () => ipcRenderer.invoke('maximize-window'),
  isMaximized: () => ipcRenderer.invoke('is-maximized'),
  closeWindow: () => ipcRenderer.invoke('close-window'),

  // 文件对话框
  showOpenDialog: (options: Electron.OpenDialogOptions) =>
    ipcRenderer.invoke('show-open-dialog', options),
  showSaveDialog: (options: Electron.SaveDialogOptions) =>
    ipcRenderer.invoke('show-save-dialog', options),

  // 选择文件夹对话框
  selectFolder: () => ipcRenderer.invoke('select-folder'),

  // 获取常用路径
  getDesktopPath: () => ipcRenderer.invoke('get-desktop-path'),
  getDocumentsPath: () => ipcRenderer.invoke('get-documents-path'),
  getUserDataPath: () => ipcRenderer.invoke('get-user-data-path'),

  // API 配置
  getApiBaseUrl: () => ipcRenderer.invoke('get-api-base-url'),

  // 事件监听
  onNewSession: (callback: () => void) => {
    ipcRenderer.on('new-session', callback);
    return () => {
      ipcRenderer.removeListener('new-session', callback);
    };
  },

  // 更新相关
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  onUpdateAvailable: (callback: (info: any) => void) => {
    ipcRenderer.on('update-available', (_event, info) => callback(info));
  },
  onUpdateDownloaded: (callback: (info: any) => void) => {
    ipcRenderer.on('update-downloaded', (_event, info) => callback(info));
  },
  installUpdate: () => ipcRenderer.invoke('install-update'),
});
