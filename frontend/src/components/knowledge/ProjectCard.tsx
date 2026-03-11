import { useState } from "react";
import {
  useDeleteProject,
  useSyncProject,
  useProjectSyncStatus,
} from "@/hooks/useProjects";
import SyncProgress from "./SyncProgress";
import type { Project } from "@/types";
import {
  RefreshCw,
  Trash2,
  ExternalLink,
  FileText,
  Clock,
} from "lucide-react";

interface ProjectCardProps {
  project: Project;
}

const statusConfig: Record<
  string,
  { label: string; color: string; bgColor: string }
> = {
  PENDING: {
    label: "Pending",
    color: "text-brand-500",
    bgColor: "bg-brand-500/10",
  },
  SYNCING: {
    label: "Syncing",
    color: "text-brand-500",
    bgColor: "bg-brand-500/10",
  },
  PROCESSING: {
    label: "Processing",
    color: "text-brand-500",
    bgColor: "bg-brand-500/10",
  },
  COMPLETED: {
    label: "Ready",
    color: "text-green-400",
    bgColor: "bg-green-400/10",
  },
  FAILED: {
    label: "Failed",
    color: "text-red-400",
    bgColor: "bg-red-400/10",
  },
};

export default function ProjectCard({ project }: ProjectCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteProject = useDeleteProject();
  const syncProject = useSyncProject();

  const isActive =
    project.sync_status === "SYNCING" ||
    project.sync_status === "PROCESSING";

  const { data: liveProject } = useProjectSyncStatus(
    isActive ? project.id : null
  );

  const displayProject = liveProject ?? project;
  const status = statusConfig[displayProject.sync_status] ??
    statusConfig.PENDING;

  const handleSync = () => {
    syncProject.mutate(project.id);
  };

  const handleDelete = () => {
    if (confirmDelete) {
      deleteProject.mutate(project.id);
    } else {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Never";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="card flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-white">
            {displayProject.name}
          </h3>
          {displayProject.gdrive_folder_url && (
            <a
              href={displayProject.gdrive_folder_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs text-brand-500 hover:text-brand-400"
            >
              <ExternalLink className="h-3 w-3" />
              Open in Google Drive
            </a>
          )}
        </div>
        <span
          className={`inline-flex items-center rounded px-2.5 py-1 text-xs font-medium ${status.color} ${status.bgColor}`}
        >
          {status.label}
        </span>
      </div>

      {/* Sync Progress (shown when active) */}
      {isActive && <SyncProgress project={displayProject} />}

      {/* Error display */}
      {displayProject.sync_status === "FAILED" &&
        displayProject.sync_error && (
          <div className="bg-red-950/30 px-3 py-2 text-xs text-red-400">
            {displayProject.sync_error}
          </div>
        )}

      {/* Stats */}
      <div className="flex items-center gap-4 text-xs text-surface-100">
        <span className="flex items-center gap-1">
          <FileText className="h-3.5 w-3.5 text-brand-500" />
          {displayProject.files_processed}/{displayProject.files_total} files
        </span>
        <span className="flex items-center gap-1">
          <Clock className="h-3.5 w-3.5" />
          {formatDate(displayProject.last_synced_at)}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 border-t border-white/[0.08] pt-3">
        <button
          onClick={handleSync}
          disabled={syncProject.isPending || isActive}
          className="btn-secondary flex-1 py-2 text-xs"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${
              isActive ? "animate-spin" : ""
            }`}
          />
          {isActive ? "Syncing..." : "Sync"}
        </button>
        <button
          onClick={handleDelete}
          disabled={deleteProject.isPending}
          className={`py-2 text-xs ${
            confirmDelete ? "btn-danger" : "btn-ghost text-surface-100 hover:text-red-400"
          }`}
        >
          <Trash2 className="h-3.5 w-3.5" />
          {confirmDelete ? "Confirm" : "Delete"}
        </button>
      </div>
    </div>
  );
}
