"use client";

import { useState, useRef, useEffect } from "react";
import { MessageSquarePlus, MessageCircle, Wifi, WifiOff, MoreHorizontal, Pencil, Trash2, FolderOpen, Plus, ChevronDown } from "lucide-react";

export interface SessionMeta {
  id: string;
  title: string;
  updatedAt: number;
  messageCount: number;
}

export interface ProjectMeta {
  id: string;
  name: string;
}

interface Props {
  projects: ProjectMeta[];
  activeProjectId: string | undefined;
  sessions: SessionMeta[];
  activeSessionId: string | undefined;
  isConnected: boolean;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
  onRenameProject: (id: string, name: string) => void;
  onDeleteProject: (id: string) => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
}

export default function Sidebar({
  projects,
  activeProjectId,
  sessions,
  activeSessionId,
  isConnected,
  onSelectProject,
  onNewProject,
  onRenameProject,
  onDeleteProject,
  onSelect,
  onNew,
  onDelete,
  onRename,
}: Props) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [projectRenameValue, setProjectRenameValue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const projectMenuRef = useRef<HTMLDivElement>(null);
  const projectRenameRef = useRef<HTMLInputElement>(null);

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

  // Close project menu on outside click
  useEffect(() => {
    if (!projectMenuOpen) return;
    const handle = (e: MouseEvent) => {
      if (projectMenuRef.current && !projectMenuRef.current.contains(e.target as Node)) {
        setProjectMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [projectMenuOpen]);

  // Focus project rename input
  useEffect(() => {
    if (renamingProjectId) {
      projectRenameRef.current?.focus();
      projectRenameRef.current?.select();
    }
  }, [renamingProjectId]);

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

  const activeProject = projects.find((p) => p.id === activeProjectId);

  const handleProjectRenameConfirm = () => {
    if (renamingProjectId && projectRenameValue.trim()) {
      onRenameProject(renamingProjectId, projectRenameValue.trim());
    }
    setRenamingProjectId(null);
    setProjectRenameValue("");
    setProjectMenuOpen(false);
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

      {/* Project selector */}
      <div className="sidebar-project" ref={projectMenuOpen ? projectMenuRef : undefined}>
        <button
          className="sidebar-project-btn"
          onClick={() => setProjectMenuOpen(!projectMenuOpen)}
        >
          <FolderOpen size={14} className="sidebar-project-icon" />
          {renamingProjectId === activeProjectId ? (
            <input
              ref={projectRenameRef}
              className="sidebar-project-rename-input"
              value={projectRenameValue}
              onChange={(e) => setProjectRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleProjectRenameConfirm();
                if (e.key === "Escape") { setRenamingProjectId(null); setProjectMenuOpen(false); }
              }}
              onBlur={handleProjectRenameConfirm}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <span className="sidebar-project-name">{activeProject?.name || "未选择项目"}</span>
          )}
          <ChevronDown size={14} className={`sidebar-project-chevron ${projectMenuOpen ? "open" : ""}`} />
        </button>
        {projectMenuOpen && !renamingProjectId && (
          <div className="sidebar-project-dropdown">
            {projects.map((p) => (
              <div
                key={p.id}
                className={`sidebar-project-item ${p.id === activeProjectId ? "active" : ""}`}
                role="button"
                tabIndex={0}
                onClick={() => { onSelectProject(p.id); setProjectMenuOpen(false); }}
              >
                <span className="sidebar-project-item-name">{p.name}</span>
                {p.id === activeProjectId && (
                  <div className="sidebar-project-item-actions">
                    <button
                      className="sidebar-project-action"
                      title="重命名"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingProjectId(p.id);
                        setProjectRenameValue(p.name);
                      }}
                    >
                      <Pencil size={12} />
                    </button>
                    {projects.length > 1 && (
                      <button
                        className="sidebar-project-action danger"
                        title="删除项目"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteProject(p.id);
                          setProjectMenuOpen(false);
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div
              className="sidebar-project-item new"
              role="button"
              tabIndex={0}
              onClick={() => { onNewProject(); setProjectMenuOpen(false); }}
            >
              <Plus size={14} />
              <span>新建项目</span>
            </div>
          </div>
        )}
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
