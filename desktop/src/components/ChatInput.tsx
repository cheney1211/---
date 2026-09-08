
import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Square, Plus, Settings, SlidersHorizontal, ChevronRight, Check, ChevronDown } from "lucide-react";
import ModeSwitcher, { type ConfirmationMode } from "./ModeSwitcher";
import { listProvidersData, setActiveModel, type ProviderData } from "@/lib/api";

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
  onStop?: () => void;
  prefillKey?: number;
  prefillText?: string;
  mode?: ConfirmationMode;
  onModeChange?: (mode: ConfirmationMode) => void;
  isEmpty?: boolean;
  onOpenModelSettings?: () => void;
  onOpenContextSettings?: () => void;
}

export default function ChatInput({ onSend, disabled, onStop, prefillKey, prefillText, mode, onModeChange, isEmpty, onOpenModelSettings, onOpenContextSettings }: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ---- Provider 下拉 ----
  const [providers, setProviders] = useState<ProviderData[]>([]);
  const [activeProviderId, setActiveProviderId] = useState<string | undefined>();
  const [activeModelId, setActiveModelId] = useState<string | undefined>();
  const [menuOpen, setMenuOpen] = useState(false);
  const [hoveredProviderId, setHoveredProviderId] = useState<string | null>(null);
  const [submenuFlip, setSubmenuFlip] = useState<Record<string, boolean>>({});
  const menuRef = useRef<HTMLDivElement>(null);
  const submenuRef = useRef<HTMLDivElement>(null);

  const loadProviders = useCallback(async () => {
    try {
      const data = await listProvidersData();
      setProviders(data.providers);
      setActiveProviderId(data.active_provider_id);
      setActiveModelId(data.active_model_id);
    } catch {}
  }, []);

  useEffect(() => { loadProviders(); }, [loadProviders]);

  // 点击外部关闭菜单
  useEffect(() => {
    if (!menuOpen) return;
    const h = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setHoveredProviderId(null);
      }
    };
    document.addEventListener("mousedown", h);
    document.addEventListener("click", h);
    return () => {
      document.removeEventListener("mousedown", h);
      document.removeEventListener("click", h);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (prefillKey && typeof prefillText === "string") {
      setText(prefillText);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) {
          el.focus();
          const len = prefillText.length;
          el.setSelectionRange(len, len);
        }
      });
    }
  }, [prefillKey]);
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  }, [text]);

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSwitchModel = async (providerId: string, modelId: string) => {
    await setActiveModel(providerId, modelId);
    setMenuOpen(false);
    loadProviders();
  };

  // 悬浮供应商时，测量子菜单实际宽度决定是否翻转
  useEffect(() => {
    if (!hoveredProviderId || !submenuRef.current) return;
    const item = submenuRef.current.closest(".chat-model-menu-item") as HTMLElement;
    if (!item) return;
    const itemRect = item.getBoundingClientRect();
    const subRect = submenuRef.current.getBoundingClientRect();
    const willOverflow = itemRect.right + subRect.width > window.innerWidth;
    setSubmenuFlip((prev) => ({ ...prev, [hoveredProviderId]: willOverflow }));
  }, [hoveredProviderId]);

  // 当前活跃的 provider 和 model
  const activeProvider = providers.find((p) => p.id === activeProviderId);
  const activeModel = activeProvider?.models.find((m) => m.id === activeModelId);
  const hasProviders = providers.length > 0;

  return (
    <div className="chat-input-container">
      <div className="chat-input-box">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isEmpty ? "向 Coco 提问" : "提出后续修改要求"}
          disabled={disabled}
          rows={1}
          className="chat-input-textarea"
        />
        <div className="chat-input-footer">
          <div className="chat-input-left">
            <button className="chat-input-tool-btn" title="添加">
              <Plus size={16} />
            </button>
            {mode && onModeChange && (
              <ModeSwitcher mode={mode} onChange={onModeChange} disabled={disabled} />
            )}
          </div>
          <div className="chat-input-right">
            {/* 供应商/模型选择器 */}
            <div className="chat-model-selector" ref={menuRef}>
              <button
                className="chat-model-trigger"
                onClick={() => { setMenuOpen(!menuOpen); if (!menuOpen) loadProviders(); }}
              >
                {hasProviders ? (
                  <span className="chat-model-trigger-text">
                    {activeProvider?.name || "未选择"}
                    {activeModel && <span className="chat-model-trigger-id">/{activeModel.id}</span>}
                  </span>
                ) : (
                  <span className="chat-model-trigger-empty">请添加供应商</span>
                )}
                <ChevronDown size={14} className={`chat-model-trigger-arrow${menuOpen ? " open" : ""}`} />
              </button>

              {menuOpen && (
                <div className="chat-model-menu">
                  {providers.map((p) => {
                    const isActive = p.id === activeProviderId;
                    return (
                      <div
                        key={p.id}
                        className="chat-model-menu-item"
                        onMouseEnter={() => setHoveredProviderId(p.id)}
                        onMouseLeave={() => setHoveredProviderId(null)}
                      >
                        <div className="chat-model-menu-item-main">
                          <span className="chat-model-menu-item-name">{p.name}</span>
                          {isActive && <Check size={14} className="text-green" />}
                          {p.models.length > 0 && <ChevronRight size={14} className="text-muted" />}
                        </div>

                        {/* 模型子菜单 */}
                        {hoveredProviderId === p.id && p.models.length > 0 && (
                          <div ref={submenuRef} className={`chat-model-submenu${submenuFlip[p.id] ? " flip-left" : ""}`}>
                            {p.models.map((m) => {
                              const isModelActive = isActive && m.id === activeModelId;
                              return (
                                <button
                                  key={m.id}
                                  className={`chat-model-submenu-item${isModelActive ? " active" : ""}`}
                                  onClick={() => handleSwitchModel(p.id, m.id)}
                                >
                                  <span>{m.id}</span>
                                  {isModelActive && <Check size={12} className="text-green" />}
                                </button>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  <div className="chat-model-menu-divider" />

                  <button className="chat-model-menu-item manage" onClick={() => { setMenuOpen(false); onOpenModelSettings?.(); }}>
                    <Settings size={14} />
                    <span>管理模型</span>
                  </button>
                </div>
              )}
            </div>

            {onOpenContextSettings && (
              <button className="chat-input-tool-btn" onClick={onOpenContextSettings} title="上下文管理">
                <SlidersHorizontal size={15} />
              </button>
            )}
            {disabled && onStop ? (
              <button onClick={onStop} className="chat-input-send-btn stop" title="停止生成">
                <Square size={16} />
              </button>
            ) : (
              <button onClick={handleSend} disabled={!text.trim() || disabled} className="chat-input-send-btn" title="发送">
                <Send size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
