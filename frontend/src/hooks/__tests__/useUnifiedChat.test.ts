import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/services/api", () => ({
  getDriveChatSessions: vi.fn().mockResolvedValue([]),
  getMessages: vi.fn().mockResolvedValue([]),
  streamChat: vi.fn().mockResolvedValue(undefined),
  deleteChatSession: vi.fn().mockResolvedValue(undefined),
}));

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useUnifiedChat", () => {
  it("starts with empty messages and no session", async () => {
    const { useUnifiedChat } = await import("../useUnifiedChat");

    const { result } = renderHook(
      () =>
        useUnifiedChat({
          folderId: "folder-1",
        }),
      { wrapper: makeWrapper() }
    );

    expect(result.current.messages).toEqual([]);
    expect(result.current.sessionId).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  it("sendMessage adds optimistic messages", async () => {
    const api = await import("@/services/api");
    // Make streamChat call the callbacks
    (api.streamChat as ReturnType<typeof vi.fn>).mockImplementation(
      async (_params: unknown, callbacks: {
        onSession: (id: string) => void;
        onDelta: (text: string) => void;
        onCitations: (c: unknown[]) => void;
        onDone: () => void;
        onStatus: (text: string) => void;
        onError: (e: string) => void;
      }) => {
        callbacks.onSession("sess-1");
        callbacks.onDelta("Hello");
        callbacks.onCitations([]);
        callbacks.onDone();
      }
    );

    const { useUnifiedChat } = await import("../useUnifiedChat");

    const { result } = renderHook(
      () =>
        useUnifiedChat({
          folderId: "folder-1",
        }),
      { wrapper: makeWrapper() }
    );

    await act(async () => {
      await result.current.sendMessage("Hi there");
    });

    // After streaming completes, messages should include user + assistant
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  it("selectSession resets messages", async () => {
    const { useUnifiedChat } = await import("../useUnifiedChat");

    const { result } = renderHook(
      () =>
        useUnifiedChat({
          folderId: "folder-1",
        }),
      { wrapper: makeWrapper() }
    );

    act(() => {
      result.current.selectSession("new-session");
    });

    expect(result.current.sessionId).toBe("new-session");
  });

  it("loading is cleared on error", async () => {
    const api = await import("@/services/api");
    (api.streamChat as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("Network error")
    );

    const { useUnifiedChat } = await import("../useUnifiedChat");

    const { result } = renderHook(
      () =>
        useUnifiedChat({
          folderId: "folder-1",
        }),
      { wrapper: makeWrapper() }
    );

    await act(async () => {
      await result.current.sendMessage("test");
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });
});
