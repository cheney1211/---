import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import { app } from 'electron';

export class PythonManager {
  private process: ChildProcess | null = null;
  private port: number = 8000;
  private isReady: boolean = false;
  private startupTimeout: number = 60000;

  async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      const isPackaged = app.isPackaged;
      let pythonPath: string;
      let args: string[];
      let cwd: string;

      if (isPackaged) {
        // 生产环境：使用打包后的可执行文件
        const backendDir = path.join(process.resourcesPath, 'backend');
        pythonPath = process.platform === 'win32'
          ? path.join(backendDir, 'xiaozhushou-backend.exe')
          : path.join(backendDir, 'xiaozhushou-backend');
        args = [];
        cwd = backendDir;
      } else {
        // 开发环境：使用系统 Python
        pythonPath = 'python';
        args = ['-m', 'web.app'];
        cwd = path.join(__dirname, '../..');
      }

      console.log('[PythonManager] Starting backend...');
      console.log('[PythonManager] Python path:', pythonPath);
      console.log('[PythonManager] Args:', args);
      console.log('[PythonManager] CWD:', cwd);

      this.process = spawn(pythonPath, args, {
        cwd,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: '1',
          PYTHONIOENCODING: 'utf-8',
        },
        stdio: ['pipe', 'pipe', 'pipe'],
        shell: process.platform === 'win32' && !isPackaged,
      });

      let startupBuffer = '';

      this.process.stdout?.on('data', (data: Buffer) => {
        const output = data.toString();
        console.log(`[Python stdout] ${output.trim()}`);
        startupBuffer += output;

        if (this.checkReady(startupBuffer)) {
          this.isReady = true;
          resolve();
        }
      });

      this.process.stderr?.on('data', (data: Buffer) => {
        const output = data.toString();
        console.log(`[Python stderr] ${output.trim()}`);
        startupBuffer += output;

        // 某些版本的 uvicorn 会输出到 stderr
        if (this.checkReady(startupBuffer)) {
          this.isReady = true;
          resolve();
        }
      });

      this.process.on('error', (error) => {
        console.error('[PythonManager] Process error:', error);
        reject(new Error(`Failed to start Python process: ${error.message}`));
      });

      this.process.on('exit', (code, signal) => {
        console.log(`[PythonManager] Process exited: code=${code}, signal=${signal}`);
        this.isReady = false;
        // 仅在尚未 resolve 时才 reject
        if (!this.isReady && code !== 0) {
          reject(new Error(`Python process exited with code ${code}`));
        }
      });

      // 超时处理
      setTimeout(() => {
        if (!this.isReady) {
          reject(new Error('Python backend startup timeout'));
        }
      }, this.startupTimeout);
    });
  }

  private checkReady(output: string): boolean {
    return (
      output.includes('Uvicorn running on') ||
      output.includes('Application startup complete') ||
      output.includes('Started server process')
    );
  }

  stop() {
    if (this.process) {
      console.log('[PythonManager] Stopping backend...');
      this.process.kill('SIGTERM');

      // 如果 5 秒后仍未退出，则强制终止
      setTimeout(() => {
        if (this.process && !this.process.killed) {
          console.log('[PythonManager] Force killing backend...');
          this.process.kill('SIGKILL');
        }
      }, 5000);

      this.process = null;
      this.isReady = false;
    }
  }

  getApiBaseUrl(): string {
    return `http://127.0.0.1:${this.port}/api`;
  }

  isBackendReady(): boolean {
    return this.isReady;
  }
}
