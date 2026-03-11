import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import UnifiedChatContainer from "../UnifiedChatContainer";

const completedProject = {
  id: "p1",
  name: "My Folder",
  gdrive_folder_id: "gf1",
  gdrive_folder_url: "https://drive.google.com/drive/folders/gf1",
  sync_status: "COMPLETED" as const,
  files_total: 5,
  files_processed: 5,
  last_synced_at: "2025-01-01T00:00:00Z",
  sync_error: null,
  created_at: "2025-01-01T00:00:00Z",
};

const mockUseProjects = vi.fn(() => ({
  data: [completedProject],
  isLoading: false,
}));

vi.mock("@/hooks/useProjects", () => ({
  useProjects: () => mockUseProjects(),
  useCreateProject: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false }),
  useValidateFolder: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useUnifiedChat", () => ({
  useUnifiedChat: () => ({
    messages: [],
    sessionId: null,
    isLoading: false,
    statusText: null,
    sendMessage: vi.fn(),
    selectSession: vi.fn(),
    startNewChat: vi.fn(),
  }),
  useUnifiedChatSessions: () => ({
    data: [],
  }),
  useDeleteChatSession: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/services/api", () => ({
  getProjects: vi.fn().mockResolvedValue([]),
}));

function renderWith(agentType: "RAG" | "DRIVE") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <UnifiedChatContainer agentType={agentType} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("UnifiedChatContainer", () => {
  it("renders folder picker for RAG mode", () => {
    renderWith("RAG");
    expect(screen.getByText("What would you like to chat about?")).toBeInTheDocument();
    expect(screen.getByText("My Folder")).toBeInTheDocument();
  });

  it("renders folder picker for DRIVE mode", () => {
    renderWith("DRIVE");
    expect(screen.getByText("What would you like to chat about?")).toBeInTheDocument();
  });

  it("shows add new folder option in picker", () => {
    renderWith("RAG");
    expect(screen.getByText("Add new folder...")).toBeInTheDocument();
  });

  it("renders New Chat button in sidebar", () => {
    renderWith("RAG");
    expect(screen.getByText("New Chat")).toBeInTheDocument();
  });

  it("renders history label in sidebar", () => {
    renderWith("RAG");
    expect(screen.getByText("History")).toBeInTheDocument();
  });

  it("shows add-folder CTA when no qualified projects exist", () => {
    mockUseProjects.mockReturnValue({ data: [], isLoading: false });
    renderWith("DRIVE");
    expect(screen.getByText("No folders connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add a folder/i })).toBeInTheDocument();
    mockUseProjects.mockReturnValue({ data: [completedProject], isLoading: false });
  });

  it("renders 'Add new folder' option in folder picker", () => {
    renderWith("DRIVE");
    expect(screen.getByText("Add new folder...")).toBeInTheDocument();
  });
});
