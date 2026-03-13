import { ChevronRight, Clock, CheckCircle2 } from "lucide-react";
import type { ReasoningStep } from "@/hooks/useUnifiedChat";

const TOOL_LABELS: Record<string, string> = {
  search_drive: "Searched files",
  get_file_content: "Read file",
  get_folder_structure: "Scanned folder",
  get_file_metadata: "Got file info",
  read_document_pages: "Read pages",
  search_within_file_text: "Searched in file",
  get_spreadsheet_overview: "Read spreadsheet",
  read_spreadsheet_rows: "Read rows",
  search_spreadsheet: "Searched spreadsheet",
  get_column_stats: "Computed stats",
  report_inability: "Reported inability",
  request_clarification: "Requested clarification",
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name;
}

interface ReasoningStepsProps {
  steps: ReasoningStep[];
  isCollapsed: boolean;
  onToggle: () => void;
  isLoading: boolean;
}

export default function ReasoningSteps({
  steps,
  isCollapsed,
  onToggle,
  isLoading,
}: ReasoningStepsProps) {
  if (steps.length === 0) return null;

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-surface-800/50">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs font-medium text-surface-100 transition-colors hover:text-fg-primary"
      >
        <ChevronRight
          className={`h-3 w-3 flex-shrink-0 transition-transform ${!isCollapsed ? "rotate-90" : ""}`}
        />
        <span>
          {steps.length} reasoning {steps.length === 1 ? "step" : "steps"}
        </span>
        {isLoading ? (
          <Clock className="ml-auto h-3 w-3 animate-pulse text-brand-500" />
        ) : (
          <CheckCircle2 className="ml-auto h-3 w-3 text-green-500" />
        )}
      </button>

      {!isCollapsed && (
        <div className="border-t border-[var(--border-subtle)] px-3 py-2 space-y-2">
          {steps.map((step, i) => (
            <div key={i} className="text-xs text-surface-100/80">
              <p className="leading-relaxed">{step.text}</p>
              {step.toolNames.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {step.toolNames.map((name, j) => (
                    <span
                      key={j}
                      className="inline-flex items-center rounded-md bg-brand-500/10 px-1.5 py-0.5 text-[10px] font-medium text-brand-400"
                    >
                      {toolLabel(name)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
