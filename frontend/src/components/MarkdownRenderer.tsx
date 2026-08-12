"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

interface Props {
  content: string;
}

export default function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight]}
      components={{
        // Style code blocks
        pre: ({ children }) => (
          <pre className="md-code-block">{children}</pre>
        ),
        // Inline code
        code: ({ className, children, ...props }) => {
          const isBlock = className?.includes("language-");
          if (isBlock) {
            return <code className={className} {...props}>{children}</code>;
          }
          return <code className="md-inline-code" {...props}>{children}</code>;
        },
        // Links open in new tab
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
        ),
        // Tables
        table: ({ children }) => (
          <div className="md-table-wrap">
            <table>{children}</table>
          </div>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
