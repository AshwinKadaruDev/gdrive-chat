import { useState, useCallback, useRef } from "react";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import {
  getDriveChatSessions,
  getMessages,
  streamChat,
  deleteChatSession,
} from "@/services/api";
import type { Message, Citation } from "@/types";

export interface ReasoningStep {
  text: string;
  toolNames: string[];
  timestamp: number;
}

interface UseChatOptions {
  folderId: string | null;
  model?: string;
}

export function useUnifiedChatSessions() {
  return useQuery({
    queryKey: ["drive-chat-sessions"],
    queryFn: () => getDriveChatSessions(),
  });
}

export function useUnifiedChat({ folderId, model }: UseChatOptions) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [reasoningSteps, setReasoningSteps] = useState<ReasoningStep[]>([]);
  const [isReasoningCollapsed, setIsReasoningCollapsed] = useState(false);
  const queryClient = useQueryClient();
  const streamingContentRef = useRef("");
  const streamingSessionIdRef = useRef<string | null>(null);
  const existingMessagesRef = useRef<Message[] | undefined>(undefined);
  const sendingRef = useRef(false);

  const { data: existingMessages } = useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: () => getMessages(sessionId!),
    enabled: !!sessionId,
  });

  // Keep ref in sync so sendMessage can read the latest value
  existingMessagesRef.current = existingMessages;

  // Reset chat state when the active folder changes
  const prevIdRef = useRef(folderId);
  if (prevIdRef.current !== folderId) {
    prevIdRef.current = folderId;
    setSessionId(null);
    setMessages([]);
  }

  // During streaming, always use local messages (which include streaming content).
  // Otherwise, prefer server data for existing sessions.
  const allMessages = isLoading
    ? messages
    : sessionId && existingMessages
      ? existingMessages
      : messages;

  const sendMessage = useCallback(
    async (content: string) => {
      if (!folderId || isLoading) return;
      if (sendingRef.current) return;
      sendingRef.current = true;

      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content,
        citations: null,
        created_at: new Date().toISOString(),
      };

      // Add user message + placeholder assistant message
      const assistantId = `assistant-${Date.now()}`;
      const assistantPlaceholder: Message = {
        id: assistantId,
        role: "assistant",
        content: "",
        citations: null,
        created_at: new Date().toISOString(),
      };

      // Seed with existing history for follow-up messages in an existing session
      const base =
        sessionId && existingMessagesRef.current
          ? existingMessagesRef.current
          : [];
      setMessages([...base, userMessage, assistantPlaceholder]);
      setIsLoading(true);
      setStatusText(null);
      setReasoningSteps([]);
      setIsReasoningCollapsed(false);
      streamingContentRef.current = "";

      const params: Record<string, string | undefined> = {
        message: content,
        session_id: sessionId ?? undefined,
        gdrive_folder_id: sessionId ? undefined : folderId!,
        model,
      };

      try {
        await streamChat(params as Parameters<typeof streamChat>[0], {
          onSession: (newSessionId) => {
            // Store in ref during streaming — don't update state yet.
            // Setting sessionId now would switch allMessages to the
            // (still-empty) existingMessages query, hiding streaming content.
            streamingSessionIdRef.current = newSessionId;
          },
          onStatus: (text) => {
            setStatusText(text);
          },
          onReasoning: (text, toolNames) => {
            setReasoningSteps((prev) => [
              ...prev,
              { text, toolNames, timestamp: Date.now() },
            ]);
          },
          onDelta: (text) => {
            setStatusText(null);
            setIsReasoningCollapsed(true);
            streamingContentRef.current += text;
            const currentContent = streamingContentRef.current;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: currentContent }
                  : m
              )
            );
          },
          onCitations: (citations: Citation[]) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, citations: citations.length > 0 ? citations : null }
                  : m
              )
            );
          },
          onDone: () => {
            // Commit the session ID now that streaming is complete
            const newId = streamingSessionIdRef.current;
            if (newId) {
              setSessionId(newId);
              streamingSessionIdRef.current = null;
            }
            queryClient.invalidateQueries({
              queryKey: ["drive-chat-sessions"],
            });
            // Invalidate messages so fresh data loads when we switch
            // from local messages back to existingMessages
            const sid = sessionId ?? newId;
            if (sid) {
              queryClient.invalidateQueries({
                queryKey: ["chat-messages", sid],
              });
            }
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: error || "Something went wrong." }
                  : m
              )
            );
          },
        });
      } catch (error) {
        const errorMsg = error instanceof TypeError
          ? "Network error — please check your connection and try again."
          : "Sorry, something went wrong. Please try again.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: errorMsg }
              : m
          )
        );
        console.error("Failed to send message:", error);
      } finally {
        sendingRef.current = false;
        setIsLoading(false);
        setStatusText(null);
      }
    },
    [folderId, sessionId, isLoading, queryClient, model]
  );

  const selectSession = useCallback((newSessionId: string | null) => {
    setSessionId(newSessionId);
    setMessages([]);
    setReasoningSteps([]);
  }, []);

  const startNewChat = useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setReasoningSteps([]);
  }, []);

  return {
    messages: allMessages,
    sessionId,
    isLoading,
    statusText,
    reasoningSteps,
    isReasoningCollapsed,
    setIsReasoningCollapsed,
    sendMessage,
    selectSession,
    startNewChat,
  };
}

export function useDeleteChatSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => deleteChatSession(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["drive-chat-sessions"],
      });
    },
  });
}
