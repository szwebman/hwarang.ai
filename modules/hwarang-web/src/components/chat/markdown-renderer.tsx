"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./code-block";

interface MarkdownRendererProps {
  content: string;
  /** HSEE Phase 1 — code copy 신호를 추적할 메시지 id (assistant 메시지 한정) */
  messageId?: string;
}

export function MarkdownRenderer({ content, messageId }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const isInline = !match;

          if (isInline) {
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          }

          return (
            <CodeBlock
              language={match[1]}
              code={String(children).replace(/\n$/, "")}
              messageId={messageId}
            />
          );
        },
        // Remove wrapping <p> in tight lists
        p({ children }) {
          return <p className="mb-3 last:mb-0">{children}</p>;
        },
        ul({ children }) {
          return <ul className="list-disc pl-5 mb-3">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="list-decimal pl-5 mb-3">{children}</ol>;
        },
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
              style={{ color: "var(--primary)" }}
            >
              {children}
            </a>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
