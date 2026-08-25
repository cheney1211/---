"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { PanelLeftClose, PanelLeft, X, Trash2, Check } from "lucide-react";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";
import ConfirmationDialog from "@/components/ConfirmationDialog";
import Sidebar, { type SessionMeta } from "@/components/Sidebar";
import SuggestedPrompts from "@/components/SuggestedPrompts";
import {
  sendMessageStream,
  checkHealth,
  getSessionHistory,
  deleteSession as apiDeleteSession,
  syncSessionMessages,
  resolveConfirmation,
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

interface Turn {
  id: string;
  user: Message;
  assistant?: Message;
}

interface ConfirmationData {
  confirmation_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  description: string;
}

function groupIntoTurns(messages: Message[]): Turn[] {
  const turns: Turn[] = [];
  let i = 0;
  while (i < messages.length) {
    const msg = messages[i];
    if (msg.role === "user") {
      const next = messages[i + 1];
      if (next && next.role === "assistant") {
        turns.push({ id: msg.id, user: msg, assistant: next });
        i += 2;
      } else {
        turns.push({ id: msg.id, user: msg });
        i += 1;
      }
    } else {
      i += 1;
    }
  }
  return turns;
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

  // ---- confirmation state ----
  const [confirmation, setConfirmation] = useState<ConfirmationData | null>(null);

  // ---- select mode ----
  const [selectMode, setSelectMode] = useState(false);
  const [selectedTurnIds, setSelectedTurnIds] = useState<Set<string>>(new Set());

  // ---- edit mode ----
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);

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
  }, [messages, agentStatus, confirmation]);

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

  const adjustSessionMessageCount = useCallback(
    (delta: number) => {
      if (!sessionId) return;
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                messageCount: Math.max(0, s.messageCount + delta),
                updatedAt: Date.now(),
              }
            : s
        )
      );
    },
    [sessionId]
  );

  const handleSelectSession = useCallback(
    async (sid: string) => {
      if (sid === sessionId) return;
      if (isStreaming) return;
      setSessionId(sid);
      setSelectMode(false);
      setSelectedTurnIds(new Set());
      setEditingMsgId(null);
      setConfirmation(null);
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
    setSelectMode(false);
    setSelectedTurnIds(new Set());
    setEditingMsgId(null);
    setConfirmation(null);
  }, [isStreaming]);

  const handleDeleteSession = useCallback(
    async (sid: string) => {
      apiDeleteSession(sid).catch(() => {});
      setSessions((prev) => prev.filter((s) => s.id !== sid));
      if (sid === sessionId) {
        setSessionId(undefined);
        setMessages([]);
        setSelectMode(false);
        setSelectedTurnIds(new Set());
        setEditingMsgId(null);
        setConfirmation(null);
      }
    },
    [sessionId]
  );

  // ---- confirmation handlers ----
  const handleConfirmApprove = useCallback(async () => {
    if (!confirmation) return;
    const id = confirmation.confirmation_id;
    setConfirmation(null);
    try {
      await resolveConfirmation(id, true);
    } catch {
      // backend resolve failed -- the timeout will handle it
    }
  }, [confirmation]);

  const handleConfirmReject = useCallback(async () => {
    if (!confirmation) return;
    const id = confirmation.confirmation_id;
    setConfirmation(null);
    try {
      await resolveConfirmation(id, false);
    } catch {
      // backend resolve failed -- the timeout will handle it
    }
  }, [confirmation]);

  // ---- select mode ----
  const handleEnterSelectMode = useCallback(() => {
    if (isStreaming) return;
    setSelectMode(true);
    setSelectedTurnIds(new Set());
  }, [isStreaming]);

  const handleToggleTurn = useCallback((turnId: string) => {
    setSelectedTurnIds((prev) => {
      const next = new Set(prev);
      if (next.has(turnId)) {
        next.delete(turnId);
      } else {
        next.add(turnId);
      }
      return next;
    });
  }, []);

  const handleCancelSelect = useCallback(() => {
    setSelectMode(false);
    setSelectedTurnIds(new Set());
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (selectedTurnIds.size === 0) return;

    const idsToDelete = new Set<string>();
    messages.forEach((m, i) => {
      if (selectedTurnIds.has(m.id)) {
        idsToDelete.add(m.id);
        const next = messages[i + 1];
        if (next && next.role === "assistant") {
          idsToDelete.add(next.id);
        }
      }
    });

    const remaining = messages.filter((m) => !idsToDelete.has(m.id));
    setMessages(remaining);
    adjustSessionMessageCount(-idsToDelete.size);
    setSelectMode(false);
    setSelectedTurnIds(new Set());

    if (sessionId) {
      const remainingTurns = remaining.filter((m) => m.role === "user").length;
      try {
        await syncSessionMessages(
          sessionId,
          remaining.map((m) => ({ role: m.role as "user" | "assistant", content: m.content })),
          remainingTurns
        );
      } catch {
        // backend sync failed; localStorage metadata is still updated
      }
    }
  }, [selectedTurnIds, messages, adjustSessionMessageCount, sessionId]);

  // ---- edit mode ----
  const handleEditStart = useCallback((msgId: string) => {
    if (isStreaming) return;
    setEditingMsgId(msgId);
  }, [isStreaming]);

  const handleEditCancel = useCallback(() => {
    setEditingMsgId(null);
  }, []);

  const handleEditSend = useCallback(
    (userMsgId: string, editedText: string) => {
      if (isStreaming) return;
      setEditingMsgId(null);

      const userIdx = messages.findIndex((m) => m.id === userMsgId);
      if (userIdx < 0) return;

      const nextMsg = messages[userIdx + 1];
      const hasAssistant = nextMsg && nextMsg.role === "assistant";

      setMessages((prev) =>
        prev.map((m) => (m.id === userMsgId ? { ...m, content: editedText } : m))
      );

      let assistantId: string;

      if (hasAssistant) {
        assistantId = nextMsg.id;
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, content: "" } : m))
        );
      } else {
        assistantId = generateId();
        setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "" }]);
        adjustSessionMessageCount(2);
      }

      setIsStreaming(true);
      setAgentStatus({ status: "thinking" });

      const abort = sendMessageStream(editedText, sessionId, {
        onSession: (sid) => {
          setSessionId(sid);
          updateSessionMeta(sid, editedText);
        },
        onStatus: (status) => {
          if (status.status === "confirmation_required") {
            setConfirmation({
              confirmation_id: status.confirmation_id,
              tool_name: status.tool_name,
              tool_args: status.tool_args,
              description: status.description,
            });
            setAgentStatus(status);
          } else {
            setAgentStatus(status);
          }
        },
        onChunk: (token) => {
          setAgentStatus({ status: "generating" });
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
          setConfirmation(null);
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
          setConfirmation(null);
        },
      });

      abortRef.current = abort;
    },
    [isStreaming, sessionId, messages, updateSessionMeta, adjustSessionMessageCount]
  );

  // ---- latest user msg ----
  const latestUserMsgId = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") return messages[i].id;
    }
    return null;
  })();

  // ---- chat ----
  const handleSend = useCallback(
    (text: string) => {
      if (isStreaming) return;
      if (selectMode) {
        setSelectMode(false);
        setSelectedTurnIds(new Set());
      }

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
          if (status.status === "confirmation_required") {
            setConfirmation({
              confirmation_id: status.confirmation_id,
              tool_name: status.tool_name,
              tool_args: status.tool_args,
              description: status.description,
            });
            setAgentStatus(status);
          } else {
            setAgentStatus(status);
          }
        },
        onChunk: (token) => {
          setAgentStatus({ status: "generating" });
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
          setConfirmation(null);
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
          setConfirmation(null);
        },
      });

      abortRef.current = abort;
    },
    [isStreaming, sessionId, updateSessionMeta, selectMode]
  );

  const handleStop = () => {
    abortRef.current?.();
    setIsStreaming(false);
    setAgentStatus(null);
    setConfirmation(null);

    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "assistant" && !last.content) {
        return prev.slice(0, -1);
      }
      return prev;
    });
  };

  // ---- render helpers ----
  const turns = groupIntoTurns(messages);
  const isEmpty = messages.length === 0;

  const renderMessage = (msg: Message, index: number, isLastInList: boolean) => {
    const showStatus = isStreaming && msg.role === "assistant" && isLastInList;
    const isLatestUser = msg.id === latestUserMsgId;
    return (
      <ChatMessage
        key={msg.id}
        role={msg.role}
        content={msg.content}
        isStreaming={showStatus}
        status={showStatus ? agentStatus : null}
        onDelete={handleEnterSelectMode}
        editable={msg.role === "user" && isLatestUser && !isStreaming}
        isEditing={editingMsgId === msg.id}
        onEditStart={() => handleEditStart(msg.id)}
        onEditCancel={handleEditCancel}
        onEditSend={(text) => handleEditSend(msg.id, text)}
        selectMode={selectMode}
      />
    );
  };

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
            title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
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
              {selectMode ? (
                turns.map((turn) => {
                  const selected = selectedTurnIds.has(turn.id);
                  const isLastTurn = turn === turns[turns.length - 1];
                  return (
                    <div
                      key={turn.id}
                      className={`turn-container${selected ? " selected" : ""}`}
                      onClick={() => handleToggleTurn(turn.id)}
                    >
                      <div className="turn-messages">
                        {renderMessage(turn.user, messages.indexOf(turn.user), false)}
                        {turn.assistant && renderMessage(turn.assistant, messages.indexOf(turn.assistant), isLastTurn && !turn.assistant)}
                      </div>
                      <div className="turn-check">
                        <div className={`checkbox${selected ? " checked" : ""}`}>
                          {selected && <Check size={14} />}
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                messages.map((msg, i) => renderMessage(msg, i, i === messages.length - 1))
              )}
            </div>
          )}
        </main>

        <ChatInput
          onSend={handleSend}
          disabled={isStreaming}
          onStop={handleStop}
        />
      </div>

      {selectMode && (
        <div className="select-float-bar">
          <button
            className="select-cancel-btn"
            onClick={handleCancelSelect}
            title="Cancel"
          >
            <X size={16} />
            <span>Cancel</span>
          </button>
          <button
            className="select-delete-btn"
            onClick={handleConfirmDelete}
            disabled={selectedTurnIds.size === 0}
            title="Delete"
          >
            <Trash2 size={16} />
            <span>Delete ({selectedTurnIds.size})</span>
          </button>
        </div>
      )}

      {confirmation && (
        <ConfirmationDialog
          data={confirmation}
          onApprove={handleConfirmApprove}
          onReject={handleConfirmReject}
        />
      )}
    </div>
  );
}