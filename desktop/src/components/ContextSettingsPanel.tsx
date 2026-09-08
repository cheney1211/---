import { X, RotateCcw } from "lucide-react";
import type { ContextSettings } from "./SettingsPanel";

const DEFAULT_SETTINGS: ContextSettings = {
  threshold: 80,
  keepRecentTurns: 5,
};

interface Props {
  isOpen: boolean;
  onClose: () => void;
  settings: ContextSettings;
  onChange: (settings: ContextSettings) => void;
}

export default function ContextSettingsPanel({
  isOpen, onClose, settings, onChange,
}: Props) {
  if (!isOpen) return null;

  const handleReset = () => {
    onChange({ ...DEFAULT_SETTINGS });
  };

  return (
    <div className="settings-overlay">
      <div className="settings-panel settings-panel-narrow">
        <div className="settings-header">
          <h3>上下文管理</h3>
          <button className="settings-close-btn" onClick={onClose}><X size={16} /></button>
        </div>
        <div className="settings-body">
          <div className="settings-group">
            <div className="settings-group-header">
              <label>压缩阈值</label>
              <span className="settings-value">{settings.threshold}%</span>
            </div>
            <p className="settings-desc">当上下文使用率达到此阈值时，自动触发压缩。</p>
            <div className="settings-slider-row">
              <span className="settings-slider-label">60%</span>
              <input type="range" min={60} max={95} step={1} value={settings.threshold}
                onChange={(e) => onChange({ ...settings, threshold: Math.max(60, Math.min(95, Number(e.target.value))) })}
                className="settings-slider" />
              <span className="settings-slider-label">95%</span>
            </div>
          </div>

          <div className="settings-group">
            <div className="settings-group-header">
              <label>保留近期轮数</label>
              <span className="settings-value">{settings.keepRecentTurns} 轮</span>
            </div>
            <p className="settings-desc">压缩时保留最近 N 轮完整对话，确保当前任务连续性。</p>
            <div className="settings-slider-row">
              <span className="settings-slider-label">3</span>
              <input type="range" min={3} max={15} step={1} value={settings.keepRecentTurns}
                onChange={(e) => onChange({ ...settings, keepRecentTurns: Math.max(3, Math.min(15, Number(e.target.value))) })}
                className="settings-slider" />
              <span className="settings-slider-label">15</span>
            </div>
          </div>

          <div className="settings-footer">
            <button className="settings-reset-btn" onClick={handleReset}>
              <RotateCcw size={14} /><span>恢复默认</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
