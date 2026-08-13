"use client";

import { Bot, User, Copy, Check, Pencil, Trash2, X, Send } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import StatusIndicator from "./StatusIndicator";
import type { AgentStatus } from "@/lib/api";

interface Props {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  status?: AgentStatus | null;
  onDelete?: () => void;
  editable?: boolean;
  isEditing?: boolean;
  onEditStart?: () => void;
  onEditCancel?: () => void;
  onEditSend?: (text: string) => void;
  selectMode?: boolean;
}

export default function ChatMessage({
  role,
  content,
  isStreaming,
  status,
  onDelete,
  editable,
  isEditing,
  onEditStart,
  onEditCancel,
  onEditSend,
  selectMode,
}: Props) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);
  const [editText, setEditText] = useState(content);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing) {
      setEditText(content);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (el) {
          el.style.height = "auto";
          el.style.height = Math.min(el.scrollHeight, 200) + "px";
          el.focus();
          el.setSelectionRange(el.value.length, el.value.length);
        }
      });
    }
  }, [isEditing]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setEditText(e.target.value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 200) + "px";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendEdit();
    }
    if (e.key === "Escape") {
      onEditCancel?.();
    }
  };

  const handleSendEdit = () => {
    const trimmed = editText.trim();
    if (!trimmed || !onEditSend) return;
    onEditSend(trimmed);
  };

  return (
    <div className={`chat-msg ${isUser ? "user" : "assistant"}`}>
      <div className={`chat-avatar ${isUser ? "user" : "assistant"}`}>
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      <div className="chat-bubble-wrap">
        <StatusIndicator
          status={status ?? null}
          visible={!!isStreaming}
        />

        {isEditing ? (
          <div className={`chat-edit-area${isUser ? " user" : ""}`}>
            <textarea
              ref={textareaRef}
              className="chat-edit-textarea"
              value={editText}
              onChange={handleTextareaInput}
              onKeyDown={handleKeyDown}
              rows={1}
            />
            <div className="chat-edit-actions">
              <button className="chat-edit-cancel" onClick={onEditCancel} title="取消">
                <X size={14} />
                <span>取消</span>
              </button>
              <button className="chat-edit-send" onClick={handleSendEdit} title="发送">
                <Send size={14} />
                <span>发送</span>
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className={`chat-bubble ${isUser ? "user" : "assistant"}${!isUser && isStreaming && !content ? " chat-streaming-empty" : ""}`}>
              {isUser ? (
                <span className="whitespace-pre-wrap">{content}</span>
              ) : content ? (
                <MarkdownRenderer content={content} />
              ) : null}
            </div>

            {!selectMode && content && !isStreaming && (
              <div className="chat-bubble-actions">
                <button className="chat-action-btn" onClick={handleCopy} title="复制">
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                </button>

                {editable && onEditStart && (
                  <button className="chat-action-btn" onClick={onEditStart} title="编辑">
                    <Pencil size={14} />
                  </button>
                )}

                {onDelete && (
                  <button className="chat-action-btn danger" onClick={onDelete} title="删除">
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}