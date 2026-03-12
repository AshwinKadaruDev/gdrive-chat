import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  disabled: boolean;
}

export default function ChatInput({
  onSend,
  isLoading,
  disabled,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || isLoading || disabled) return;
    onSend(trimmed);
    setValue("");
    // Reset height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="mx-auto max-w-3xl">
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-surface-800 px-4 pb-3 pt-3 shadow-lg shadow-black/10 dark:shadow-black/20">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents..."
            disabled={isLoading || disabled}
            rows={1}
            aria-label="Message input"
            className="max-h-[7.5rem] min-h-[1.75rem] w-full resize-none bg-transparent text-[15px] leading-relaxed text-fg-primary placeholder-surface-100/60 focus:outline-none disabled:opacity-50"
          />
          <div className="flex items-center justify-between pt-2">
            <p className="text-[11px] text-surface-100/40">
              Enter to send, Shift + Enter for new line
            </p>
            <button
              onClick={handleSubmit}
              disabled={!value.trim() || isLoading || disabled}
              aria-label="Send message"
              className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-fg-primary text-fg-inverted transition-colors hover:bg-brand-500 disabled:opacity-30"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
