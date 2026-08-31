"use client";

import { useState, useRef, useEffect } from "react";
import { MessageSquarePlus, MessageCircle, Wifi, WifiOff, MoreHorizontal, Pencil, Trash2 } from "lucide-react";

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
  onRename: (id: string, newTitle: string) => void;
}

export default function Sidebar({
  sessions,
  activeSessionId,
  isConnected,
  onSelect,
  onNew,
  onDelete,
  onRename,
}: Props) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!openMenuId) return;
    const handle = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [openMenuId]);

  // Focus rename input when entering rename mode
  useEffect(() => {
    if (renamingId) {
      renameInputRef.current?.focus();
      renameInputRef.current?.select();
    }
  }, [renamingId]);

  const handleStartRename = (id: string, currentTitle: string) => {
    setRenamingId(id);
    setRenameValue(currentTitle);
    setOpenMenuId(null);
  };

  const handleConfirmRename = () => {
    if (renamingId && renameValue.trim()) {
      onRename(renamingId, renameValue.trim());
    }
    setRenamingId(null);
    setRenameValue("");
  };

  const handleCancelRename = () => {
    setRenamingId(null);
    setRenameValue("");
  };

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
                {renamingId === s.id ? (
                  <input
                    ref={renameInputRef}
                    className="sidebar-rename-input"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleConfirmRename();
                      if (e.key === "Escape") handleCancelRename();
                    }}
                    onBlur={handleConfirmRename}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <span className="sidebar-session-title">{s.title}</span>
                )}
                <span className="sidebar-session-meta">{s.messageCount} 条消息</span>
              </div>
              <div className="sidebar-session-actions" ref={openMenuId === s.id ? menuRef : undefined}>
                <button
                  className="sidebar-session-menu-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setOpenMenuId(openMenuId === s.id ? null : s.id);
                  }}
                  title="更多操作"
                >
                  <MoreHorizontal size={14} />
                </button>
                {openMenuId === s.id && (
                  <div className="sidebar-dropdown">
                    <button
                      className="sidebar-dropdown-item"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStartRename(s.id, s.title);
                      }}
                    >
                      <Pencil size={14} />
                      <span>重命名</span>
                    </button>
                    <button
                      className="sidebar-dropdown-item sidebar-dropdown-item-danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        setOpenMenuId(null);
                        onDelete(s.id);
                      }}
                    >
                      <Trash2 size={14} />
                      <span>删除</span>
                    </button>
                  </div>
                )}
              </div>
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
