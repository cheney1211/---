import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "小助手 - AI Chat",
  description: "Your AI assistant powered by LLM",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
