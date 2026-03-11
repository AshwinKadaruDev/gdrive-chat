import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import CitationTooltip from "./CitationTooltip";
import type { Message, Citation } from "@/types";

interface MessageBubbleProps {
  message: Message;
}

/**
 * Replace [1], [2], etc. in markdown text with citation superscript placeholders.
 * We render citations as React components after markdown parsing.
 */
function renderMarkdownWithCitations(
  content: string,
  citations: Citation[] | null
): React.ReactNode {
  if (!content) return null;

  if (!citations || citations.length === 0) {
    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    );
  }

  // Split content by citation references [1], [2], etc.
  const parts = content.split(/(\[\d+\])/g);

  return (
    <div className="markdown-body">
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
          const idx = parseInt(match[1], 10);
          const citation = citations[idx - 1];
          if (citation) {
            return (
              <CitationTooltip
                key={`cite-${i}`}
                citation={citation}
                index={idx}
              />
            );
          }
          return <sup key={`cite-${i}`} className="text-surface-100">{part}</sup>;
        }
        // Render non-citation parts as markdown
        if (!part) return null;
        return (
          <ReactMarkdown
            key={`md-${i}`}
            remarkPlugins={[remarkGfm]}
            components={markdownComponents}
          >
            {part}
          </ReactMarkdown>
        );
      })}
    </div>
  );
}

const markdownComponents = {
  // Style overrides for markdown elements
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="mb-3 last:mb-0">{children}</p>
  ),
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="mb-3 mt-4 text-lg font-bold first:mt-0">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="mb-2 mt-3 text-base font-bold first:mt-0">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="mb-2 mt-3 text-sm font-bold first:mt-0">{children}</h3>
  ),
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="mb-3 ml-4 list-disc space-y-1 last:mb-0">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="mb-3 ml-4 list-decimal space-y-1 last:mb-0">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="leading-relaxed">{children}</li>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-white">{children}</strong>
  ),
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
    const isBlock = className?.startsWith("language-");
    if (isBlock) {
      return (
        <code className="block overflow-x-auto rounded bg-surface-800 p-3 font-mono text-xs leading-relaxed">
          {children}
        </code>
      );
    }
    return (
      <code className="rounded bg-surface-800 px-1.5 py-0.5 font-mono text-xs">
        {children}
      </code>
    );
  },
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="mb-3 last:mb-0">{children}</pre>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="mb-3 border-l-[3px] border-l-brand-500 pl-3 italic text-surface-100 last:mb-0">
      {children}
    </blockquote>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="border border-white/[0.08] bg-surface-800 px-3 py-1.5 text-left text-xs font-semibold">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border border-white/[0.08] px-3 py-1.5 text-xs">{children}</td>
  ),
};

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  const renderedContent = useMemo(
    () =>
      isUser
        ? message.content
        : renderMarkdownWithCitations(message.content, message.citations),
    [message.content, message.citations, isUser]
  );

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[70%] rounded-lg border border-white/[0.08] bg-surface-850 px-4 py-3">
          <div className="whitespace-pre-wrap text-[15px] leading-relaxed text-white">
            {renderedContent}
          </div>
          <p className="mt-1 text-right text-[10px] text-surface-100/50">
            {new Date(message.created_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        </div>
      </div>
    );
  }

  // Don't render empty assistant messages (placeholder before streaming starts)
  if (!message.content) return null;

  return (
    <div>
      <div className="py-1">
        <div className="text-[15px] leading-relaxed text-cream">
          {renderedContent}
        </div>

        {/* Citation sources footer */}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-3 border-t border-white/[0.08] pt-2">
            <p className="text-xs font-medium text-surface-100">
              Sources ({message.citations.length})
            </p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {message.citations.map((citation, i) => (
                <CitationTooltip
                  key={`summary-${citation.chunk_id || citation.file_id}-${i}`}
                  citation={citation}
                  index={i + 1}
                />
              ))}
            </div>
          </div>
        )}

        <p className="mt-1 text-[10px] text-surface-100/50">
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}
