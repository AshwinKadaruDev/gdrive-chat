import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { Message } from "@/types";
import { MessageSquare } from "lucide-react";

interface MessageListProps {
  messages: Message[];
  isLoading: boolean;
  statusText?: string | null;
}

export default function MessageList({ messages, isLoading, statusText }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusText]);

  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <MessageSquare className="h-10 w-10 text-surface-700" />
        <h3 className="mt-4 text-base font-medium text-surface-100">
          Start a conversation
        </h3>
        <p className="mt-1 max-w-sm text-sm text-surface-100/60">
          Ask any question about the documents in your folder.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-4 py-6"
    >
      <div className="mx-auto max-w-3xl space-y-4">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {isLoading && statusText && (
          <div className="flex items-center gap-2 py-2">
            <div className="flex items-center gap-1">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              <div
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500"
                style={{ animationDelay: "0.4s" }}
              />
              <div
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500"
                style={{ animationDelay: "0.8s" }}
              />
            </div>
            <span className="text-xs text-surface-100">
              {statusText}
            </span>
          </div>
        )}

        {isLoading && !statusText && messages.length > 0 && messages[messages.length - 1].content === "" && (
          <div className="flex items-center gap-2 py-2">
            <div className="flex items-center gap-1">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              <div
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500"
                style={{ animationDelay: "0.4s" }}
              />
              <div
                className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500"
                style={{ animationDelay: "0.8s" }}
              />
            </div>
            <span className="text-xs uppercase tracking-wider text-surface-100">
              Thinking
            </span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
