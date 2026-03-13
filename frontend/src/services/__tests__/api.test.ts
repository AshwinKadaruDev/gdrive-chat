import { describe, it, expect, vi, afterEach } from "vitest";
import { streamChat, type StreamChatCallbacks } from "../api";

function makeCallbacks(overrides: Partial<StreamChatCallbacks> = {}): StreamChatCallbacks {
  return {
    onSession: vi.fn(),
    onStatus: vi.fn(),
    onDelta: vi.fn(),
    onCitations: vi.fn(),
    onReasoning: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

describe("streamChat SSE parsing", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("logs a warning on malformed SSE JSON", async () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    // Build a stream that sends a malformed SSE event
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode("event: delta\ndata: {not valid json}\n\n"),
        );
        controller.close();
      },
    });

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: stream,
    });

    const cbs = makeCallbacks();
    await streamChat({ message: "hi" }, cbs);

    expect(warnSpy).toHaveBeenCalled();
    const warnArgs = warnSpy.mock.calls.flat().join(" ");
    expect(warnArgs).toContain("SSE");

    warnSpy.mockRestore();
  });

  it("calls reader.cancel() when stream ends", async () => {
    const cancelMock = vi.fn().mockResolvedValue(undefined);

    const mockReader = {
      read: vi
        .fn()
        .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode("event: done\ndata: {}\n\n") })
        .mockResolvedValueOnce({ done: true, value: undefined }),
      cancel: cancelMock,
    };

    const stream = { getReader: () => mockReader };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: stream,
    });

    const cbs = makeCallbacks();
    await streamChat({ message: "hi" }, cbs);

    expect(cancelMock).toHaveBeenCalled();
  });
});
