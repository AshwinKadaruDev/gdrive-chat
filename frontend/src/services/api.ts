import axios from "axios";
import type {
  User,
  Project,
  ChatSession,
  Message,
  SendMessageResponse,
} from "@/types";

const api = axios.create({
  baseURL: "",
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const currentPath = window.location.pathname;
      if (currentPath !== "/") {
        window.location.href = "/";
      }
    }
    return Promise.reject(error);
  }
);

// ---------- Auth ----------

export async function getCurrentUser(): Promise<User> {
  const { data } = await api.get<User>("/auth/me");
  return data;
}

export function login(): void {
  window.location.href = "/auth/google/login";
}

export async function logout(): Promise<void> {
  await api.post("/auth/logout");
}

// ---------- Projects ----------

export async function getProjects(): Promise<Project[]> {
  const { data } = await api.get<Project[]>("/api/projects");
  return data;
}

export interface FolderValidation {
  folder_id: string;
  folder_name: string;
  gdrive_folder_url: string;
}

export async function validateFolder(
  gdrive_folder_url: string
): Promise<FolderValidation> {
  const { data } = await api.post<FolderValidation>(
    "/api/projects/validate-folder",
    { gdrive_folder_url }
  );
  return data;
}

export async function createProject(
  gdrive_folder_url: string,
  name?: string
): Promise<Project> {
  const { data } = await api.post<Project>("/api/projects", {
    gdrive_folder_url,
    ...(name ? { name } : {}),
  });
  return data;
}

export async function deleteProject(projectId: string): Promise<void> {
  await api.delete(`/api/projects/${projectId}`);
}

export async function triggerSync(projectId: string): Promise<void> {
  await api.post(`/api/sync/${projectId}`);
}

export async function getSyncStatus(projectId: string): Promise<Project> {
  const { data } = await api.get<Project>(`/api/projects/${projectId}`);
  return data;
}

// ---------- Chat ----------

export async function getChatSessions(
  projectId: string
): Promise<ChatSession[]> {
  const { data } = await api.get<ChatSession[]>(
    `/api/chat/sessions/${projectId}`
  );
  return data;
}

export async function getMessages(sessionId: string): Promise<Message[]> {
  const { data } = await api.get<Message[]>(
    `/api/chat/sessions/${sessionId}/messages`
  );
  return data;
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  await api.delete(`/api/chat/sessions/${sessionId}`);
}

export async function sendMessage(
  projectId: string,
  message: string,
  sessionId?: string
): Promise<SendMessageResponse> {
  const { data } = await api.post<SendMessageResponse>(
    `/api/chat`,
    {
      message,
      session_id: sessionId,
      project_id: sessionId ? undefined : projectId,
    }
  );
  return data;
}

// ---------- Drive Chat ----------

export async function getDriveChatSessions(): Promise<ChatSession[]> {
  const { data } = await api.get<ChatSession[]>(
    `/api/chat/sessions/drive`
  );
  return data;
}

export async function sendDriveMessage(
  folderId: string,
  message: string,
  sessionId?: string
): Promise<SendMessageResponse> {
  const { data } = await api.post<SendMessageResponse>(
    `/api/chat`,
    {
      message,
      session_id: sessionId,
      gdrive_folder_id: sessionId ? undefined : folderId,
      agent_type: "drive",
    }
  );
  return data;
}

// ---------- Streaming Chat ----------

export interface StreamChatCallbacks {
  onSession: (sessionId: string) => void;
  onStatus: (text: string) => void;
  onDelta: (text: string) => void;
  onCitations: (citations: import("@/types").Citation[]) => void;
  onDone: () => void;
  onError: (error: string) => void;
}

export async function streamChat(
  params: {
    message: string;
    session_id?: string;
    project_id?: string;
    gdrive_folder_id?: string;
    agent_type?: string;
  },
  callbacks: StreamChatCallbacks
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(params),
  });

  if (!response.ok) {
    if (response.status === 401) {
      window.location.href = "/";
    }
    callbacks.onError("Failed to connect to chat service.");
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError("Streaming not supported.");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events from buffer
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // Keep incomplete line in buffer

    let eventType = "";
    let eventData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        eventData = line.slice(6);
      } else if (line === "" && eventType && eventData) {
        // End of event — dispatch
        try {
          const parsed = JSON.parse(eventData);
          switch (eventType) {
            case "session":
              callbacks.onSession(parsed.session_id);
              break;
            case "status":
              callbacks.onStatus(parsed.text);
              break;
            case "delta":
              callbacks.onDelta(parsed.text);
              break;
            case "citations":
              callbacks.onCitations(parsed);
              break;
            case "done":
              callbacks.onDone();
              break;
          }
        } catch {
          // Ignore parse errors
        }
        eventType = "";
        eventData = "";
      }
    }
  }
}

export default api;
