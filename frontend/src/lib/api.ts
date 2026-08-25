const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api";

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

/** Non-streaming chat request */
export async function sendMessage(
  message: string,
  sessionId?: string
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
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
  }
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId }),
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