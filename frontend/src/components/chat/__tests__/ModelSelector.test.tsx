import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ModelSelector from "../ModelSelector";

describe("ModelSelector", () => {
  it("renders the selected model label", () => {
    render(<ModelSelector model="gpt-5.2" onChange={vi.fn()} />);
    expect(screen.getByText("GPT 5.2")).toBeInTheDocument();
  });

  it("opens dropdown on click and shows options", () => {
    render(<ModelSelector model="gpt-5.2" onChange={vi.fn()} />);
    fireEvent.click(screen.getByText("GPT 5.2"));
    expect(screen.getByText("Opus 4.5")).toBeInTheDocument();
  });

  it("calls onChange when a model is selected", () => {
    const onChange = vi.fn();
    render(<ModelSelector model="gpt-5.2" onChange={onChange} />);
    fireEvent.click(screen.getByText("GPT 5.2"));
    fireEvent.click(screen.getByText("Opus 4.5"));
    expect(onChange).toHaveBeenCalledWith("claude-opus-4-5-20251101");
  });
});
