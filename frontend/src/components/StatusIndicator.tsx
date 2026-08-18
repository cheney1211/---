"use client";

import { Brain, Wrench, CheckCircle, Loader2 } from "lucide-react";
import type { AgentStatus } from "@/lib/api";

interface Props {
  status: AgentStatus | null;
  visible: boolean;
}

export default function StatusIndicator({ status, visible }: Props) {
  console.log("[Indicator]", visible, status?.status, status);
  if (!visible || !status) return null;

  let icon = <Brain size={14} />;
  let text = "正在思考";

  if (status.status === "tool_start") {
    icon = <Wrench size={14} />;
    text = `调用工具: ${status.name}`;
  } else if (status.status === "tool_end") {
    icon = <CheckCircle size={14} />;
    text = `工具完成: ${status.name}`;
  } else if (status.status === "generating") {
    icon = <Loader2 size={14} className="animate-spin" />;
    text = "正在输出";
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
