"use client";

import { useState, useEffect, useRef } from "react";
import { ShieldAlert, Check, X, Clock } from "lucide-react";

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
  onExpire?: () => void;
  timeoutSeconds?: number;
}

const TOOL_LABELS: Record<string, string> = {
  file_write: "写入文件",
  write_file: "写入文件",
  shell_exec: "执行命令行",
  bash: "执行命令行",
  edit_file: "编辑文件",
  read_file: "读取文件",
  calculate: "计算",
  get_weather: "查询天气",
  get_current_time: "获取时间",
  call_skill: "调用技能",
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

export default function ConfirmationDialog({
  data,
  onApprove,
  onReject,
  onExpire,
  timeoutSeconds = 300,
}: Props) {
  const label = TOOL_LABELS[data.tool_name] ?? data.tool_name;
  const argsText = formatArgs(data.tool_args);
  const [remaining, setRemaining] = useState(timeoutSeconds);
  const expiredRef = useRef(false);

  useEffect(() => {
    setRemaining(timeoutSeconds);
    expiredRef.current = false;
  }, [data.confirmation_id, timeoutSeconds]);

  useEffect(() => {
    if (remaining <= 0) {
      if (!expiredRef.current) {
        expiredRef.current = true;
        onExpire?.();
      }
      return;
    }
    const timer = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [remaining, onExpire]);

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  const timerText = `${minutes}:${seconds.toString().padStart(2, "0")}`;
  const isExpired = remaining <= 0;

  return (
    <div className="confirmation-overlay" onClick={onReject}>
      <div className="confirmation-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="confirmation-header">
          <ShieldAlert size={20} />
          <span>需要授权</span>
          <span className="confirmation-timer">
            <Clock size={14} />
            <span>{timerText}</span>
          </span>
        </div>

        <div className="confirmation-body">
          <p className="confirmation-tool-name">{label}</p>
          <pre className="confirmation-args">{argsText}</pre>
        </div>

        {isExpired ? (
          <div className="confirmation-expired">
            <span>授权超时，工具调用已被自动拒绝。</span>
          </div>
        ) : (
          <div className="confirmation-actions">
            <button className="confirmation-btn reject" onClick={onReject}>
              <X size={14} />
              <span>拒绝</span>
            </button>
            <button className="confirmation-btn approve" onClick={onApprove}>
              <Check size={14} />
              <span>允许</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
