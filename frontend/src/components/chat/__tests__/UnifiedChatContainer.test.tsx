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

vi.mock("@/hooks/useProjects", () => ({
  useProjects: () => ({
    data: [completedProject],
    isLoading: false,
  }),
}));

vi.mock("@/hooks/useUnifiedChat", () => ({
  useUnifiedChat: () => ({
    messages: [],
    sessionId: null,
    isLoading: false,
    sendMessage: vi.fn(),
    selectSession: vi.fn(),
    startNewChat: vi.fn(),
  }),
  useUnifiedChatSessions: () => ({
    data: [],
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
  it("renders project selector dropdown for RAG mode", () => {
    renderWith("RAG");
    expect(screen.getByText("Select a folder...")).toBeInTheDocument();
  });

  it("renders project selector dropdown for DRIVE mode", () => {
    renderWith("DRIVE");
    expect(screen.getByText("Select a folder...")).toBeInTheDocument();
  });

  it("shows empty state when no folder is selected", () => {
    renderWith("RAG");
    expect(
      screen.getByText("Select a folder to start chatting")
    ).toBeInTheDocument();
  });

  it("renders New Chat button in sidebar", () => {
    renderWith("RAG");
    expect(screen.getByText("New Chat")).toBeInTheDocument();
  });

  it("renders history label in sidebar", () => {
    renderWith("RAG");
    expect(screen.getByText("History")).toBeInTheDocument();
  });
});
