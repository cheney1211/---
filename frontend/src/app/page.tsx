"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { PanelLeftClose, PanelLeft } from "lucide-react";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";
import Sidebar, { type SessionMeta } from "@/components/Sidebar";
import SuggestedPrompts from "@/components/SuggestedPrompts";
import {
  sendMessageStream,
  checkHealth,
  getSessionHistory,
  deleteSession as apiDeleteSession,
  type AgentStatus,
} from "@/lib/api";

// ---- helpers ----
function generateId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const STORAGE_KEY = "coco_sessions";

function loadSessions(): SessionMeta[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveSessions(sessions: SessionMeta[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

// ---- page ----
export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);

  // ---- init ----
  useEffect(() => {
    setSessions(loadSessions());
    checkHealth().then(setIsConnected);
    const timer = setInterval(() => checkHealth().then(setIsConnected), 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, agentStatus]);

  // ---- session helpers ----
  const updateSessionMeta = useCallback(
    (sid: string, userMsg: string) => {
      setSessions((prev) => {
        const idx = prev.findIndex((s) => s.id === sid);
        const meta: SessionMeta =
          idx >= 0
            ? {
                ...prev[idx],
                title: prev[idx].messageCount === 0 ? userMsg.slice(0, 30) : prev[idx].title,
                messageCount: prev[idx].messageCount + 2,
                updatedAt: Date.now(),
              }
            : {
                id: sid,
                title: userMsg.slice(0, 30),
                updatedAt: Date.now(),
                messageCount: 2,
              };
        const next = [...prev];
        if (idx >= 0) next[idx] = meta;
        else next.unshift(meta);
        return next;
      });
    },
    []
  );

  const handleSelectSession = useCallback(
    async (sid: string) => {
      if (sid === sessionId) return;
      if (isStreaming) return;
      setSessionId(sid);
      try {
        const history = await getSessionHistory(sid);
        setMessages(
          history.messages.map((m, i) => ({
            id: `${sid}-${i}`,
            role: m.role as "user" | "assistant",
            content: m.content,
          }))
        );
      } catch {
        setMessages([]);
      }
    },
    [sessionId, isStreaming]
  );

  const handleNewSession = useCallback(() => {
    if (isStreaming) return;
    setSessionId(undefined);
    setMessages([]);
  }, [isStreaming]);

  const handleDeleteSession = useCallback(
    async (sid: string) => {
      apiDeleteSession(sid).catch(() => {});
      setSessions((prev) => prev.filter((s) => s.id !== sid));
      if (sid === sessionId) {
        setSessionId(undefined);
        setMessages([]);
      }
    },
    [sessionId]
  );

  // ---- chat ----
  const handleSend = useCallback(
    (text: string) => {
      if (isStreaming) return;

      const userId = generateId();
      const assistantId = generateId();

      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: text },
        { id: assistantId, role: "assistant", content: "" },
      ]);
      setIsStreaming(true);
      setAgentStatus({ status: "thinking" });

      const abort = sendMessageStream(text, sessionId, {
        onSession: (sid) => {
          setSessionId(sid);
          updateSessionMeta(sid, text);
        },
        onStatus: (status) => {
          setAgentStatus(status);
        },
        onChunk: (token) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + token } : m
            )
          );
        },
        onDone: (fullContent) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: fullContent } : m
            )
          );
          setIsStreaming(false);
          setAgentStatus(null);
        },
        onError: (err) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: `[Error] ${err}` }
                : m
            )
          );
          setIsStreaming(false);
          setAgentStatus(null);
        },
      });

      abortRef.current = abort;
    },
    [isStreaming, sessionId, updateSessionMeta]
  );

  const handleStop = () => {
    abortRef.current?.();
    setIsStreaming(false);
    setAgentStatus(null);

    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "assistant" && !last.content) {
        return prev.slice(0, -1);
      }
      return prev;
    });
  };


  // ---- render ----
  const isEmpty = messages.length === 0;

  return (
    <div className="app-layout">
      {sidebarOpen && (
        <Sidebar
          sessions={sessions}
          activeSessionId={sessionId}
          isConnected={isConnected}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
          onDelete={handleDeleteSession}
        />
      )}

      <div className="main-area">
        <header className="main-header">
          <button
            className="sidebar-toggle"
            onClick={() => setSidebarOpen((v) => !v)}
            title={sidebarOpen ? "收起侧边栏" : "展开侧边栏"}
          >
            {sidebarOpen ? <PanelLeftClose size={18} /> : <PanelLeft size={18} />}
          </button>
          <h1 className="main-header-title">Coco</h1>
          <div className={`header-status-dot ${isConnected ? "connected" : ""}`} />
        </header>

        <main ref={scrollRef} className="messages-area">
          {isEmpty ? (
            <SuggestedPrompts onSelect={handleSend} />
          ) : (
            <div className="messages-list">
              {messages.map((msg, i) => {
                const isLast = i === messages.length - 1;
                const showStatus = isStreaming && msg.role === "assistant" && isLast;
                return (
                  <ChatMessage
                    key={msg.id}
                    role={msg.role}
                    content={msg.content}
                    isStreaming={showStatus}
                    status={showStatus ? agentStatus : null}
                  />
                );
              })}
            </div>
          )}
        </main>

        <ChatInput onSend={handleSend} disabled={isStreaming} onStop={handleStop} />
      </div>
    </div>
  );
}
