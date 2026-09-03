
import { useState, useRef, useEffect } from "react";
import { Send, Square, Plus } from "lucide-react";
import ModeSwitcher, { type ConfirmationMode } from "./ModeSwitcher";

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
  onStop?: () => void;
  prefillKey?: number;
  prefillText?: string;
  mode?: ConfirmationMode;
  onModeChange?: (mode: ConfirmationMode) => void;
  isEmpty?: boolean;
}

export default function ChatInput({ onSend, disabled, onStop, prefillKey, prefillText, mode, onModeChange, isEmpty }: Props) {
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
            {disabled && onStop ? (
              <button
                onClick={onStop}
                className="chat-input-send-btn stop"
                title="停止生成"
              >
                <Square size={16} />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!text.trim() || disabled}
                className="chat-input-send-btn"
                title="发送"
              >
                <Send size={16} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
