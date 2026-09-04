/**
 * SessionManager - 会话级状态管理器
 *
 * 核心职责：
 * 1. 会话实例生命周期管理（创建/销毁/切换）
 * 2. 发布订阅机制驱动 React 精确重渲染
 * 3. 后台会话静默接收数据，前台会话实时渲染
 * 4. 会话级 AbortController 管理
 */

import type { AgentStatus } from './api';

// ---- 类型定义 ----

export type SessionStatus =
  | 'idle'
  | 'streaming'
  | 'tool_calling'
  | 'waiting_confirm'
  | 'error'
  | 'done';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export interface ConfirmationData {
  confirmation_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  description: string;
}

export interface SessionInstance {
  id: string;
  status: SessionStatus;
  abortController: AbortController | null;
  messageBuffer: Message[];
  agentStatus: AgentStatus | null;
  confirmation: ConfirmationData | null;
  isForeground: boolean;
  lastActivity: number;
  title?: string;
  isNew?: boolean;  // 标记是否是新会话（用于标题生成）
}

export type ChangeType = 'chunk' | 'status' | 'confirmation' | 'done' | 'error';
export type SessionChangeCallback = (sessionId: string, changeType: ChangeType) => void;

// ---- SessionManager 类 ----

export class SessionManager {
  private sessions = new Map<string, SessionInstance>();
  private activeSessionId: string | undefined;
  private subscribers = new Set<SessionChangeCallback>();

  // ======== 发布订阅机制 ========

  subscribe(cb: SessionChangeCallback): () => void {
    this.subscribers.add(cb);
    return () => {
      this.subscribers.delete(cb);
    };
  }

  private notify(sessionId: string, changeType: ChangeType): void {
    for (const cb of this.subscribers) {
      try {
        cb(sessionId, changeType);
      } catch (err) {
        console.error('[SessionManager] Subscriber error:', err);
      }
    }
  }

  // ======== 会话生命周期管理 ========

  getOrCreate(sessionId: string): SessionInstance {
    let session = this.sessions.get(sessionId);
    if (!session) {
      session = {
        id: sessionId,
        status: 'idle',
        abortController: null,
        messageBuffer: [],
        agentStatus: null,
        confirmation: null,
        isForeground: false,
        lastActivity: Date.now(),
      };
      this.sessions.set(sessionId, session);
    }
    return session;
  }

  switchTo(sessionId: string): SessionInstance {
    const target = this.getOrCreate(sessionId);

    // 如果已经是当前活跃会话，直接返回
    if (this.activeSessionId === sessionId) {
      return target;
    }

    // 旧会话置为后台
    if (this.activeSessionId) {
      const old = this.sessions.get(this.activeSessionId);
      if (old) {
        old.isForeground = false;
      }
    }

    // 新会话置为前台
    target.isForeground = true;
    this.activeSessionId = sessionId;

    return target;
  }

  getForeground(): SessionInstance | undefined {
    return this.activeSessionId
      ? this.sessions.get(this.activeSessionId)
      : undefined;
  }

  get(sessionId: string): SessionInstance | undefined {
    return this.sessions.get(sessionId);
  }

  getActiveSessionId(): string | undefined {
    return this.activeSessionId;
  }

  getAll(): SessionInstance[] {
    return Array.from(this.sessions.values());
  }

  // ======== ID 映射（临时ID -> 服务端真实ID）========

  renameId(oldId: string, newId: string): void {
    const session = this.sessions.get(oldId);
    if (!session) return;

    // 更新实例 ID
    session.id = newId;

    // 更新 Map
    this.sessions.delete(oldId);
    this.sessions.set(newId, session);

    // 更新活跃会话 ID
    if (this.activeSessionId === oldId) {
      this.activeSessionId = newId;
    }

    // 通知订阅者 ID 变更
    this.notify(newId, 'status');
  }

  // ======== 数据更新方法（触发通知）========

  appendChunk(sessionId: string, chunk: string): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    // 聚合逻辑：追加到最后一条 assistant 消息，避免碎片化
    const lastMsg = session.messageBuffer[session.messageBuffer.length - 1];

