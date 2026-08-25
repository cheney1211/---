"use client";

import { Brain, Wrench, CheckCircle, Loader2, ShieldAlert } from "lucide-react";
import type { AgentStatus } from "@/lib/api";

interface Props {
  status: AgentStatus | null;
  visible: boolean;
}

export default function StatusIndicator({ status, visible }: Props) {
  if (!visible || !status) return null;

  let icon = <Brain size={14} />;
  let text = "思考中...";

  if (status.status === "tool_start") {
    icon = <Wrench size={14} />;
    text = `调用工具: ${status.name}`;
  } else if (status.status === "tool_end") {
    icon = <CheckCircle size={14} />;
    text = `工具完成: ${status.name}`;
  } else if (status.status === "generating") {
    icon = <Loader2 size={14} className="animate-spin" />;
    text = "输出中...";
  } else if (status.status === "confirmation_required") {
    icon = <ShieldAlert size={14} />;
    text = `等待授权: ${status.tool_name}`;
  }

  return (
    <div className="status-indicator">
      <span className="status-indicator-icon">{icon}</span>
      <span className="status-indicator-text">{text}</span>
      <span className="status-indicator-dots">
        <span />
        <span />
        <span />
      </span>
    </div>
  );
}