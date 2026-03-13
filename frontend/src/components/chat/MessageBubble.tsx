import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import CitationTooltip from "./CitationTooltip";
import ReasoningSteps from "./ReasoningSteps";
import TenexLogo from "@/components/TenexLogo";
import { useAuth } from "@/hooks/useAuth";
import type { Message, Citation } from "@/types";
import type { ReasoningStep } from "@/hooks/useUnifiedChat";

const citationSanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "sup"],
  attributes: { ...defaultSchema.attributes, sup: ["data-cite"] },
};

interface MessageBubbleProps {
  message: Message;
  reasoningSteps?: ReasoningStep[];
  isReasoningCollapsed?: boolean;
  onReasoningToggle?: () => void;
  isReasoningLoading?: boolean;
}

const markdownComponents = {
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
    <strong className="font-medium">{children}</strong>
  ),
  code: ({
    children,
    className,
  }: {
    children?: React.ReactNode;
    className?: string;
  }) => {
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
    <th className="border border-[var(--border-subtle)] bg-surface-800 px-3 py-1.5 text-left text-xs font-semibold">
      {children}
    </th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="border border-[var(--border-subtle)] px-3 py-1.5 text-xs">
      {children}
    </td>
  ),
};

/**
 * Build markdown components that include a citation-aware `sup` override.
 * `<sup data-cite="N">` tags injected into the markdown source are rendered
 * as interactive CitationTooltip components when a matching citation exists.
 */
function buildComponents(citations: Citation[] | null) {
  if (!citations || citations.length === 0) return markdownComponents;

  return {
    ...markdownComponents,
    sup: (props: React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }) => {
      const citeAttr = (props as Record<string, unknown>)["data-cite"];
      if (typeof citeAttr === "string") {
        const idx = parseInt(citeAttr, 10);
        const citation = citations[idx - 1];
        if (citation) {
          return <CitationTooltip citation={citation} index={idx} />;
        }
      }
      return <sup>{props.children}</sup>;
    },
  };
}

/**
 * Replace `[1]`, `[2]`, etc. with `<sup data-cite="N">N</sup>` so they
 * pass through rehype-raw as inline HTML inside the markdown AST — keeping
 * them on the same line as the surrounding text.
 */
function injectCitationMarkers(content: string): string {
  return content.replace(
    /\[(\d+)\]/g,
    '<sup data-cite="$1">$1</sup>'
  );
}

function SourcesCollapsible({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-3 border-t border-[var(--border-subtle)] pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-surface-100 hover:text-fg-primary transition-colors"
      >
        <svg
          className={`h-3 w-3 transition-transform ${open ? "rotate-90" : ""}`}
          viewBox="0 0 12 12"
          fill="currentColor"
        >
          <path d="M4.5 2l4 4-4 4V2z" />
        </svg>
        Sources ({citations.length})
      </button>
      {open && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {citations.map((citation, i) => (
            <CitationTooltip
              key={`summary-${citation.chunk_id || citation.file_id}-${i}`}
              citation={citation}
              index={i + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ message, reasoningSteps, isReasoningCollapsed, onReasoningToggle, isReasoningLoading }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const user = useAuth((s) => s.user);

  const renderedContent = useMemo(() => {
    if (isUser) return message.content;
    if (!message.content) return null;

    const hasCitations =
      message.citations && message.citations.length > 0;
    const source = hasCitations
      ? injectCitationMarkers(message.content)
      : message.content;
    const components = buildComponents(message.citations);

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={hasCitations ? [rehypeRaw, [rehypeSanitize, citationSanitizeSchema]] : []}
        components={components}
      >
        {source}
      </ReactMarkdown>
    );
  }, [message.content, message.citations, isUser]);

  const timestamp = new Date(message.created_at).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  if (isUser) {
    const initial = user?.name?.charAt(0)?.toUpperCase() ?? "?";
    return (
      <div className="group flex flex-col items-end">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-[10px] text-surface-100/50 opacity-0 transition-opacity group-hover:opacity-100">
            {timestamp}
          </span>
          <span className="text-xs text-surface-100">You</span>
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-surface-700 text-[10px] font-medium text-fg-primary">
            {initial}
          </div>
        </div>
        <div className="max-w-[85%] rounded-lg border border-[var(--border-subtle)] bg-surface-850 px-4 py-3">
          <div className="whitespace-pre-wrap text-[15px] leading-relaxed text-fg-primary">
            {renderedContent}
          </div>
        </div>
      </div>
    );
  }

  // Don't render empty assistant messages (placeholder before streaming starts)
  if (!message.content) return null;

  return (
    <div className="group">
      <div className="mb-1 flex items-center gap-2">
        <TenexLogo showWordmark={false} iconSize={16} />
        <span className="text-xs text-surface-100">Tenex</span>
        <span className="text-[10px] text-surface-100/50 opacity-0 transition-opacity group-hover:opacity-100">
          {timestamp}
        </span>
      </div>
      {reasoningSteps && reasoningSteps.length > 0 && onReasoningToggle && (
        <div className="mb-2">
          <ReasoningSteps
            steps={reasoningSteps}
            isCollapsed={isReasoningCollapsed ?? false}
            onToggle={onReasoningToggle}
            isLoading={isReasoningLoading ?? false}
          />
        </div>
      )}
      <div className="py-1">
        <div className="text-[15px] leading-relaxed text-cream">
          {renderedContent}
        </div>

        {/* Collapsible citation sources */}
        {message.citations && message.citations.length > 0 && (
          <SourcesCollapsible citations={message.citations} />
        )}
      </div>
    </div>
  );
}
