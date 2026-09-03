
import { useState, useRef, useEffect, useCallback } from "react";
import { MessageSquarePlus, MoreHorizontal, Pencil, Trash2, FolderOpen, Folder, ChevronRight, ChevronDown, PanelLeftClose } from "lucide-react";

export interface SessionMeta {
  id: string;
  title: string;
  updatedAt: number;
  messageCount: number;
  projectId?: string;
}

export interface ProjectMeta {
  id: string;
  name: string;
}

interface SessionItemProps {
  session: SessionMeta;
  isActive: boolean;
  isRenaming: boolean;
  renameValue: string;
  openMenuId: string | null;
  sidebarWidth: number;
  menuRef: React.RefObject<HTMLDivElement | null>;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRenameStart: (id: string, title: string) => void;
  onRenameConfirm: () => void;
  onRenameCancel: () => void;
  onRenameChange: (value: string) => void;
  onMenuToggle: (id: string | null) => void;
  showMeta?: boolean;
}

function SessionItem({
  session,
  isActive,
  isRenaming,
  renameValue,
  openMenuId,
  sidebarWidth,
  menuRef,
  onSelect,
  onDelete,
  onRenameStart,
  onRenameConfirm,
  onRenameCancel,
  onRenameChange,
  onMenuToggle,
  showMeta = true,
}: SessionItemProps) {
  const titleRef = useRef<HTMLDivElement>(null);
  const spanRef = useRef<HTMLSpanElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);

  // 检测文字是否溢出
  const checkOverflow = () => {
    if (titleRef.current && spanRef.current) {
      // 比较span的实际宽度和容器的可见宽度
      setIsOverflowing(spanRef.current.scrollWidth > titleRef.current.clientWidth);
    }
  };

  useEffect(() => {
    // 延迟检测，确保DOM已渲染
    const timer = setTimeout(checkOverflow, 10);
    window.addEventListener('resize', checkOverflow);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', checkOverflow);
    };
  }, [session.title, sidebarWidth]);

  // 聚焦重命名输入框
  useEffect(() => {
    if (isRenaming && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [isRenaming]);

  return (
    <div
      className={`sidebar-session ${isActive ? "active" : ""}`}
      onClick={() => onSelect(session.id)}
    >
        <div className="sidebar-session-content">
          <div ref={titleRef} className={`sidebar-session-title${isOverflowing ? ' overflow' : ''}`}>
            {isRenaming ? (
              <input
                ref={renameInputRef}
                className="sidebar-rename-input"
                value={renameValue}
                onChange={(e) => onRenameChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onRenameConfirm();
                  if (e.key === "Escape") onRenameCancel();
                }}
                onBlur={onRenameConfirm}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <span ref={spanRef}>{session.title || "新对话"}</span>
            )}
          </div>
        {showMeta && (
          <div className="sidebar-session-meta">
            <span className="sidebar-session-count">{session.messageCount} 条消息</span>
          </div>
        )}
      </div>
      <div className="sidebar-session-actions" ref={openMenuId === session.id ? menuRef : undefined}>
        <button
          className="sidebar-session-menu-btn"
          onClick={(e) => {
            e.stopPropagation();
            onMenuToggle(openMenuId === session.id ? null : session.id);
          }}
        >
          <MoreHorizontal size={14} />
        </button>
        {openMenuId === session.id && (
          <div className="sidebar-session-menu">
            <button
              className="sidebar-session-menu-item"
              onClick={(e) => {
                e.stopPropagation();
                onRenameStart(session.id, session.title || "");
                onMenuToggle(null);
              }}
            >
              <Pencil size={12} />
              <span>重命名</span>
            </button>
            <button
              className="sidebar-session-menu-item danger"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(session.id);
                onMenuToggle(null);
              }}
            >
              <Trash2 size={12} />
              <span>删除</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

interface Props {
  projects: ProjectMeta[];
  sessions: SessionMeta[];
  activeSessionId: string | undefined;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
  onOpenFolder: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onNewInProject: (projectId: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onSelectProject: (id: string) => void;
}

export default function Sidebar({
  projects,
  sessions,
  activeSessionId,
  sidebarOpen,
  onToggleSidebar,
  onOpenFolder,
  onSelect,
  onNew,
  onNewInProject,
  onDelete,
  onRename,
  onSelectProject,
}: Props) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [brandHovered, setBrandHovered] = useState(false);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  const [sidebarWidth, setSidebarWidth] = useState(280);
  const [isResizing, setIsResizing] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const addMenuRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
      if (addMenuRef.current && !addMenuRef.current.contains(e.target as Node)) {
        setAddMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleRenameConfirm = () => {
    if (renamingId && renameValue.trim()) {
      onRename(renamingId, renameValue.trim());
    }
    setRenamingId(null);
  };

  const handleOpenFolder = () => {
    setAddMenuOpen(false);
    onOpenFolder();
  };

  const toggleProject = (projectId: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev);
      if (next.has(projectId)) {
        next.delete(projectId);
      } else {
        next.add(projectId);
      }
      return next;
    });
  };

  // 侧边栏拖动调整大小
  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    const startX = e.clientX;
    const startWidth = sidebarWidth;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = Math.max(200, Math.min(500, startWidth + (e.clientX - startX)));
      setSidebarWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [sidebarWidth]);

  // 获取不属于任何项目的普通对话
  const ungroupedSessions = sessions.filter((s) => !s.projectId);

  // 获取属于特定项目的对话
  const getProjectSessions = (projectId: string) => {
    return sessions.filter((s) => s.projectId === projectId);
  };

  return (
    <aside
      ref={sidebarRef}
      className={`sidebar${isResizing ? ' resizing' : ''}`}
      style={{ width: sidebarWidth, minWidth: sidebarWidth }}
    >
      {/* Resize handle */}
      <div
        className={`sidebar-resize-handle${isResizing ? ' active' : ''}`}
        onMouseDown={handleResizeStart}
      />

      {/* Header */}
      <div className="sidebar-header">
        <div
          className={`sidebar-brand${brandHovered ? ' hovered' : ''}`}
          onMouseEnter={() => setBrandHovered(true)}
          onMouseLeave={() => setBrandHovered(false)}
          onClick={onToggleSidebar}
          title={sidebarOpen ? "收起侧边栏" : "展开侧边栏"}
        >
          {brandHovered ? (
            <PanelLeftClose size={22} className="sidebar-brand-icon sidebar-brand-toggle" />
          ) : (
            <img src="/logo.png" alt="Coco" className="sidebar-brand-icon" />
          )}
        </div>
      </div>

      {/* Projects Section */}
      <div className="sidebar-section">
        <div className="sidebar-section-header">
          <div className="sidebar-section-title">项目</div>
          <div className="sidebar-add-wrapper" ref={addMenuRef}>
            <button
              className="sidebar-add-btn"
              title="添加项目"
              onClick={() => setAddMenuOpen(!addMenuOpen)}
            >
              <FolderOpen size={16} />
            </button>
            {addMenuOpen && (
              <div className="sidebar-add-dropdown">
                <button
                  className="sidebar-add-item"
                  onClick={handleOpenFolder}
                >
                  <FolderOpen size={14} />
                  <span>打开项目文件夹</span>
                </button>
              </div>
            )}
          </div>
        </div>
        {projects.length === 0 ? (
          <div className="sidebar-section-empty">
            <span>还没有项目</span>
          </div>
        ) : (
          projects.map((project) => (
            <div key={project.id} className="sidebar-project-group">
              <div className="sidebar-project-header">
                <div
                  className="sidebar-project-header-main"
                  onClick={() => {
                    onSelectProject(project.id);
                    toggleProject(project.id);
                  }}
                >
                  {expandedProjects.has(project.id) ? (
                    <ChevronDown size={14} className="sidebar-project-chevron" />
                  ) : (
                    <ChevronRight size={14} className="sidebar-project-chevron" />
                  )}
                  <Folder size={14} className="sidebar-project-icon" />
                  <span className="sidebar-project-name">{project.name}</span>
                </div>
                <button
                  className="sidebar-project-add-btn"
                  title="新建任务"
                  onClick={(e) => {
                    e.stopPropagation();
                    onNewInProject(project.id);
                  }}
                >
                  <MessageSquarePlus size={14} />
                </button>
              </div>
              {expandedProjects.has(project.id) && (
                <div className="sidebar-project-sessions">
                  {getProjectSessions(project.id).length === 0 ? (
                    <div className="sidebar-section-empty">暂无对话</div>
                  ) : (
                    getProjectSessions(project.id).map((s) => (
                      <SessionItem
                        key={s.id}
                        session={s}
                        isActive={s.id === activeSessionId}
                        isRenaming={renamingId === s.id}
                        renameValue={renameValue}
                        openMenuId={openMenuId}
                        sidebarWidth={sidebarWidth}
                        menuRef={menuRef}
                        onSelect={onSelect}
                        onDelete={onDelete}
                        onRenameStart={(id, title) => {
                          setRenamingId(id);
                          setRenameValue(title);
                        }}
                        onRenameConfirm={handleRenameConfirm}
                        onRenameCancel={() => setRenamingId(null)}
                        onRenameChange={setRenameValue}
                        onMenuToggle={setOpenMenuId}
                      />
                    ))
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Tasks Section (ungrouped sessions) */}
      <div className="sidebar-section">
        <div className="sidebar-section-header">
          <div className="sidebar-section-title">任务</div>
          <button onClick={onNew} className="sidebar-add-btn" title="新建对话">
            <MessageSquarePlus size={16} />
          </button>
        </div>
        {ungroupedSessions.length === 0 ? (
          <div className="sidebar-section-empty">还没有任务</div>
        ) : (
          ungroupedSessions.map((s) => (
            <SessionItem
              key={s.id}
              session={s}
              isActive={s.id === activeSessionId}
              isRenaming={renamingId === s.id}
              renameValue={renameValue}
              openMenuId={openMenuId}
              sidebarWidth={sidebarWidth}
              menuRef={menuRef}
              onSelect={onSelect}
              onDelete={onDelete}
              onRenameStart={(id, title) => {
                setRenamingId(id);
                setRenameValue(title);
              }}
              onRenameConfirm={handleRenameConfirm}
              onRenameCancel={() => setRenamingId(null)}
              onRenameChange={setRenameValue}
              onMenuToggle={setOpenMenuId}
            />
          ))
        )}
      </div>
    </aside>
  );
}
