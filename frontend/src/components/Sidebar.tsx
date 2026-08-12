"use client";

import { MessageSquarePlus, Trash2, MessageCircle, Wifi, WifiOff } from "lucide-react";

export interface SessionMeta {
  id: string;
  title: string;
  updatedAt: number;
  messageCount: number;
}

interface Props {
  sessions: SessionMeta[];
  activeSessionId: string | undefined;
  isConnected: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({
  sessions,
  activeSessionId,
  isConnected,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <aside className="sidebar">
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="sidebar-brand-icon">C</span>
          <span className="sidebar-brand-text">Coco</span>
        </div>
        <button onClick={onNew} className="sidebar-new-btn" title="新建对话">
          <MessageSquarePlus size={18} />
        </button>
      </div>

      {/* Session list */}
      <div className="sidebar-sessions">
        {sessions.length === 0 ? (
          <div className="sidebar-empty">暂无对话</div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.id}
              className={`sidebar-session ${s.id === activeSessionId ? "active" : ""}`}
              onClick={() => onSelect(s.id)}
            >
              <MessageCircle size={14} className="sidebar-session-icon" />
              <div className="sidebar-session-info">
                <span className="sidebar-session-title">{s.title}</span>
                <span className="sidebar-session-meta">{s.messageCount} 条消息</span>
              </div>
              <button
                className="sidebar-session-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(s.id);
                }}
                title="删除对话"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Footer - connection status */}
      <div className="sidebar-footer">
        <div className={`sidebar-status ${isConnected ? "connected" : "disconnected"}`}>
          {isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
          <span>{isConnected ? "已连接" : "未连接"}</span>
        </div>
      </div>
    </aside>
  );
}
