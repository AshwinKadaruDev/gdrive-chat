import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import MessageBubble from "../MessageBubble";
import type { Message, Citation } from "@/types";

// Mock useAuth to return a test user
vi.mock("@/hooks/useAuth", () => ({
  useAuth: (selector: (state: { user: { name: string } }) => unknown) =>
    selector({ user: { name: "Test User" } }),
}));

// Mock TenexLogo
vi.mock("@/components/TenexLogo", () => ({
  default: () => <span data-testid="tenex-logo">Logo</span>,
}));

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: "msg-1",
    role: "assistant",
    content: "Hello world",
    citations: null,
    created_at: "2025-01-01T12:00:00Z",
    ...overrides,
  };
}

function makeCitation(overrides: Partial<Citation> = {}): Citation {
  return {
    chunk_id: "c1",
    file_id: "f1",
    file_name: "report.pdf",
    source_url: "https://drive.google.com/file/f1",
    location: "Page 3",
    snippet: "Some relevant text",
    ...overrides,
  };
}

describe("MessageBubble", () => {
  it("renders user message text", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "What is revenue?" })}
      />
    );

    expect(screen.getByText("What is revenue?")).toBeInTheDocument();
    expect(screen.getByText("You")).toBeInTheDocument();
  });

  it("renders assistant message with markdown", () => {
    render(
      <MessageBubble
        message={makeMessage({ content: "Revenue grew **15%** year-over-year." })}
      />
    );

    expect(screen.getByText("Tenex")).toBeInTheDocument();
    // The text should be rendered (markdown parsed)
    expect(screen.getByText(/Revenue grew/)).toBeInTheDocument();
  });

  it("renders citation markers with valid citations", () => {
    const citation = makeCitation();
    render(
      <MessageBubble
        message={makeMessage({
          content: "Revenue grew 15% [1].",
          citations: [citation],
        })}
      />
    );

    // The [1] should be rendered as a citation (sup element with data-cite)
    // and the Sources collapsible should appear
    expect(screen.getByText("Sources (1)")).toBeInTheDocument();
  });

  it("does not show Sources section without citations", () => {
    render(
      <MessageBubble
        message={makeMessage({ content: "Just a plain answer." })}
      />
    );

    expect(screen.queryByText(/Sources/)).not.toBeInTheDocument();
  });

  it("does not render empty assistant messages", () => {
    const { container } = render(
      <MessageBubble message={makeMessage({ content: "" })} />
    );

    expect(container.innerHTML).toBe("");
  });

  it("renders user initial from auth state", () => {
    render(
      <MessageBubble
        message={makeMessage({ role: "user", content: "Hi" })}
      />
    );

    // "T" from "Test User"
    expect(screen.getByText("T")).toBeInTheDocument();
  });
});
