"use client";

import { ShieldAlert, Check, X } from "lucide-react";

interface ConfirmationData {
  confirmation_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  description: string;
}

interface Props {
  data: ConfirmationData;
  onApprove: () => void;
  onReject: () => void;
}

const TOOL_LABELS: Record<string, string> = {
  file_write: "写入文件",
  shell_exec: "执行命令行",
};

function formatArgs(args: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(args)) {
    if (typeof value === "string" && value.length > 200) {
      parts.push(`${key}: ${value.slice(0, 200)}...`);
    } else {
      parts.push(`${key}: ${JSON.stringify(value)}`);
    }
  }
  return parts.join("\n");
}

export default function ConfirmationDialog({ data, onApprove, onReject }: Props) {
  const label = TOOL_LABELS[data.tool_name] ?? data.tool_name;
  const argsText = formatArgs(data.tool_args);

  return (
    <div className="confirmation-overlay">
      <div className="confirmation-dialog">
        <div className="confirmation-header">
          <ShieldAlert size={20} />
          <span>Authorization Required</span>
        </div>

        <div className="confirmation-body">
          <p className="confirmation-tool-name">{label}</p>
          <pre className="confirmation-args">{argsText}</pre>
        </div>

        <div className="confirmation-actions">
          <button className="confirmation-btn reject" onClick={onReject}>
            <X size={14} />
            <span>Reject</span>
          </button>
          <button className="confirmation-btn approve" onClick={onApprove}>
            <Check size={14} />
            <span>Approve</span>
          </button>
        </div>
      </div>
    </div>
  );
}