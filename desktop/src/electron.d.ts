export {};

declare global {
  interface Window {
    electronAPI: {
      // 应用信息
      getAppVersion: () => Promise<string>;
      getPlatform: () => Promise<string>;

      // 窗口控制
      minimizeWindow: () => Promise<void>;
      maximizeWindow: () => Promise<void>;
      isMaximized: () => Promise<boolean>;
      closeWindow: () => Promise<void>;

      // 文件对话框
      showOpenDialog: (
        options: Electron.OpenDialogOptions
      ) => Promise<Electron.OpenDialogReturnValue>;
      showSaveDialog: (
        options: Electron.SaveDialogOptions
      ) => Promise<Electron.SaveDialogReturnValue>;

      // 选择文件夹对话框
      selectFolder: () => Promise<Electron.OpenDialogReturnValue>;

      // 获取常用路径
      getDesktopPath: () => Promise<string>;
      getDocumentsPath: () => Promise<string>;
      getUserDataPath: () => Promise<string>;

      // API 配置
      getApiBaseUrl: () => Promise<string>;

      // 事件监听
      onNewSession: (callback: () => void) => () => void;

      // 更新相关
      checkForUpdates: () => Promise<void>;
      onUpdateAvailable: (callback: (info: any) => void) => void;
      onUpdateDownloaded: (callback: (info: any) => void) => void;
      installUpdate: () => Promise<void>;
    };
  }
}
