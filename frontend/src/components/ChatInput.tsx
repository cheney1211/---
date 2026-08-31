"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import ModeSwitcher, { type ConfirmationMode } from "./ModeSwitcher";

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
  onStop?: () => void;
  prefillKey?: number;
  prefillText?: string;
  mode?: ConfirmationMode;
  onModeChange?: (mode: ConfirmationMode) => void;
}

export default function ChatInput({ onSend, disabled, onStop, prefillKey, prefillText, mode, onModeChange }: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
      el.style.height = Math.min(el.scrollHeight, 160) + "px";
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

  return (
    <div className="chat-input-bar">
      <div className="chat-input-inner">
        {mode && onModeChange && (
          <ModeSwitcher mode={mode} onChange={onModeChange} disabled={disabled} />
        )}
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
          disabled={disabled}
          rows={1}
          className="chat-input-textarea"
        />
        {disabled && onStop ? (
          <button
            onClick={onStop}
            className="chat-input-btn stop"
            title="停止生成"
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!text.trim() || disabled}
            className="chat-input-btn send"
            title="发送"
          >
            <Send size={16} />
          </button>
        )}
      </div>
    </div>
  );
}
