import { Minus, Square, X, Copy } from "lucide-react";
import { useState } from "react";

export default function TitleBar() {
  const [isMaximized, setIsMaximized] = useState(false);

  const handleMinimize = () => {
    window.electronAPI?.minimizeWindow();
  };

  const handleMaximize = () => {
    window.electronAPI?.maximizeWindow();
    setIsMaximized((v) => !v);
  };

  const handleClose = () => {
    window.electronAPI?.closeWindow();
  };

  return (
    <div className="title-bar">
      <div className="title-bar-drag">
        <span className="title-bar-text">Coco AI 助手</span>
      </div>
      <div className="title-bar-controls">
        <button
          className="title-bar-btn minimize"
          onClick={handleMinimize}
          title="最小化"
        >
          <Minus size={14} />
        </button>
        <button
          className="title-bar-btn maximize"
          onClick={handleMaximize}
          title={isMaximized ? "还原" : "最大化"}
        >
          {isMaximized ? <Copy size={12} /> : <Square size={12} />}
        </button>
        <button
          className="title-bar-btn close"
          onClick={handleClose}
          title="关闭"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
