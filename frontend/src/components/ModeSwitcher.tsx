"use client";

import { useState, useRef, useEffect } from "react";
import { Shield, Eye, Zap, ChevronDown } from "lucide-react";

export type ConfirmationMode = "confirm" | "plan" | "full_access";

interface Props {
  mode: ConfirmationMode;
  onChange: (mode: ConfirmationMode) => void;
  disabled?: boolean;
}

const MODES: { value: ConfirmationMode; label: string; icon: typeof Shield; tip: string }[] = [
  { value: "confirm", label: "变更前确认", icon: Shield, tip: "危险操作前弹出确认框" },
  { value: "plan", label: "计划模式", icon: Eye, tip: "所有工具调用都需确认" },
  { value: "full_access", label: "完全访问", icon: Zap, tip: "跳过所有确认，直接执行" },
];

export default function ModeSwitcher({ mode, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const current = MODES.find((m) => m.value === mode) ?? MODES[0];
  const CurrentIcon = current.icon;

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const handleSelect = (value: ConfirmationMode) => {
    onChange(value);
    setOpen(false);
  };

  return (
    <div className="mode-switcher" ref={ref}>
      <button
        className="mode-switcher-trigger"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        title={current.tip}
      >
        <CurrentIcon size={14} />
        <span className="mode-switcher-trigger-label">{current.label}</span>
        <ChevronDown size={12} className={`mode-switcher-arrow${open ? " open" : ""}`} />
      </button>

      {open && (
        <div className="mode-switcher-dropdown">
          {MODES.map((m) => {
            const Icon = m.icon;
            const active = m.value === mode;
            return (
              <button
                key={m.value}
                className={`mode-switcher-option${active ? " active" : ""}`}
                onClick={() => handleSelect(m.value)}
                title={m.tip}
              >
                <Icon size={14} />
                <span className="mode-switcher-option-label">{m.label}</span>
                {active && <span className="mode-switcher-check">✓</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
