import { useEffect, useState, useCallback } from "react";
import {
  X, Plus, Trash2, Check, Loader2, CircleDot, Pencil, Lock,
} from "lucide-react";
import {
  listProvidersData, createProvider, updateProviderApi, deleteProviderApi,
  addModelToProvider, removeModelFromProvider,
  setActiveModel, setActiveProvider,
  type ProviderData, type ModelInfo,
} from "@/lib/api";

export interface ContextSettings {
  threshold: number;
  keepRecentTurns: number;
}

const STORAGE_KEY = "coco_context_settings";

export function loadContextSettings(): ContextSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        threshold: Math.max(60, Math.min(95, parsed.threshold ?? 80)),
        keepRecentTurns: Math.max(3, Math.min(15, parsed.keepRecentTurns ?? 5)),
      };
    }
  } catch {}
  return { threshold: 80, keepRecentTurns: 5 };
}

export function saveContextSettings(settings: ContextSettings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

type View = "list" | "add" | "edit";

export default function SettingsPanel({ isOpen, onClose }: Props) {

  const [providers, setProviders] = useState<ProviderData[]>([]);
  const [activeProviderId, setActiveProviderId] = useState<string | undefined>();
  const [activeModelId, setActiveModelId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const [view, setView] = useState<View>("list");
  const [editingProvider, setEditingProvider] = useState<ProviderData | null>(null);

  const [form, setForm] = useState({ name: "", base_url: "", api_key: "", api_format: "openai" });
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModelIds, setSelectedModelIds] = useState<Set<string>>(new Set());

  // ---- 添加模型弹窗 ----
  const [showModelModal, setShowModelModal] = useState(false);
  const [editingModelIndex, setEditingModelIndex] = useState<number | null>(null);
  const [modelForm, setModelForm] = useState({
    id: "", context_window: 1000000, max_output_tokens: 128000,
    input_types: ["文本"] as string[], output_types: ["文本"] as string[],
  });

  const loadProviders = useCallback(async () => {
    try {
      const data = await listProvidersData();
      setProviders(data.providers);
      setActiveProviderId(data.active_provider_id);
      setActiveModelId(data.active_model_id);
    } catch {}
  }, []);

  useEffect(() => {
    if (isOpen) {
      setView("list");
      setEditingProvider(null);
      setModels([]);
      setSelectedModelIds(new Set());
      loadProviders();
    }
  }, [isOpen, loadProviders]);


  if (!isOpen && !showModelModal) return null;

  const resetForm = () => {
    setForm({ name: "", base_url: "", api_key: "", api_format: "openai" });
    setModels([]);
    setSelectedModelIds(new Set());
  };

  const handleAddProvider = () => { resetForm(); setEditingProvider(null); setView("add"); };

  const handleEditProvider = (p: ProviderData) => {
    setForm({ name: p.name, base_url: p.base_url, api_key: "", api_format: p.api_format });
    setEditingProvider(p);
    setModels(p.models);
    setSelectedModelIds(new Set(p.models.map((m) => m.id)));
    setView("edit");
  };

  const openAddModel = () => {
    setEditingModelIndex(null);
    setModelForm({ id: "", context_window: 1000000, max_output_tokens: 128000, input_types: ["文本"], output_types: ["文本"] });
    setShowModelModal(true);
  };

  const openEditModel = (index: number) => {
    const m = models[index];
    setEditingModelIndex(index);
    setModelForm({
      id: m.id,
      context_window: m.context_window || 0,
      max_output_tokens: m.max_output_tokens || 0,
      input_types: m.input_types?.length ? m.input_types : ["文本"],
      output_types: m.output_types?.length ? m.output_types : ["文本"],
    });
    setShowModelModal(true);
  };

  const handleSaveModel = () => {
    const name = modelForm.id.trim();
    if (!name) return;
    const model: ModelInfo = {
      id: name, display_name: name,
      context_window: modelForm.context_window,
      max_output_tokens: modelForm.max_output_tokens,
      input_types: modelForm.input_types,
      output_types: modelForm.output_types,
    };
    if (editingModelIndex !== null) {
      const next = [...models];
      next[editingModelIndex] = model;
      setModels(next);
    } else {
      setModels([...models, model]);
      setSelectedModelIds(new Set([...selectedModelIds, name]));
    }
    setShowModelModal(false);
  };

  const handleRemoveModel = (modelId: string) => {
    setModels(models.filter((m) => m.id !== modelId));
    const next = new Set(selectedModelIds);
    next.delete(modelId);
    setSelectedModelIds(next);
  };


  const handleSaveProvider = async () => {
    setLoading(true);
    try {
      const modelsToAdd = models.filter((m) => selectedModelIds.has(m.id));
      if (editingProvider) {
        const updates: Record<string, string> = {};
        if (form.name !== editingProvider.name) updates.name = form.name;
        if (form.base_url !== editingProvider.base_url) updates.base_url = form.base_url;
        if (form.api_key) updates.api_key = form.api_key;
        if (form.api_format !== editingProvider.api_format) updates.api_format = form.api_format;
        if (Object.keys(updates).length > 0) await updateProviderApi(editingProvider.id, updates);
        const existingIds = new Set(editingProvider.models.map((m) => m.id));
        for (const m of modelsToAdd) { if (!existingIds.has(m.id)) await addModelToProvider(editingProvider.id, m); }
        for (const m of editingProvider.models) { if (!selectedModelIds.has(m.id)) await removeModelFromProvider(editingProvider.id, m.id); }
      } else {
        const result = await createProvider(form);
        if (result.status === "ok") { for (const m of modelsToAdd) await addModelToProvider(result.provider_id, m); }
      }
      await loadProviders();
      setView("list");
    } catch (e) { console.error("保存失败:", e); }
    setLoading(false);
  };

  const handleDeleteProvider = async (id: string) => {
    await deleteProviderApi(id);
    await loadProviders();
    setView("list");
    setEditingProvider(null);
  };

  const handleSetActive = async (providerId: string, modelId: string) => {
    await setActiveModel(providerId, modelId);
    await loadProviders();
  };

  return (
    <>
    <div className="settings-overlay">
      <div className="settings-panel settings-panel-wide">
        <div className="settings-header">
          <h3>模型配置</h3>
          <button className="settings-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="settings-body-row">
          {/* 左栏 */}
          <div className="settings-sidebar">
            <div className="settings-sidebar-header">供应商</div>
            {providers.map((p) => (
              <div key={p.id}
                className={`settings-sidebar-item${view === "edit" && editingProvider?.id === p.id ? " active" : ""}`}
                onClick={() => handleEditProvider(p)}>
                <CircleDot size={14} className={p.is_active ? "text-green" : "text-muted"} />
                <span className="settings-sidebar-item-name">{p.name}</span>
                {p.is_active ? (
                  <span className="settings-sidebar-active-label">使用中</span>
                ) : (
                  <button className="settings-sidebar-enable-btn"
                    onClick={(e) => { e.stopPropagation(); setActiveProvider(p.id).then(loadProviders); }}>
                    启用
                  </button>
                )}
              </div>
            ))}
            <button className="settings-sidebar-add" onClick={handleAddProvider}>
              <Plus size={14} /> 添加供应商
            </button>
          </div>

          {/* 右栏 */}
          <div className="settings-content">
            {view === "list" && (
              <div className="settings-model-empty">
                选择左侧供应商进行配置，或点击"添加供应商"创建新的。
              </div>
            )}

            {(view === "add" || view === "edit") && (
              <>
                <div className="settings-section-title">{view === "add" ? "添加模型供应商" : "配置供应商"}</div>
                <p className="settings-desc" style={{ marginTop: 0 }}>配置一个 API 端点和可用模型。</p>

                <div className="settings-group">
                  <label className="settings-field-label">名称</label>
                  <input type="text" className="settings-text-input" placeholder="如：小米 Mimo"
                    value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </div>
                <div className="settings-group">
                  <label className="settings-field-label">Base URL</label>
                  <input type="text" className="settings-text-input" placeholder="https://api.example.com/v1"
                    value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
                </div>
                <div className="settings-group">
                  <label className="settings-field-label">API Key</label>
                  <input type="password" className="settings-text-input"
                    placeholder={editingProvider?.api_key_set ? "留空则不修改" : "输入 API Key"}
                    value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
                </div>
                <div className="settings-group">
                  <label className="settings-field-label">API 格式</label>
                  <select className="settings-select" value={form.api_format}
                    onChange={(e) => setForm({ ...form, api_format: e.target.value })}>
                    <option value="openai">Chat Completions (/chat/completions)</option>
                    <option value="anthropic">Anthropic Messages (/v1/messages)</option>
                    <option value="ollama">Ollama (本地)</option>
                  </select>
                </div>

                <div className="settings-group">
                  <label className="settings-field-label">模型列表</label>
                  {models.length > 0 ? (
                    <div className="settings-model-list">
                      {models.map((m, idx) => {
                        const isActive = m.id === activeModelId && editingProvider?.id === activeProviderId;
                        return (
                          <div key={m.id} className={`settings-model-item-new${isActive ? " active" : ""}`}>
                            <span className="settings-model-item-name">{m.display_name || m.id}</span>
                            <div className="settings-model-item-tags">
                              {m.context_window > 0 && (
                                <span className="settings-model-tag-sm">
                                  {m.context_window >= 1_000_000
                                    ? `${(m.context_window / 1_000_000).toFixed(0)}M`
                                    : `${(m.context_window / 1_000).toFixed(0)}K`}
                                </span>
                              )}
                              {m.input_types?.filter((t) => t !== "文本").map((t) => (
                                <span key={t} className="settings-model-tag-sm tag-vision">{t}</span>
                              ))}
                            </div>
                            <div className="settings-model-item-actions">
                              <button className="settings-model-icon-btn" title="编辑"
                                onClick={() => openEditModel(idx)}>
                                <Pencil size={13} />
                              </button>
                              {editingProvider && (
                                <button className={`settings-model-icon-btn${isActive ? " active" : ""}`}
                                  onClick={() => handleSetActive(editingProvider.id, m.id)}
                                  title={isActive ? "当前活跃" : "设为活跃"}>
                                  <CircleDot size={13} />
                                </button>
                              )}
                              <button className="settings-model-icon-btn danger"
                                onClick={() => handleRemoveModel(m.id)} title="删除">
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="settings-model-empty-box">
                      <span>当前没有配置模型，添加模型后可在聊天中使用。</span>
                    </div>
                  )}
                  <button className="settings-add-model-btn" onClick={openAddModel}>
                    <Plus size={14} /> 添加模型
                  </button>
                </div>

                <div className="settings-action-row" style={{ marginTop: 16 }}>
                  {view === "edit" && (
                    <button className="settings-delete-btn" onClick={() => handleDeleteProvider(editingProvider!.id)}>
                      <Trash2 size={14} /> 删除
                    </button>
                  )}
                  <button className="settings-cancel-btn" onClick={() => setView("list")}>取消</button>
                  <button className="settings-save-btn" onClick={handleSaveProvider} disabled={loading || !form.name}>
                    {loading ? <Loader2 size={14} className="settings-spin" /> : <Check size={14} />}
                    <span>{view === "add" ? "添加供应商" : "保存"}</span>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>

      {/* ---- 添加模型弹窗 ---- */}
      {showModelModal && (
        <div className="model-modal-overlay"
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}>
          <div className="model-modal" onClick={(e) => e.stopPropagation()}>
            <div className="model-modal-header">
              <h4>{editingModelIndex !== null ? "编辑模型" : "添加模型"}</h4>
              <button className="settings-close-btn" onClick={() => setShowModelModal(false)}>
                <X size={16} />
              </button>
            </div>
            <div className="model-modal-body">
              <div className="settings-group">
                <label className="settings-field-label">模型 ID</label>
                <input type="text" className="settings-text-input"
                  placeholder="模型 ID"
                  value={modelForm.id}
                  onChange={(e) => setModelForm({ ...modelForm, id: e.target.value })} />
              </div>
              <div className="settings-group">
                <label className="settings-field-label">上下文窗口</label>
                <input type="number" className="settings-text-input"
                  value={modelForm.context_window}
                  onChange={(e) => setModelForm({ ...modelForm, context_window: Number(e.target.value) })} />
              </div>
              <div className="settings-group">
                <label className="settings-field-label">最大输出 Token</label>
                <input type="number" className="settings-text-input"
                  value={modelForm.max_output_tokens}
                  onChange={(e) => setModelForm({ ...modelForm, max_output_tokens: Number(e.target.value) })} />
              </div>
              <div className="settings-group">
                <label className="settings-field-label">输入类型</label>
                <div className="settings-type-chips">
                  <span className="settings-type-chip active locked">
                    文本<Lock size={10} className="settings-type-lock" />
                  </span>
                  {["图片", "视频", "PDF"].map((t) => (
                    <span key={t} className="settings-type-chip disabled">
                      {t}
                    </span>
                  ))}
                </div>
              </div>
              <div className="settings-group">
                <label className="settings-field-label">输出类型</label>
                <div className="settings-type-chips">
                  <span className="settings-type-chip active locked">
                    文本<Lock size={10} className="settings-type-lock" />
                  </span>
                </div>
              </div>
            </div>
            <div className="model-modal-footer">
              <button className="settings-cancel-btn" onClick={() => setShowModelModal(false)}>取消</button>
              <button className="settings-save-btn" onClick={handleSaveModel} disabled={!modelForm.id.trim()}>
                <Check size={14} /><span>保存</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
