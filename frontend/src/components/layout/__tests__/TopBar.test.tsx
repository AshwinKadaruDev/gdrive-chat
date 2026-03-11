import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TopBar from "../TopBar";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "1", name: "Test User", email: "test@example.com", picture_url: null },
    logout: vi.fn(),
  }),
}));

function renderTopBar() {
  return render(
    <MemoryRouter>
      <TopBar />
    </MemoryRouter>
  );
}

describe("TopBar", () => {
  it("renders all three tabs", () => {
    renderTopBar();
    expect(screen.getByText("Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Deep Search")).toBeInTheDocument();
    expect(screen.getByText("Quick Search")).toBeInTheDocument();
  });

  it("renders correct navigation links", () => {
    renderTopBar();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveAttribute("href", "/knowledge");
    expect(links[1]).toHaveAttribute("href", "/deep-search");
    expect(links[2]).toHaveAttribute("href", "/quick-search");
  });

  it("renders user info", () => {
    renderTopBar();
    expect(screen.getByText("Test User")).toBeInTheDocument();
    expect(screen.getByText("T")).toBeInTheDocument(); // avatar fallback
  });

  it("renders sign out button", () => {
    renderTopBar();
    expect(screen.getByTitle("Sign out")).toBeInTheDocument();
  });
});