    if (!lastMsg || lastMsg.role !== 'assistant') {
      // 如果最后一条不是 assistant 消息，新建一条
      session.messageBuffer.push({
        id: `${sessionId}-${Date.now()}`,
        role: 'assistant',
        content: chunk,
      });
    } else {
      // 否则追加到已有 assistant 消息的 content 末尾
      lastMsg.content += chunk;
    }

    session.lastActivity = Date.now();
    this.notify(sessionId, 'chunk');
  }

  updateStatus(sessionId: string, status: AgentStatus): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    session.agentStatus = status;
    session.lastActivity = Date.now();

    // 更新会话状态
    switch (status.status) {
      case 'tool_start':
      case 'tool_end':
        session.status = 'tool_calling';
        break;
      case 'confirmation_required':
        session.status = 'waiting_confirm';
        session.confirmation = {
          confirmation_id: status.confirmation_id,
          tool_name: status.tool_name,
          tool_args: status.tool_args,
          description: status.description,
        };
        break;
      case 'confirmation_expired':
        session.status = 'streaming';
        session.confirmation = null;
        break;
      case 'thinking':
      case 'generating':
        session.status = 'streaming';
        break;
    }

    this.notify(sessionId, 'status');
  }

  markDone(sessionId: string): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    session.status = 'done';
    session.abortController = null;
    session.lastActivity = Date.now();
    this.notify(sessionId, 'done');
  }

  markError(sessionId: string, error: string): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    session.status = 'error';
    session.abortController = null;
    session.lastActivity = Date.now();
    console.error(`[SessionManager] Session ${sessionId} error:`, error);
    this.notify(sessionId, 'error');
  }

  resolveConfirmation(sessionId: string): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    session.confirmation = null;
    session.status = 'streaming';
    this.notify(sessionId, 'confirmation');
  }

  addMessage(sessionId: string, message: Message): void {
    const session = this.getOrCreate(sessionId);
    session.messageBuffer.push(message);
    session.lastActivity = Date.now();
    this.notify(sessionId, 'chunk');
  }

  replaceMessages(sessionId: string, messages: Message[]): void {
    const session = this.getOrCreate(sessionId);
    session.messageBuffer = messages;
    session.lastActivity = Date.now();
    this.notify(sessionId, 'chunk');
  }

  clearMessages(sessionId: string): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    session.messageBuffer = [];
    this.notify(sessionId, 'chunk');
  }

  // ======== 生命周期管理 ========

  abort(sessionId: string): void {
    const session = this.sessions.get(sessionId);
    if (!session) return;

    if (session.abortController) {
      session.abortController.abort();
      session.abortController = null;
    }

    session.status = 'idle';
    session.agentStatus = null;
    session.confirmation = null;
  }

  destroy(sessionId: string): void {
    this.abort(sessionId);
    this.sessions.delete(sessionId);

    if (this.activeSessionId === sessionId) {
      this.activeSessionId = undefined;
    }
  }

  abortAll(): void {
    for (const [id] of this.sessions) {
      this.abort(id);
    }
  }

  // ======== 持久化支持 ========

  getDirtySessions(): SessionInstance[] {
    // 返回有消息但未持久化的会话
    // TODO: 实现增量持久化标记
    return Array.from(this.sessions.values()).filter(
      (s) => s.messageBuffer.length > 0 && (s.status === 'streaming' || s.status === 'tool_calling')
    );
  }

  // ======== 统计信息 ========

  getActiveCount(): number {
    let count = 0;
    for (const session of this.sessions.values()) {
      if (['streaming', 'tool_calling', 'waiting_confirm'].includes(session.status)) {
        count++;
      }
    }
    return count;
  }

  isStreaming(sessionId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session) return false;
    return ['streaming', 'tool_calling', 'waiting_confirm'].includes(session.status);
  }

  // ======== 清理 ========

  destroyAll(): void {
    this.abortAll();
    this.sessions.clear();
    this.activeSessionId = undefined;
    this.subscribers.clear();
  }
}
