import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import ChatInput from "../ChatInput";

describe("ChatInput", () => {
  it("textarea has aria-label 'Message input'", () => {
    render(<ChatInput onSend={vi.fn()} isLoading={false} disabled={false} model="gpt-5.2" onModelChange={vi.fn()} />);
    expect(screen.getByRole("textbox")).toHaveAttribute(
      "aria-label",
      "Message input",
    );
  });

  it("send button has aria-label 'Send message'", () => {
    render(<ChatInput onSend={vi.fn()} isLoading={false} disabled={false} model="gpt-5.2" onModelChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
  });
});
