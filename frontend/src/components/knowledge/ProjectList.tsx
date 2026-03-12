import { useState, useRef } from "react";
import { useProjects } from "@/hooks/useProjects";
import ProjectCard from "./ProjectCard";
import AddFolderModal from "./AddFolderModal";
import { FolderPlus, FolderOpen } from "lucide-react";

export default function ProjectList() {
  const [showModal, setShowModal] = useState(false);
  const addFolderBtnRef = useRef<HTMLButtonElement>(null);
  const { data: projects, isLoading, error } = useProjects();

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-fg-primary">Knowledge Base</h2>
            <p className="mt-1 text-sm text-surface-100">
              Connect Google Drive folders to build your searchable knowledge
              base.
            </p>
          </div>
          <button
            ref={addFolderBtnRef}
            onClick={() => setShowModal(true)}
            className="btn-primary"
          >
            <FolderPlus className="h-4 w-4" />
            Add Folder
          </button>
        </div>

        {/* Content */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              <div
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500"
                style={{ animationDelay: "0.4s" }}
              />
              <div
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500"
                style={{ animationDelay: "0.8s" }}
              />
            </div>
            <p className="mt-3 text-sm text-surface-100">
              Loading projects...
            </p>
          </div>
        )}

        {error && (
          <div className="card border-red-900/50 text-center">
            <p className="text-sm text-red-400">
              Failed to load projects. Please try again.
            </p>
          </div>
        )}

        {!isLoading && !error && projects?.length === 0 && (
          <div className="flex flex-col items-center justify-center border-2 border-dashed border-[var(--border-subtle)] py-20">
            <FolderOpen className="h-12 w-12 text-surface-700" />
            <h3 className="mt-4 text-base font-medium text-surface-100">
              No folders connected
            </h3>
            <p className="mt-2 text-sm text-surface-100/60">
              Add a Google Drive folder to get started.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="btn-primary mt-6"
            >
              <FolderPlus className="h-4 w-4" />
              Add your first folder
            </button>
          </div>
        )}

        {projects && projects.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {projects.map((project) => (
              <ProjectCard key={project.id} project={project} />
            ))}
          </div>
        )}

        {/* Modal */}
        {showModal && (
          <AddFolderModal onClose={() => setShowModal(false)} triggerRef={addFolderBtnRef} />
        )}
      </div>
    </div>
  );
}
