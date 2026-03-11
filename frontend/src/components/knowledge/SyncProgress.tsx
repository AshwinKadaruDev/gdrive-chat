import type { Project } from "@/types";

interface SyncProgressProps {
  project: Project;
}

export default function SyncProgress({ project }: SyncProgressProps) {
  const { files_processed, files_total, sync_status, sync_error } = project;

  const percentage =
    files_total > 0
      ? Math.round((files_processed / files_total) * 100)
      : 0;

  const statusLabel =
    sync_status === "SYNCING"
      ? "Downloading files from Google Drive..."
      : sync_status === "PROCESSING"
        ? "Processing and indexing documents..."
        : sync_status === "FAILED"
          ? "Sync failed"
          : "Preparing...";

  if (sync_status === "FAILED") {
    return (
      <div className="space-y-2">
        <div className="bg-red-950/30 px-3 py-2">
          <p className="text-xs font-medium text-red-400">Sync Failed</p>
          {sync_error && (
            <p className="mt-1 text-xs text-red-400/70">{sync_error}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* Status line */}
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
        <span className="text-xs text-surface-100">{statusLabel}</span>
      </div>

      {/* Progress bar */}
      {files_total > 0 && (
        <div className="space-y-1">
          <div className="h-1 w-full overflow-hidden bg-surface-800">
            <div
              className="h-full bg-brand-500 transition-all duration-500"
              style={{ width: `${percentage}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-surface-100">
            <span>
              {files_processed} of {files_total} files
            </span>
            <span>{percentage}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
