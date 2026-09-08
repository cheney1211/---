import { useState, useEffect } from "react";
import { Loader2, CheckCircle2 } from "lucide-react";

interface ContextIndicatorProps {
  totalTokens: number;
  maxTokens: number;
  usagePercent: number;
  isCompressing: boolean;
  compressionResult?: { freedPercent: number } | null;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function ContextIndicator({
  totalTokens,
  maxTokens,
  usagePercent,
  isCompressing,
  compressionResult,
}: ContextIndicatorProps) {
  const [showResult, setShowResult] = useState(false);

  // 压缩完成后短暂显示结果
  useEffect(() => {
    if (compressionResult && !isCompressing) {
      setShowResult(true);
      const timer = setTimeout(() => setShowResult(false), 4000);
      return () => clearTimeout(timer);
    }
  }, [compressionResult, isCompressing]);

  // 确定颜色级别
  const level =
    usagePercent >= 80 ? "danger" : usagePercent >= 60 ? "warning" : "safe";

  return (
    <div className="context-indicator">
      {/* 压缩中状态 */}
      {isCompressing && (
        <div className="context-indicator-compressing">
          <Loader2 size={12} className="context-spin-icon" />
          <span>正在压缩上下文...</span>
        </div>
      )}

      {/* 压缩完成提示 */}
      {showResult && compressionResult && !isCompressing && (
        <div className="context-indicator-compressed">
          <CheckCircle2 size={12} />
          <span>
            上下文已压缩，释放了 {compressionResult.freedPercent.toFixed(1)}% 空间
          </span>
        </div>
      )}

      {/* 正常态：进度条 + 百分比 */}
      {!isCompressing && !showResult && (
        <div className="context-indicator-bar-wrapper">
          <div className="context-indicator-bar-track">
            <div
              className={`context-indicator-bar-fill context-level-${level}`}
              style={{ width: `${Math.min(usagePercent, 100)}%` }}
            />
          </div>
          <span className={`context-indicator-text context-text-${level}`}>
            {formatTokens(totalTokens)} / {formatTokens(maxTokens)} (
            {usagePercent.toFixed(1)}%)
          </span>
        </div>
      )}
    </div>
  );
}
