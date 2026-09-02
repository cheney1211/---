const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

// ---- Projects ----

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string | null;
  updated_at: string | null;
}

/** List all projects. */
export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${API_BASE}/projects`);
  if (!res.ok) throw new Error(`Failed to list projects: ${res.status}`);
  return res.json();
}

/** Create a new project. name is optional (auto-generated if omitted). */
export async function createProject(name?: string): Promise<ProjectSummary> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || undefined }),
  });
  if (!res.ok) throw new Error(`Failed to create project: ${res.status}`);
  return res.json();
}

/** Rename a project (display name only). */
export async function renameProject(projectId: string, name: string): Promise<ProjectSummary> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`Failed to rename project: ${res.status}`);
  return res.json();
}

/** Delete a project and all its sessions. */
export async function deleteProject(projectId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${projectId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete project: ${res.status}`);
}

// ---- Sessions ----

export interface SessionSummary {
  id: string;
  title: string | null;
  turns: number;
  updated_at: string | null;
}

/** List sessions, optionally filtered by project_id. */
export async function listSessions(projectId?: string): Promise<SessionSummary[]> {
  const url = projectId
    ? `${API_BASE}/sessions?project_id=${encodeURIComponent(projectId)}`
    : `${API_BASE}/sessions`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  return res.json();
}

export interface ChatMessage {
  role: "user" | "assistant";
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

/** Health check - returns true if backend is reachable */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    return res.ok;
  } catch {
    return false;
  }
}

// ---- Workspace ----

/** Get the current workspace root directory. */
export async function getWorkspace(): Promise<string> {
  const res = await fetch(`${API_BASE}/workspace`);
  if (!res.ok) throw new Error(`Failed to get workspace: ${res.status}`);
  const data = await res.json();
  return data.workspace_root;
}

/** Search for directories matching a folder name. */
export async function searchWorkspace(name: string): Promise<string[]> {
  const res = await fetch(`${API_BASE}/workspace/search?name=${encodeURIComponent(name)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.matches ?? [];
}

/** Update the workspace root directory. */
export async function setWorkspace(path: string): Promise<{ name: string; matches?: string[] }> {
  const res = await fetch(`${API_BASE}/workspace`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.error || `Failed to set workspace: ${res.status}`);
  return { name: data.workspace_root, matches: data.matches };
}

/** Get session conversation history */
export async function getSessionHistory(sessionId: string): Promise<SessionHistory> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/history`);
  if (!res.ok) throw new Error(`Failed to get history: ${res.status}`);
  return res.json();
}

/** Delete a session */
export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/session/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete session: ${res.status}`);
}

/** Sync updated messages back to the backend after local edits/deletions */
export async function syncSessionMessages(
  sessionId: string,
  messages: ChatMessage[],
  turns: number
): Promise<void> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/messages`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, turns }),
  });
  if (!res.ok) throw new Error(`Failed to sync messages: ${res.status}`);
}

/** Trigger LLM-based title generation after the first assistant reply. */
export async function generateSessionTitle(
  sessionId: string,
  userMessage: string,
  assistantMessage: string
): Promise<{ title: string | null }> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/generate-title`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_message: userMessage,
      assistant_message: assistantMessage,
    }),
  });
  if (!res.ok) throw new Error(`Failed to generate title: ${res.status}`);
  return res.json();
}

/** Manually update a session's title. */
export async function updateSessionTitle(
  sessionId: string,
  title: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/session/${sessionId}/title`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Failed to update title: ${res.status}`);
}

/** Non-streaming chat request */
export async function sendMessage(
  message: string,
  sessionId?: string,
  projectId?: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId, project_id: projectId }),
  });
  if (!res.ok) throw new Error(`Chat request failed: ${res.status}`);
  return res.json();
}

// ---- Status types ----
export type AgentStatus =
  | { status: "thinking" }
  | { status: "generating" }
  | { status: "tool_start"; name: string; args: unknown }
  | { status: "tool_end"; name: string; output: string }
  | {
      status: "confirmation_required";
      confirmation_id: string;
      tool_name: string;
      tool_args: Record<string, unknown>;
      description: string;
    }
  | {
      status: "confirmation_expired";
      confirmation_id: string;
      tool_name: string;
    };

// ---- Confirmation API ----

/** Approve or reject a pending tool confirmation. */
export async function resolveConfirmation(
  confirmationId: string,
  approved: boolean
): Promise<void> {
  const res = await fetch(`${API_BASE}/confirm/${confirmationId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved }),
  });
  if (!res.ok) throw new Error(`Confirmation request failed: ${res.status}`);
}

// ---- SSE streaming ----

/** SSE streaming chat with rich status events. */
export function sendMessageStream(
  message: string,
  sessionId: string | undefined,
  callbacks: {
    onSession?: (sessionId: string) => void;
    onStatus?: (status: AgentStatus) => void;
    onChunk?: (content: string) => void;
    onDone?: (fullContent: string, sessionId: string) => void;
    onError?: (error: string) => void;
  },
  mode?: string,
  projectId?: string
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId, project_id: projectId, mode: mode || "confirm" }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        callbacks.onError?.(`Request failed: ${res.status}`);
        return;
      }

     const reader = res.body.getReader();
     const decoder = new TextDecoder();
     let buffer = "";
     let currentEvent = "";

     while (true) {
       const { done, value } = await reader.read();
       if (done) break;

       buffer += decoder.decode(value, { stream: true });
       const lines = buffer.split("\n");
       buffer = lines.pop() || "";

         for (const line of lines) {
            if (line.startsWith("event:")) {
              currentEvent = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              const data = line.slice(5).trim();
              if (!data) continue;
              try {
                const parsed = JSON.parse(data);
                if (currentEvent === "session") {
                  callbacks.onSession?.(parsed.session_id);
               } else if (currentEvent === "status") {
                 callbacks.onStatus?.(parsed as AgentStatus);
                 await new Promise((r) => setTimeout(r, 0));
               } else if (currentEvent === "chunk") {
                  callbacks.onChunk?.(parsed.content);
                } else if (currentEvent === "done") {
                  callbacks.onDone?.(parsed.content, parsed.session_id);
                }
              } catch {
                // skip malformed JSON
              }
            }
          }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      callbacks.onError?.(String(err));
    }
  })();

  return () => controller.abort();
}
