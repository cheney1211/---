
import { useState, useEffect, useRef, useCallback } from "react";
import { FileText, Terminal, Edit, Eye, Clock } from "lucide-react";

interface ConfirmationData {
  confirmation_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  description: string;
}

interface Props {
  data: ConfirmationData;
  onApprove: (allowAlways?: boolean) => void;
  onReject: () => void;
  onExpire?: () => void;
  timeoutSeconds?: number;
}

const TOOL_CONFIGS: Record<string, { label: string; icon: typeof FileText }> = {
  file_write: { label: "写入文件", icon: FileText },
  write_file: { label: "写入文件", icon: FileText },
  shell_exec: { label: "执行命令", icon: Terminal },
  bash: { label: "执行命令", icon: Terminal },
  edit_file: { label: "编辑文件", icon: Edit },
  read_file: { label: "读取文件", icon: Eye },
  calculate: { label: "计算", icon: FileText },
  get_weather: { label: "查询天气", icon: FileText },
  get_current_time: { label: "获取时间", icon: FileText },
  call_skill: { label: "调用技能", icon: FileText },
};

interface Option {
  id: number;
  title: string;
  description: string;
  action: () => void;
}

export default function ConfirmationDialog({
  data,
  onApprove,
  onReject,
  onExpire,
  timeoutSeconds = 300,
}: Props) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [remaining, setRemaining] = useState(timeoutSeconds);
  const expiredRef = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const toolConfig = TOOL_CONFIGS[data.tool_name] ?? { label: data.tool_name, icon: FileText };
  const ToolIcon = toolConfig.icon;

  const getDisplayInfo = useCallback(() => {
    const args = data.tool_args;
    if (args.path || args.file_path || args.filePath) {
      const path = (args.path || args.file_path || args.filePath) as string;
      const fileName = path.split(/[/\\]/).pop() || path;
      return { icon: <FileText size={14} />, text: fileName };
    }
    if (args.command || args.cmd) {
      const cmd = (args.command || args.cmd) as string;
      const display = cmd.length > 30 ? cmd.slice(0, 30) + "..." : cmd;
      return { icon: <Terminal size={14} />, text: display };
    }
    return { icon: <ToolIcon size={14} />, text: toolConfig.label };
  }, [data.tool_args, data.tool_name, toolConfig.label, ToolIcon]);

  const displayInfo = getDisplayInfo();

  const options: Option[] = [
    {
      id: 1,
      title: "允许",
      description: "仅允许这一次",
      action: () => onApprove(false),
    },
    {
      id: 2,
      title: "始终允许本项目",
      description: "后续相同文件操作不再询问",
      action: () => onApprove(true),
    },
    {
      id: 3,
      title: "拒绝",
      description: "这次先拒绝",
      action: onReject,
    },
  ];

  useEffect(() => {
    setRemaining(timeoutSeconds);
    expiredRef.current = false;
    setSelectedIndex(0);
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

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, options.length - 1));
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        options[selectedIndex]?.action();
      } else if (e.key === "1") {
        e.preventDefault();
        options[0]?.action();
      } else if (e.key === "2") {
        e.preventDefault();
        options[1]?.action();
      } else if (e.key === "3") {
        e.preventDefault();
        options[2]?.action();
      } else if (e.key === "Escape") {
        e.preventDefault();
        onReject();
      }
    },
    [selectedIndex, options, onReject]
  );

  const minutes = Math.floor(remaining / 60);
  const seconds = remaining % 60;
  const timerText = `${minutes}:${seconds.toString().padStart(2, "0")}`;
  const isExpired = remaining <= 0;

  return (
    <div
      className="confirmation-inline"
      ref={containerRef}
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      <div className="confirmation-inline-content">
        <div className="confirmation-inline-header">
          <span>需要权限</span>
          {!isExpired && (
            <span className="confirmation-inline-timer">
              <Clock size={12} />
              <span>{timerText}</span>
            </span>
          )}
        </div>

        <div className="confirmation-inline-tool">
          <span className="confirmation-inline-status">等待确认</span>
          <span className="confirmation-inline-detail">
            {displayInfo.icon}
            <span>{displayInfo.text}</span>
          </span>
        </div>

        {isExpired ? (
          <div className="confirmation-inline-expired">
            <span>授权超时，工具调用已被自动拒绝。</span>
          </div>
        ) : (
          <div className="confirmation-inline-options">
            {options.map((option, index) => (
              <div
                key={option.id}
                className={`confirmation-inline-option${index === selectedIndex ? " selected" : ""}`}
                onClick={option.action}
                onMouseEnter={() => setSelectedIndex(index)}
              >
                <span className="confirmation-inline-option-num">{option.id}.</span>
                <span className="confirmation-inline-option-title">{option.title}</span>
                <span className="confirmation-inline-option-desc">{option.description}</span>
              </div>
            ))}
          </div>
        )}

        {!isExpired && (
          <div className="confirmation-inline-footer">
            <span className="confirmation-inline-hint">
              使用 Tab / 上下键选择，回车确认
            </span>
            <button
              className="confirmation-inline-confirm-btn"
              onClick={options[selectedIndex]?.action}
            >
              确认
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
