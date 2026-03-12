import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TopBar from "../TopBar";

const mockToggleTheme = vi.fn();
let mockTheme = "dark";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "1", name: "Test User", email: "test@example.com", picture_url: null },
    logout: vi.fn(),
  }),
}));

vi.mock("@/hooks/useTheme", () => ({
  useTheme: () => ({
    theme: mockTheme,
    toggleTheme: mockToggleTheme,
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
  it("renders both tabs", () => {
    renderTopBar();
    expect(screen.getByText("Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
  });

  it("renders correct navigation links", () => {
    renderTopBar();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "/knowledge");
    expect(links[1]).toHaveAttribute("href", "/chat");
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

  it("renders theme toggle button", () => {
    renderTopBar();
    expect(screen.getByTitle("Switch to light mode")).toBeInTheDocument();
  });

  it("calls toggleTheme when theme button is clicked", () => {
    renderTopBar();
    fireEvent.click(screen.getByTitle("Switch to light mode"));
    expect(mockToggleTheme).toHaveBeenCalledOnce();
  });
});
