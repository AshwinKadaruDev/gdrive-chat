import { useState, useRef, useEffect } from "react";
import { ExternalLink, FileText } from "lucide-react";
import type { Citation } from "@/types";

interface CitationTooltipProps {
  citation: Citation;
  index: number;
}

export default function CitationTooltip({
  citation,
  index,
}: CitationTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        tooltipRef.current &&
        !tooltipRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        setIsVisible(false);
      }
    };

    if (isVisible) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isVisible]);

  const handleClick = () => {
    if (citation.source_url) {
      window.open(citation.source_url, "_blank", "noopener,noreferrer");
    } else {
      setIsVisible(!isVisible);
    }
  };

  return (
    <span className="relative inline">
      <button
        ref={triggerRef}
        onClick={handleClick}
        onMouseEnter={() => setIsVisible(true)}
        onMouseLeave={() => setIsVisible(false)}
        className="relative -top-1 ml-[1px] mr-[1px] inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-brand-500/20 px-1 text-[10px] font-bold leading-none text-brand-400 transition-colors hover:bg-brand-500/40 hover:text-brand-300"
        title={citation.file_name}
      >
        {index}
      </button>

      {isVisible && (
        <div
          ref={tooltipRef}
          className="absolute bottom-full left-1/2 z-50 mb-2 w-80 -translate-x-1/2 rounded-lg border border-white/[0.08] bg-surface-850 p-3 shadow-2xl"
        >
          {/* Arrow */}
          <div className="absolute -bottom-1.5 left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 rounded-sm border-b border-r border-white/[0.08] bg-surface-850" />

          {/* File name */}
          <div className="mb-2 flex items-center gap-2">
            <FileText className="h-4 w-4 flex-shrink-0 text-brand-500" />
            <span className="truncate text-sm font-semibold text-white">
              {citation.file_name}
            </span>
          </div>

          {/* Location */}
          {citation.location && (
            <p className="mb-2 text-xs text-surface-100">{citation.location}</p>
          )}

          {/* Snippet */}
          {citation.snippet && (
            <div className="mb-3 rounded border-l-[3px] border-l-brand-500 bg-brand-500/[0.04] px-3 py-2">
              <p className="line-clamp-4 font-mono text-xs leading-relaxed text-cream">
                {citation.snippet}
              </p>
            </div>
          )}

          {/* Link */}
          {citation.source_url && (
            <a
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-500 hover:text-brand-400"
            >
              <ExternalLink className="h-3 w-3" />
              Open in Google Drive
            </a>
          )}
        </div>
      )}
    </span>
  );
}
