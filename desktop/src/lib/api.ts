// API 基础地址，初始化时从 Electron 主进程获取
export let API_BASE = 'http://localhost:8000/api';

// 初始化 API 基础地址
export async function initApiBase() {
  try {
    if (window.electronAPI) {
      // Electron 环境：从主进程获取
      const url = await window.electronAPI.getApiBaseUrl();
      console.log('[API] Got API URL from Electron:', url);
      API_BASE = url;
    } else {
      // 浏览器环境：使用环境变量或默认值
      API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api';
      console.log('[API] Using default API URL:', API_BASE);
    }
  } catch (error) {
    console.error('[API] Failed to get API URL from Electron:', error);
    API_BASE = 'http://localhost:8000/api';
    console.log('[API] Fallback to default:', API_BASE);
  }
  console.log('[API] Final API_BASE:', API_BASE);
}

// ---- 项目管理 ----

export interface ProjectSummary {
  id: string;
  name: string;
  root_path: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 获取所有项目列表。 */
export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) throw new Error(`Failed to list projects: ${res.status}`);
  return res.json();
}

/** 创建新项目。name 为可选参数（省略时自动生成）。 */
export async function createProject(name?: string): Promise<ProjectSummary> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name || undefined }),
  });
  if (!res.ok) throw new Error(`Failed to create project: ${res.status}`);
  return res.json();
}

/** 重命名项目（仅修改显示名称）。 */
export async function renameProject(projectId: string, name: string): Promise<ProjectSummary> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`Failed to rename project: ${res.status}`);
  return res.json();
}

/** 删除项目及其所有会话。 */
export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete project: ${res.status}`);
}

// ---- 会话管理 ----

export interface SessionSummary {
  id: string;
  title: string | null;
  turns: number;
  updated_at: string | null;
  project_id: string | null;
}

/** 获取会话列表，可按 project_id 进行筛选。 */
export async function listSessions(projectId?: string): Promise<SessionSummary[]> {
  const url = projectId
    ? `${API_BASE}/sessions?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/sessions`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  return res.json();
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  reply: string;
  session_id: string;
}

export interface SessionHistory {
  session_id: string;
  messages: ChatMessage[];
  turns: number;
}

/** 健康检查 - 后端可达时返回 true */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

// ---- 工作区 ----

/** 获取当前工作区根目录。 */
export async function getWorkspace(): Promise<string> {
  const res = await fetch(`${API_BASE}/workspace`);
  if (!res.ok) throw new Error(`Failed to get workspace: ${res.status}`);
  const data = await res.json();
  return data.workspace_root;
}

/** 在工作区中搜索文件或目录。 */
export async function searchWorkspace(name: string): Promise<string[]> {
  const res = await fetch(`${API_BASE}/workspace/search?name=${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error(`Failed to search workspace: ${res.status}`);
  const data = await res.json();
  return data.results;
}

/** 设置工作区根目录。 */
export async function setWorkspace(path: string): Promise<string> {
  const res = await fetch(`${API_BASE}/workspace`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  });
  if (!res.ok) throw new Error(`Failed to set workspace: ${res.status}`);
  const data = await res.json();
  return data.workspace_root;
}

/** 使用 Electron 对话框选择文件夹并将其设为工作区。 */
export async function selectAndSetWorkspace(): Promise<string | null> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available');
  }

  const result = await window.electronAPI.selectFolder();
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }

  const selectedPath = result.filePaths[0];
  const workspaceRoot = await setWorkspace(selectedPath);
  return workspaceRoot;
}

// ---- 聊天 ----

export type AgentStatus =
  | { status: 'thinking' }
  | { status: 'generating' }
  | { status: 'tool_start'; name: string; args: unknown }
  | { status: 'tool_end'; name: string; output: string }
  | {
      status: 'confirmation_required';
      confirmation_id: string;
      tool_name: string;
      tool_args: Record<string, unknown>;
      description: string;
    }
  | {
      status: 'confirmation_expired';
      confirmation_id: string;
      tool_name: string;
    };

