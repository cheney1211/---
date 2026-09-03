import { useState, useRef, useEffect, useCallback } from "react";
import { X, Trash2, Check, Minus, Square, Copy, Folder, PanelLeft } from "lucide-react";
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
  listSessions,
  listProjects,
  createProject as apiCreateProject,
  generateSessionTitle,
  updateSessionTitle,
  type AgentStatus,
  initApiBase,
  API_BASE,
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

type ConfirmationMode = "confirm" | "plan" | "full_access";

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

function saveSessions(sessions: SessionMeta[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

// ---- App ----
export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [expandHovered, setExpandHovered] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<(() => void) | null>(null);
  const isNewSessionRef = useRef(false);

  // ---- confirmation state ----
  const [confirmation, setConfirmation] = useState<ConfirmationData | null>(null);

  // ---- select mode ----
  const [selectMode, setSelectMode] = useState(false);
  const [selectedTurnIds, setSelectedTurnIds] = useState<Set<string>>(new Set());

  // ---- edit mode ----
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);

  // ---- confirmation mode ----
  const [confirmationMode, setConfirmationMode] = useState<ConfirmationMode>("confirm");

  // ---- window state ----
  const [isMaximized, setIsMaximized] = useState(false);

  // ---- project state ----
  const [projects, setProjects] = useState<{ id: string; name: string; root_path: string | null }[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | undefined>();

  // ---- init ----
  useEffect(() => {
    // 全局错误处理
    const handleError = (event: ErrorEvent) => {
      console.error('[App] Unhandled error:', event.error);
    };
    const handleRejection = (event: PromiseRejectionEvent) => {
      console.error('[App] Unhandled promise rejection:', event.reason);
    };
    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleRejection);

    // 初始化 API 基础地址
    initApiBase().then(() => {
      console.log('[App] API initialized');
      checkHealth().then(setIsConnected);
      const timer = setInterval(() => checkHealth().then(setIsConnected), 30000);

      // 加载项目列表
      loadProjects();

      // 加载会话列表
      loadSessions();

      // 初始化窗口最大化状态
      if (window.electronAPI) {
        window.electronAPI.isMaximized().then(setIsMaximized);
      }

      return () => clearInterval(timer);
    }).catch((error) => {
      console.error('[App] Failed to initialize API:', error);
    });

    return () => {
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleRejection);
    };
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
  const loadSessions = useCallback(() => {
    listSessions()
      .then((remote) => {
        setSessions(
          remote.map((r) => ({
            id: r.id,
            title: r.title || r.id.slice(0, 8),  // 如果没有标题，使用session id前8位
            updatedAt: r.updated_at ? new Date(r.updated_at).getTime() : Date.now(),
            messageCount: r.turns * 2,
          }))
        );
      })
      .catch(() => {});
  }, []);

  // ---- project helpers ----
  const loadProjects = useCallback(() => {
    listProjects()
      .then((remote) => {
        setProjects(remote.map((r) => ({
          id: r.id,
          name: r.name,
          root_path: r.root_path || null,
        })));
      })
      .catch(() => {});
  }, []);

  const handleOpenFolder = useCallback(async () => {
    try {
      const result = await window.electronAPI?.selectFolder();
      if (result && !result.canceled && result.filePaths.length > 0) {
        const folderPath = result.filePaths[0];
        const folderName = folderPath.split(/[\\/]/).pop() || '新项目';

        // 创建项目
        const project = await apiCreateProject(folderName);

        // 设置项目的根路径
        await fetch(`${API_BASE}/projects/${project.id}/root-path`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ root_path: folderPath }),
        });

        // 重新加载项目列表
        loadProjects();
      }
    } catch (err) {
      console.error('添加项目失败:', err);
    }
  }, [loadProjects]);

  const handleSelectProject = useCallback((_projectId: string) => {
    // 项目选择逻辑
  }, []);

  // ---- session helpers ----
  const updateSessionMeta = useCallback(
    (sid: string, userMsg: string) => {
      setSessions((prev) => {
        const idx = prev.findIndex((s) => s.id === sid);
        const isNew = idx < 0;
        const tempTitle = userMsg.slice(0, 20);  // 临时标题：截取前20字
        const meta: SessionMeta =
          idx >= 0
            ? {
                ...prev[idx],
                title: prev[idx].title || tempTitle,  // 如果没有标题，使用临时标题
                messageCount: prev[idx].messageCount + 2,
                updatedAt: Date.now(),
              }
            : {
                id: sid,
                title: tempTitle,
                updatedAt: Date.now(),
                messageCount: 2,
                projectId: activeProjectId,  // 关联到当前活跃项目
              };
        const next = [...prev];
        if (idx >= 0) next[idx] = meta;
        else next.unshift(meta);
        isNewSessionRef.current = isNew;
        return next;
      });
    },
    [activeProjectId]
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

  const handleNewSessionInProject = useCallback((projectId: string) => {
    if (isStreaming) return;
    // 设置当前项目为活跃项目
    setActiveProjectId(projectId);
    // 清空当前会话，开始新对话
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

  const handleRenameSession = useCallback(
    async (sid: string, newTitle: string) => {
      setSessions((prev) =>
        prev.map((s) => (s.id === sid ? { ...s, title: newTitle } : s))
      );
      updateSessionTitle(sid, newTitle).catch(() => {});
    },
    []
  );

  // ---- confirmation handlers ----
  const handleConfirmApprove = useCallback(async (allowAlways?: boolean) => {
    if (!confirmation) return;
    const id = confirmation.confirmation_id;
    setConfirmation(null);
    try {
      await resolveConfirmation(id, true, allowAlways);
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

  const handleConfirmExpire = useCallback(() => {
    setConfirmation(null);
  }, []);

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
          } else if (status.status === "confirmation_expired") {
            setConfirmation(null);
            setAgentStatus(null);
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
        onDone: (fullContent, doneSessionId) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: fullContent } : m
            )
          );
          setIsStreaming(false);
          setConfirmation(null);

          // Auto-generate title after first reply
          if (isNewSessionRef.current) {
            isNewSessionRef.current = false;

            // 1. 先异步存储临时标题到数据库
            const tempTitle = editedText.slice(0, 20);
            updateSessionTitle(doneSessionId, tempTitle).catch(() => {});

            // 2. 调用小模型生成正式标题
            generateSessionTitle(doneSessionId, editedText, fullContent)
              .then((res) => {
                if (res.title) {
                  // 3. 生成成功后，静默覆盖临时标题
                  setSessions((prev) =>
                    prev.map((s) =>
                      s.id === doneSessionId ? { ...s, title: res.title! } : s
                    )
                  );
                }
              })
              .catch(() => {});
          }
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
          isNewSessionRef.current = false;
        },
      }, confirmationMode);

      abortRef.current = abort;
    },
    [isStreaming, sessionId, messages, updateSessionMeta, adjustSessionMessageCount, setConfirmation, confirmationMode]
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
          } else if (status.status === "confirmation_expired") {
            setConfirmation(null);
            setAgentStatus(null);
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
        onDone: (fullContent, doneSessionId) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: fullContent } : m
            )
          );
          setIsStreaming(false);
          setConfirmation(null);

          // Auto-generate title after first reply
          if (isNewSessionRef.current) {
            isNewSessionRef.current = false;

            // 1. 先异步存储临时标题到数据库
            const tempTitle = text.slice(0, 20);
            updateSessionTitle(doneSessionId, tempTitle).catch(() => {});

            // 2. 调用小模型生成正式标题（使用 TITLE_PROVIDER/TITLE_MODEL 环境变量配置）
            generateSessionTitle(doneSessionId, text, fullContent)
              .then((res) => {
                if (res.title) {
                  // 3. 生成成功后，静默覆盖临时标题（前端状态 + 数据库）
                  setSessions((prev) =>
                    prev.map((s) =>
                      s.id === doneSessionId ? { ...s, title: res.title! } : s
                    )
                  );
                  // 数据库已在 generateSessionTitle API 中更新
                }
              })
              .catch(() => {});
          }
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
            isNewSessionRef.current = false;
        },
      }, confirmationMode, activeProjectId);

      abortRef.current = abort;
    },
    [isStreaming, sessionId, updateSessionMeta, selectMode, confirmationMode, activeProjectId]
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

  const renderMessage = (msg: Message, _index: number, isLastInList: boolean) => {
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

  // Only show window controls on Windows/Linux (macOS uses native traffic lights)
  const showWindowControls = typeof window !== 'undefined' && window.electronAPI && !navigator.platform.includes('Mac');

  return (
    <div className="app-layout">
      <div className={`sidebar-wrapper${sidebarOpen ? ' open' : ''}`}>
        <Sidebar
          projects={projects}
          sessions={sessions}
          activeSessionId={sessionId}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen((v) => !v)}
          onOpenFolder={handleOpenFolder}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
          onNewInProject={handleNewSessionInProject}
          onDelete={handleDeleteSession}
          onRename={handleRenameSession}
          onSelectProject={handleSelectProject}
        />
      </div>

      <div className="main-area">
        <header className="main-header">
          <div className="main-header-left">
            {!sidebarOpen && (
              <button
                className={`sidebar-expand-btn${expandHovered ? ' hovered' : ''}`}
                onClick={() => setSidebarOpen(true)}
                onMouseEnter={() => setExpandHovered(true)}
                onMouseLeave={() => setExpandHovered(false)}
                title="展开侧边栏"
              >
                {expandHovered ? (
                  <PanelLeft size={22} className="sidebar-expand-icon" />
                ) : (
                  <img src="/logo.png" alt="Coco" className="sidebar-expand-icon" />
                )}
              </button>
            )}
            {activeProjectId && projects.find(p => p.id === activeProjectId) ? (
              <div className="main-header-project">
                <Folder size={14} />
                <span>{projects.find(p => p.id === activeProjectId)?.name}</span>
              </div>
            ) : null}
            <div className={`header-status-dot ${isConnected ? "connected" : ""}`} />
          </div>

          {showWindowControls && (
            <div className="window-controls">
              <button
                className="window-control-btn minimize"
                onClick={() => window.electronAPI?.minimizeWindow()}
                title="最小化"
              >
                <Minus size={14} />
              </button>
              <button
                className="window-control-btn maximize"
                onClick={() => {
                  window.electronAPI?.maximizeWindow();
                  setIsMaximized((v) => !v);
                }}
                title={isMaximized ? "还原" : "最大化"}
              >
                {isMaximized ? <Copy size={12} /> : <Square size={12} />}
              </button>
              <button
                className="window-control-btn close"
                onClick={() => window.electronAPI?.closeWindow()}
                title="关闭"
              >
                <X size={14} />
              </button>
            </div>
          )}
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

        {confirmation ? (
          <ConfirmationDialog
            data={confirmation}
            onApprove={handleConfirmApprove}
            onReject={handleConfirmReject}
            onExpire={handleConfirmExpire}
          />
        ) : (
          <ChatInput
            onSend={handleSend}
            disabled={isStreaming}
            onStop={handleStop}
            mode={confirmationMode}
            onModeChange={setConfirmationMode}
            isEmpty={isEmpty}
          />
        )}
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
    </div>
  );
}
