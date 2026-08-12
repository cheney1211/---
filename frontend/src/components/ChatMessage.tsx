"use client";

import { Bot, User, Copy, Check } from "lucide-react";
import { useState } from "react";
import MarkdownRenderer from "./MarkdownRenderer";
import StatusIndicator from "./StatusIndicator";
import type { AgentStatus } from "@/lib/api";

interface Props {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  status?: AgentStatus | null;
}

export default function ChatMessage({ role, content, isStreaming, status }: Props) {
  const isUser = role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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

        <div className={`chat-bubble ${isUser ? "user" : "assistant"}${!isUser && isStreaming && !content ? " chat-streaming-empty" : ""}`}>
          {isUser ? (
            <span className="whitespace-pre-wrap">{content}</span>
          ) : content ? (
            <MarkdownRenderer content={content} />
          ) : null}
        </div>

        {content && !isStreaming && (
          <button className="chat-copy-btn" onClick={handleCopy} title="复制">
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
        )}
      </div>
    </div>
  );
}
