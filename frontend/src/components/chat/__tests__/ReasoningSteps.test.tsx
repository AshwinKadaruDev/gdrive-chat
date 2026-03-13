import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ReasoningSteps from "../ReasoningSteps";
import type { ReasoningStep } from "@/hooks/useUnifiedChat";

const STEPS: ReasoningStep[] = [
  {
    text: "Let me check the folder structure.",
    toolNames: ["get_folder_structure"],
    timestamp: 1000,
  },
  {
    text: "I found a relevant file. Let me read it.",
    toolNames: ["get_file_content"],
    timestamp: 2000,
  },
];

describe("ReasoningSteps", () => {
  it("renders nothing when steps array is empty", () => {
    const { container } = render(
      <ReasoningSteps steps={[]} isCollapsed={false} onToggle={vi.fn()} isLoading={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows step count and expanded content when not collapsed", () => {
    render(
      <ReasoningSteps steps={STEPS} isCollapsed={false} onToggle={vi.fn()} isLoading={false} />
    );
    expect(screen.getByText("2 reasoning steps")).toBeInTheDocument();
    expect(screen.getByText("Let me check the folder structure.")).toBeInTheDocument();
    expect(screen.getByText("Scanned folder")).toBeInTheDocument();
    expect(screen.getByText("Read file")).toBeInTheDocument();
  });

  it("hides content when collapsed", () => {
    render(
      <ReasoningSteps steps={STEPS} isCollapsed={true} onToggle={vi.fn()} isLoading={false} />
    );
    expect(screen.getByText("2 reasoning steps")).toBeInTheDocument();
    expect(screen.queryByText("Let me check the folder structure.")).not.toBeInTheDocument();
  });

  it("calls onToggle when header is clicked", () => {
    const onToggle = vi.fn();
    render(
      <ReasoningSteps steps={STEPS} isCollapsed={false} onToggle={onToggle} isLoading={false} />
    );
    fireEvent.click(screen.getByText("2 reasoning steps"));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("uses singular 'step' for a single reasoning step", () => {
    render(
      <ReasoningSteps steps={[STEPS[0]]} isCollapsed={false} onToggle={vi.fn()} isLoading={false} />
    );
    expect(screen.getByText("1 reasoning step")).toBeInTheDocument();
  });
});
