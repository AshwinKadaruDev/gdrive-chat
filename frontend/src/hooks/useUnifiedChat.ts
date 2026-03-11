import { useState, useCallback, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getChatSessions,
  getDriveChatSessions,
  getMessages,
  streamChat,
} from "@/services/api";
import type { Message, AgentType, Citation } from "@/types";

interface UseChatOptions {
  agentType: AgentType;
  projectId: string | null;
  folderId: string | null;
}

export function useUnifiedChatSessions(
  agentType: AgentType,
  projectId: string | null
) {
  return useQuery({
    queryKey:
      agentType === "RAG"
        ? ["chat-sessions", projectId]
        : ["drive-chat-sessions"],
    queryFn: () =>
      agentType === "RAG"
        ? getChatSessions(projectId!)
        : getDriveChatSessions(),
    enabled: agentType === "RAG" ? !!projectId : true,
  });
}

export function useUnifiedChat({
  agentType,
  projectId,
  folderId,
}: UseChatOptions) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const streamingContentRef = useRef("");

  const { data: existingMessages } = useQuery({
    queryKey: ["chat-messages", sessionId],
    queryFn: () => getMessages(sessionId!),
    enabled: !!sessionId,
  });

  const allMessages =
    sessionId && existingMessages ? existingMessages : messages;

  const sendMessage = useCallback(
    async (content: string) => {
      const id = agentType === "RAG" ? projectId : folderId;
      if (!id || isLoading) return;

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

      setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);
      setIsLoading(true);
      setStatusText(null);
      streamingContentRef.current = "";

      const params: Record<string, string | undefined> = {
        message: content,
        session_id: sessionId ?? undefined,
      };

      if (agentType === "RAG") {
        params.project_id = sessionId ? undefined : projectId!;
      } else {
        params.gdrive_folder_id = sessionId ? undefined : folderId!;
        params.agent_type = "drive";
      }

      try {
        await streamChat(params as Parameters<typeof streamChat>[0], {
          onSession: (newSessionId) => {
            if (!sessionId) {
              setSessionId(newSessionId);
            }
          },
          onStatus: (text) => {
            setStatusText(text);
          },
          onDelta: (text) => {
            setStatusText(null);
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
            queryClient.invalidateQueries({
              queryKey:
                agentType === "RAG"
                  ? ["chat-sessions", projectId]
                  : ["drive-chat-sessions"],
            });
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
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: "Sorry, something went wrong. Please try again." }
              : m
          )
        );
        console.error("Failed to send message:", error);
      } finally {
        setIsLoading(false);
        setStatusText(null);
      }
    },
    [agentType, projectId, folderId, sessionId, isLoading, queryClient]
  );

  const selectSession = useCallback((newSessionId: string | null) => {
    setSessionId(newSessionId);
    setMessages([]);
  }, []);

  const startNewChat = useCallback(() => {
    setSessionId(null);
    setMessages([]);
  }, []);

  return {
    messages: allMessages,
    sessionId,
    isLoading,
    statusText,
    sendMessage,
    selectSession,
    startNewChat,
  };
}