/** 发送消息并获取响应（非流式）。 */
export async function sendMessage(
  message: string,
  sessionId?: string,
  projectId?: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      project_id: projectId,
    }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.status}`);
  return res.json();
}

/** 发送消息并获取流式响应。返回一个中止函数。 */
export function sendMessageStream(
  message: string,
  sessionId: string | undefined,
  callbacks: {
    onSession: (sessionId: string) => void;
    onStatus: (status: AgentStatus) => void;
    onChunk: (content: string) => void;
    onDone: (fullContent: string, sessionId: string) => void;
    onError: (error: string) => void;
  },
  mode: string = 'confirm',
  projectId?: string
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      console.log('[API] Sending message to:', `${API_BASE}/chat/stream`);
      console.log('[API] Current API_BASE:', API_BASE);
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          session_id: sessionId,
          project_id: projectId,
          mode,
        }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        callbacks.onError(`Request failed: ${res.status}`);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const data = line.slice(5).trim();
            if (!data) continue;
            try {
              const parsed = JSON.parse(data);
              if (currentEvent === 'session') {
                callbacks.onSession(parsed.session_id);
              } else if (currentEvent === 'status') {
                callbacks.onStatus(parsed as AgentStatus);
                await new Promise((r) => setTimeout(r, 0));
              } else if (currentEvent === 'chunk') {
                callbacks.onChunk(parsed.content);
              } else if (currentEvent === 'done') {
                callbacks.onDone(parsed.content, parsed.session_id);
              } else if (currentEvent === 'error') {
                callbacks.onError(parsed.error || 'Unknown error');
              }
            } catch {
              // 跳过格式错误的 JSON
            }
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('[API] Stream error:', err);
      callbacks.onError(String(err));
    }
  })();

  return () => controller.abort();
}

// ---- 会话管理 ----

/** 获取会话历史记录。 */
export async function getSessionHistory(sessionId: string): Promise<SessionHistory> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/history`);
  if (!res.ok) throw new Error(`Failed to get session history: ${res.status}`);
  return res.json();
}

/** 删除会话。 */
export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.status}`);
}

/** 同步会话消息（前端编辑/删除后调用）。 */
export async function syncSessionMessages(
  sessionId: string,
  messages: ChatMessage[],
  turns: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/messages`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, turns }),
  });
  if (!res.ok) throw new Error(`Failed to sync session messages: ${res.status}`);
}

/** 生成会话标题。 */
export async function generateSessionTitle(
  sessionId: string,
  userMessage: string,
  assistantMessage: string
): Promise<{ title: string | null }> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/generate-title`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_message: userMessage, assistant_message: assistantMessage }),
  });
  if (!res.ok) throw new Error(`Failed to generate title: ${res.status}`);
  return res.json();
}

/** 更新会话标题。 */
export async function updateSessionTitle(sessionId: string, title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/title`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Failed to update title: ${res.status}`);
}

// ---- 确认机制 ----

/** 处理确认请求。 */
export async function resolveConfirmation(
  confirmationId: string,
  approved: boolean,
  allowAlways?: boolean
): Promise<void> {
  const res = await fetch(`${API_BASE}/confirm/${confirmationId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved, allow_always: allowAlways }),
  });
  if (!res.ok) throw new Error(`Failed to resolve confirmation: ${res.status}`);
}

// ---- 系统 ----

/** 获取可用技能列表。 */
export async function listSkills(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/skills`);
  if (!res.ok) throw new Error(`Failed to list skills: ${res.status}`);
  return res.json();
}

/** 获取技能详情。 */
export async function getSkillDetails(name: string): Promise<any> {
  const res = await fetch(`${API_BASE}/skills/${name}`);
  if (!res.ok) throw new Error(`Failed to get skill details: ${res.status}`);
  return res.json();
}

/** 获取可用提供商列表。 */
export async function listProviders(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/providers`);
  if (!res.ok) throw new Error(`Failed to list providers: ${res.status}`);
  return res.json();
}
