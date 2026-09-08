import { useState, useRef, useEffect, useCallback } from "react";
import { X, Trash2, Check, Minus, Square, Copy, Folder, PanelLeft } from "lucide-react";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";
import ConfirmationDialog from "@/components/ConfirmationDialog";
import ContextIndicator from "@/components/ContextIndicator";
import SettingsPanel, {
  type ContextSettings,
  loadContextSettings,
  saveContextSettings,
} from "@/components/SettingsPanel";
import ContextSettingsPanel from "@/components/ContextSettingsPanel";
import Sidebar, { type SessionMeta } from "@/components/Sidebar";
import SuggestedPrompts from "@/components/SuggestedPrompts";
import {
  sendMessageStreamWithSession,
  checkHealth,
  getSessionHistory,
  deleteSession as apiDeleteSession,
  syncSessionMessages,
  resolveConfirmation,
  listSessions,
  listProjects,
  listProvidersData,
  createProject as apiCreateProject,
  generateSessionTitle,
  updateSessionTitle,
  initApiBase,
  API_BASE,
} from "@/lib/api";
import { SessionManager } from "@/lib/session-manager";

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
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [expandHovered, setExpandHovered] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // SessionManager - 会话级状态管理
  const sessionManagerRef = useRef<SessionManager>(new SessionManager());

  // 简单的流式状态：只要在等待输出就为 true
  const [isStreaming, setIsStreaming] = useState(false);
  // 确认状态
  const [confirmation, setConfirmation] = useState<ConfirmationData | null>(null);

  // 流式渲染优化：使用 rAF 批量更新
  const pendingUpdateRef = useRef<boolean>(false);
  const rafIdRef = useRef<number | null>(null);

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

  // ---- context management state ----
  const [contextSettings, setContextSettings] = useState<ContextSettings>(loadContextSettings);
  const [modelSettingsOpen, setModelSettingsOpen] = useState(false);
  const [contextSettingsOpen, setContextSettingsOpen] = useState(false);
  const [contextStats, setContextStats] = useState<{
    totalTokens: number;
    maxTokens: number;
    usagePercent: number;
  } | null>(null);
  const [isCompressing, setIsCompressing] = useState(false);
  const [compressionResult, setCompressionResult] = useState<{ freedPercent: number } | null>(null);
  const [activeModelContextWindow, setActiveModelContextWindow] = useState(0);

  // 持久化设置变更
  const handleContextSettingsChange = useCallback((newSettings: ContextSettings) => {
    setContextSettings(newSettings);
    saveContextSettings(newSettings);
  }, []);

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

      // 加载活跃模型的 context_window
      listProvidersData().then((data) => {
        for (const p of data.providers) {
          if (p.is_active) {
            for (const m of p.models) {
              if (m.id === data.active_model_id) {
                setActiveModelContextWindow(m.context_window);
                return;
              }
            }
            if (p.models.length > 0) {
              setActiveModelContextWindow(p.models[0].context_window);
            }
          }
        }
      }).catch(() => {});

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

  // ---- 发布订阅：监听前台会话变更，精确控制重渲染 ----
  useEffect(() => {
    const sessionManager = sessionManagerRef.current;

    const unsubscribe = sessionManager.subscribe((changedSid, changeType) => {
      const foreground = sessionManager.getForeground();

      // 只有当前台会话发生变更时，才触发 App 重渲染
      if (foreground && changedSid === foreground.id) {
        // chunk 和 status 变更频率高，使用 requestAnimationFrame 节流
        if (changeType === 'chunk' || changeType === 'status') {
          requestAnimationFrame(() => setRenderTrigger((n) => n + 1));
        } else {
          // confirmation/done/error 立即触发
          setRenderTrigger((n) => n + 1);
        }
      }
      // 后台会话变更只通知 Sidebar（Sidebar 内部自行订阅处理）
    });

    return unsubscribe;
  }, []);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, confirmation, isStreaming]);

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
            projectId: r.project_id || undefined,  // 映射项目ID
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

        // 标记会话是否是新创建的（用于标题生成）
        if (isNew) {
          const session = sessionManagerRef.current.get(sid);
          if (session) session.isNew = true;
        }

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

      const sessionManager = sessionManagerRef.current;
      sessionManager.switchTo(sid);

      // 先清空消息，避免显示旧会话的内容
      setMessages([]);
      setSessionId(sid);
      setSelectMode(false);
      setSelectedTurnIds(new Set());
      setEditingMsgId(null);
      setConfirmation(null);
      setContextStats(null);
      setIsCompressing(false);
      setCompressionResult(null);

      // 优先使用 buffer，否则从数据库加载
      const session = sessionManager.get(sid);
      if (session && session.messageBuffer.length > 0) {
        setMessages(session.messageBuffer);
      } else {
        try {
          const history = await getSessionHistory(sid);
          const msgs = history.messages.map((m, i) => ({
            id: `${sid}-${i}`,
            role: m.role as "user" | "assistant",
            content: m.content,
          }));
          sessionManager.replaceMessages(sid, msgs);
          setMessages(msgs);
        } catch {
          // 保持空消息
        }
      }
    },
    [sessionId]
  );

  const handleNewSession = useCallback(() => {
    // 移除 isStreaming 阻塞！允许在流式输出时创建新会话
    setSessionId(undefined);
    setMessages([]);
    setSelectMode(false);
    setSelectedTurnIds(new Set());
    setEditingMsgId(null);
    setConfirmation(null);
    setContextStats(null);
    setIsCompressing(false);
    setCompressionResult(null);
  }, []);

  const handleNewSessionInProject = useCallback((projectId: string) => {
    // 移除 isStreaming 阻塞！
    // 设置当前项目为活跃项目
    setActiveProjectId(projectId);
    // 清空当前会话，开始新对话
    setSessionId(undefined);
    setMessages([]);
    setSelectMode(false);
    setSelectedTurnIds(new Set());
    setEditingMsgId(null);
    setConfirmation(null);
    setContextStats(null);
    setIsCompressing(false);
    setCompressionResult(null);
  }, []);

  const handleDeleteSession = useCallback(
    async (sid: string) => {
      const sessionManager = sessionManagerRef.current;
      sessionManager.destroy(sid);  // 中止流 + 清理内存

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
    // 移除 isStreaming 阻塞
    setSelectMode(true);
    setSelectedTurnIds(new Set());
  }, []);

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
    // 移除 isStreaming 阻塞
    setEditingMsgId(msgId);
  }, []);

  const handleEditCancel = useCallback(() => {
    setEditingMsgId(null);
  }, []);

  const handleEditSend = useCallback(
    (userMsgId: string, editedText: string) => {
      // 移除全局 isStreaming 检查，改为会话级检查
      const sessionManager = sessionManagerRef.current;
      const currentSessionId = sessionId || `temp-${generateId()}`;
      const session = sessionManager.getOrCreate(currentSessionId);

      // 会话级检查：只有当前会话在 streaming 时才阻塞
      if (session.status === 'streaming' || session.status === 'tool_calling') {
        return;
      }

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

      // 设置流式状态
      setIsStreaming(true);

      // 如果是新会话，立即设置 sessionId
      if (!sessionId) {
        setSessionId(currentSessionId);
      }

      // 使用新版 sendMessageStreamWithSession
      const controller = sendMessageStreamWithSession(editedText, session, {
        onSession: (sid) => {
          // 处理 ID 映射
          if (currentSessionId !== sid) {
            sessionManager.renameId(currentSessionId, sid);
            setSessionId(sid);
          }
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
          } else if (status.status === "confirmation_expired") {
            setConfirmation(null);
          } else if (status.status === "context_stats") {
            setContextStats({
              totalTokens: status.total_tokens,
              maxTokens: status.max_tokens,
              usagePercent: status.usage_percent,
            });
          } else if (status.status === "compressing") {
            setIsCompressing(true);
            setCompressionResult(null);
          } else if (status.status === "compressed") {
            setIsCompressing(false);
            setCompressionResult({ freedPercent: status.freed_percent });
          } else if (status.status === "usage") {
            setContextStats((prev) => prev ? {
              ...prev,
              totalTokens: status.prompt_tokens,
              usagePercent: prev.maxTokens > 0
                ? Math.round((status.prompt_tokens / (prev.maxTokens - 4096)) * 10000) / 100
                : 0,
            } : prev);
          }
        },
        onChunk: (token) => {
          sessionManager.appendChunk(session.id, token);

          // 使用 rAF 批量更新
          pendingUpdateRef.current = true;
          if (!rafIdRef.current) {
            rafIdRef.current = requestAnimationFrame(() => {
              rafIdRef.current = null;
              if (pendingUpdateRef.current && session.messageBuffer.length > 0) {
                if (session.isForeground) {
                  setMessages([...session.messageBuffer]);
                }
                pendingUpdateRef.current = false;
              }
            });
          }
        },
        onDone: (fullContent, doneSessionId) => {
          sessionManager.markDone(doneSessionId);
          setIsStreaming(false);
          setConfirmation(null);

          // 同步更新 React messages 状态
          if (session.messageBuffer.length > 0) {
            setMessages([...session.messageBuffer]);
          }

          // Auto-generate title after first reply（使用 session.isNew 替代全局 ref）
          if (session.isNew) {
            session.isNew = false;
            const tempTitle = editedText.slice(0, 20);
            updateSessionTitle(doneSessionId, tempTitle).catch(() => {});
            generateSessionTitle(doneSessionId, editedText, fullContent)
              .then((res) => {
                if (res.title) {
                  session.title = res.title;
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
          sessionManager.markError(session.id, err);
          setIsStreaming(false);
          setConfirmation(null);
          session.isNew = false;
        },
      }, confirmationMode, undefined, contextSettings.threshold, contextSettings.keepRecentTurns, activeModelContextWindow);

      // 更新 sessionId
      if (!sessionId) setSessionId(currentSessionId);
    },
    [sessionId, messages, updateSessionMeta, adjustSessionMessageCount, confirmationMode, contextSettings, activeModelContextWindow]
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
      const sessionManager = sessionManagerRef.current;
      const currentSessionId = sessionId || `temp-${generateId()}`;
      const session = sessionManager.getOrCreate(currentSessionId);

      // 会话级检查：只有当前会话在 streaming 时才阻塞
      if (session.status === 'streaming' || session.status === 'tool_calling') {
        return;
      }

      if (selectMode) {
        setSelectMode(false);
        setSelectedTurnIds(new Set());
      }

      const userId = generateId();
      const assistantId = generateId();

      // 创建消息并添加到会话 buffer
      const userMsg = { id: userId, role: "user" as const, content: text };
      const assistantMsg = { id: assistantId, role: "assistant" as const, content: "" };

      sessionManager.addMessage(currentSessionId, userMsg);
      sessionManager.addMessage(currentSessionId, assistantMsg);

      // 设置流式状态
      setIsStreaming(true);

      // 如果是新会话，立即设置 sessionId
      if (!sessionId) {
        setSessionId(currentSessionId);
      }

      // 更新 React 状态
      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      // 使用新版 sendMessageStreamWithSession
      const controller = sendMessageStreamWithSession(text, session, {
        onSession: (sid) => {
          // 处理 ID 映射：临时ID -> 服务端真实ID
          if (currentSessionId !== sid) {
            sessionManager.renameId(currentSessionId, sid);
            setSessionId(sid);
          }
          updateSessionMeta(sid, text);
        },
        onStatus: (status) => {
          // 处理确认状态
          if (status.status === "confirmation_required") {
            setConfirmation({
              confirmation_id: status.confirmation_id,
              tool_name: status.tool_name,
              tool_args: status.tool_args,
              description: status.description,
            });
          } else if (status.status === "confirmation_expired") {
            setConfirmation(null);
          } else if (status.status === "context_stats") {
            setContextStats({
              totalTokens: status.total_tokens,
              maxTokens: status.max_tokens,
              usagePercent: status.usage_percent,
            });
          } else if (status.status === "compressing") {
            setIsCompressing(true);
            setCompressionResult(null);
          } else if (status.status === "compressed") {
            setIsCompressing(false);
            setCompressionResult({ freedPercent: status.freed_percent });
          } else if (status.status === "usage") {
            setContextStats((prev) => prev ? {
              ...prev,
              totalTokens: status.prompt_tokens,
              usagePercent: prev.maxTokens > 0
                ? Math.round((status.prompt_tokens / (prev.maxTokens - 4096)) * 10000) / 100
                : 0,
            } : prev);
          }
        },
        onChunk: (token) => {
          // 追加 chunk 到会话 buffer
          sessionManager.appendChunk(session.id, token);

          // 使用 rAF 批量更新，避免频繁重渲染
          pendingUpdateRef.current = true;
          if (!rafIdRef.current) {
            rafIdRef.current = requestAnimationFrame(() => {
              rafIdRef.current = null;
              if (pendingUpdateRef.current && session.messageBuffer.length > 0) {
                // 只有当前会话才更新 React 状态
                if (session.isForeground) {
                  setMessages([...session.messageBuffer]);
                }
                pendingUpdateRef.current = false;
              }
            });
          }
        },
        onDone: (fullContent, doneSessionId) => {
          sessionManager.markDone(doneSessionId);
          setIsStreaming(false);
          setConfirmation(null);

          // 同步更新 React messages 状态
          if (session.messageBuffer.length > 0) {
            setMessages([...session.messageBuffer]);
          }

          // Auto-generate title after first reply（使用 session.isNew 替代全局 ref）
          if (session.isNew) {
            session.isNew = false;

            // 1. 先异步存储临时标题到数据库
            const tempTitle = text.slice(0, 20);
            updateSessionTitle(doneSessionId, tempTitle).catch(() => {});

            // 2. 调用小模型生成正式标题
            generateSessionTitle(doneSessionId, text, fullContent)
              .then((res) => {
                if (res.title) {
                  session.title = res.title;
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
          sessionManager.markError(currentSessionId, err);
          setIsStreaming(false);
          setConfirmation(null);
          session.isNew = false;
        },
      }, confirmationMode, activeProjectId, contextSettings.threshold, contextSettings.keepRecentTurns, activeModelContextWindow);

      // 更新 sessionId
      if (!sessionId) setSessionId(currentSessionId);
    },
    [sessionId, updateSessionMeta, selectMode, confirmationMode, activeProjectId, contextSettings, activeModelContextWindow]
  );

  const handleStop = () => {
    const sessionManager = sessionManagerRef.current;
    if (sessionId) {
      sessionManager.abort(sessionId);
    }
    setIsStreaming(false);
    setConfirmation(null);

    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "assistant" && !last.content) {
        return prev.slice(0, -1);
      }
      return prev;
    });
  };

  // ---- 当前是否在流式输出 ----
  const isCurrentStreaming = isStreaming;

  // ---- render helpers ----
  const turns = groupIntoTurns(messages);
  const isEmpty = messages.length === 0;

  const renderMessage = (msg: Message, _index: number, isLastInList: boolean) => {
    const showStatus = isCurrentStreaming && msg.role === "assistant" && isLastInList;
    const isLatestUser = msg.id === latestUserMsgId;
    return (
      <ChatMessage
        key={msg.id}
        role={msg.role}
        content={msg.content}
        isStreaming={showStatus}
        onDelete={handleEnterSelectMode}
        editable={msg.role === "user" && isLatestUser && !isCurrentStreaming}
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
          sessionManager={sessionManagerRef.current}
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
          <>
            {contextStats && messages.length > 0 && (
              <ContextIndicator
                totalTokens={contextStats.totalTokens}
                maxTokens={contextStats.maxTokens}
                usagePercent={contextStats.usagePercent}
                isCompressing={isCompressing}
                compressionResult={compressionResult}
              />
            )}
            <ChatInput
              onSend={handleSend}
              disabled={isCurrentStreaming}
              onStop={handleStop}
              mode={confirmationMode}
              onModeChange={setConfirmationMode}
              isEmpty={isEmpty}
              onOpenModelSettings={() => setModelSettingsOpen(true)}
              onOpenContextSettings={() => setContextSettingsOpen(true)}
            />
          </>
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

      <SettingsPanel
        isOpen={modelSettingsOpen}
        onClose={() => setModelSettingsOpen(false)}
      />

      <ContextSettingsPanel
        isOpen={contextSettingsOpen}
        onClose={() => setContextSettingsOpen(false)}
        settings={contextSettings}
        onChange={handleContextSettingsChange}
      />
    </div>
  );
}
