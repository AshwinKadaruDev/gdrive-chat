import { FolderOpen, ChevronDown } from "lucide-react";
import type { Project } from "@/types";

interface ProjectSelectorProps {
  projects: Project[];
  selected: Project | null;
  onSelect: (project: Project) => void;
  label?: string;
  onAddFolder?: () => void;
}

export default function ProjectSelector({
  projects,
  selected,
  onSelect,
  label = "Chat with",
  onAddFolder,
}: ProjectSelectorProps) {
  return (
    <div className="relative">
      <label className="mb-1 block text-xs font-medium text-surface-100">
        {label}
      </label>
      <div className="relative">
        <FolderOpen className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-100" />
        <select
          value={selected?.id ?? ""}
          onChange={(e) => {
            if (e.target.value === "__add_new__") {
              onAddFolder?.();
              e.target.value = selected?.id ?? "";
              return;
            }
            const project = projects.find((p) => p.id === e.target.value);
            if (project) onSelect(project);
          }}
          className="input-field appearance-none pl-9 pr-9"
        >
          <option value="" disabled>
            Select a folder...
          </option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name} ({project.files_total} files)
            </option>
          ))}
          {onAddFolder && (
            <>
              <option disabled>──────────</option>
              <option value="__add_new__">+ Add new folder...</option>
            </>
          )}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-surface-100" />
      </div>
    </div>
  );
}
