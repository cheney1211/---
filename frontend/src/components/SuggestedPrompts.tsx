"use client";

import { Code, BookOpen, Lightbulb, PenTool } from "lucide-react";

const PROMPTS = [
  { icon: Code, text: "帮我写一段 Python 快排", label: "写代码" },
  { icon: BookOpen, text: "用简单的话解释什么是闭包", label: "解释概念" },
  { icon: Lightbulb, text: "给我 3 个周末活动建议", label: "出主意" },
  { icon: PenTool, text: "帮我润色一段工作邮件", label: "写文案" },
];

interface Props {
  onSelect: (text: string) => void;
}

export default function SuggestedPrompts({ onSelect }: Props) {
  return (
    <div className="suggested-prompts">
      <div className="suggested-hero">
        <div className="suggested-avatar">C</div>
        <h2>你好，我是 Coco</h2>
        <p>有什么我可以帮你的？</p>
      </div>
      <div className="suggested-grid">
        {PROMPTS.map((p) => (
          <button
            key={p.label}
            className="suggested-card"
            onClick={() => onSelect(p.text)}
          >
            <p.icon size={18} className="suggested-card-icon" />
            <span className="suggested-card-label">{p.label}</span>
            <span className="suggested-card-text">{p.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
