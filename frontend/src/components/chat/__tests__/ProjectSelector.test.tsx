import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ProjectSelector from "../ProjectSelector";
import type { Project } from "@/types";

const mockProjects: Project[] = [
  {
    id: "p1",
    name: "My Folder",
    gdrive_folder_id: "gf1",
    gdrive_folder_url: "https://drive.google.com/drive/folders/gf1",
    sync_status: "COMPLETED",
    files_total: 5,
    files_processed: 5,
    last_synced_at: "2025-01-01T00:00:00Z",
    sync_error: null,
    created_at: "2025-01-01T00:00:00Z",
  },
];

describe("ProjectSelector", () => {
  it("select has id='project-selector'", () => {
    render(
      <ProjectSelector
        projects={mockProjects}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    const select = screen.getByRole("combobox");
    expect(select).toHaveAttribute("id", "project-selector");
  });

  it("label has htmlFor='project-selector'", () => {
    render(
      <ProjectSelector
        projects={mockProjects}
        selected={null}
        onSelect={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Chat with")).toBeInTheDocument();
  });
});
