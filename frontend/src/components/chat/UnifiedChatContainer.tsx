import { useState } from "react";
import { useProjects } from "@/hooks/useProjects";
import {
  useUnifiedChat,
  useUnifiedChatSessions,
} from "@/hooks/useUnifiedChat";
import ProjectSelector from "./ProjectSelector";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import AddFolderModal from "@/components/knowledge/AddFolderModal";
import { MessageSquare, Plus, Clock, FolderPlus } from "lucide-react";
import type { Project, AgentType, ChatSession } from "@/types";

interface Props {
  agentType: AgentType;
}

export default function UnifiedChatContainer({ agentType }: Props) {
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const { data: projects, isLoading: projectsLoading } = useProjects();

  const projectId = selectedProject?.id ?? null;
  const folderId = selectedProject?.gdrive_folder_id ?? null;

  const {
    messages,
    sessionId,
    isLoading: chatLoading,
    statusText,
    sendMessage,
    selectSession,
    startNewChat,
  } = useUnifiedChat({ agentType, projectId, folderId });

  const { data: sessions } = useUnifiedChatSessions(agentType, projectId);

  const qualifiedProjects =
    agentType === "RAG"
      ? (projects?.filter((p) => p.sync_status === "COMPLETED") ?? [])
      : (projects?.filter((p) => !!p.gdrive_folder_id) ?? []);

  // For DRIVE mode, filter sessions to the selected folder
  const filteredSessions: ChatSession[] =
    agentType === "DRIVE" && folderId
      ? (sessions?.filter((s) => s.gdrive_folder_id === folderId) ?? [])
      : (sessions ?? []);

  if (projectsLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2">
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
      </div>
    );
  }

  if (qualifiedProjects.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <MessageSquare className="h-12 w-12 text-surface-700" />
        <h3 className="mt-4 text-base font-medium text-surface-100">
          No folders connected
        </h3>
        <p className="mt-2 max-w-sm text-sm text-surface-100/60">
          Connect a Google Drive folder to start searching your documents.
        </p>
        <button
          onClick={() => setShowAddModal(true)}
          className="btn-primary mt-6"
        >
          <FolderPlus className="h-4 w-4" />
          Add a folder
        </button>
        {showAddModal && (
          <AddFolderModal
            onClose={() => setShowAddModal(false)}
            onCreated={(project) => setSelectedProject(project)}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Sidebar: Session History */}
      <div className="hidden w-[280px] flex-col border-r border-[var(--border-subtle)] bg-surface-850 lg:flex">
        <div className="border-b border-[var(--border-subtle)] p-4">
          <button
            onClick={startNewChat}
            className="btn-primary w-full py-2 text-sm"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-4">
          <p className="mb-2 px-6 text-[11px] font-semibold uppercase tracking-[0.08em] text-surface-100">
            History
          </p>
          {filteredSessions.length > 0 ? (
            <div className="space-y-0.5">
              {filteredSessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => selectSession(session.id)}
                  className={`w-full border-l-[3px] px-6 py-2.5 text-left text-sm transition-colors ${
                    sessionId === session.id
                      ? "border-l-brand-500 bg-brand-500/[0.06] text-fg-primary"
                      : "border-l-transparent text-cream hover:bg-[var(--hover-overlay)]"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-3.5 w-3.5 flex-shrink-0" />
                    <span className="truncate">
                      {session.title ?? "Untitled"}
                    </span>
                  </div>
                  <div className="ml-5 mt-0.5 flex items-center gap-1 text-xs text-surface-100">
                    <Clock className="h-3 w-3" />
                    {new Date(session.created_at).toLocaleDateString()}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="px-6 py-4 text-center text-xs text-surface-100">
              No conversations yet
            </p>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex flex-1 flex-col bg-surface-950">
        {/* Project Selector Bar */}
        <div className="border-b border-[var(--border-subtle)] px-4 py-3">
          <ProjectSelector
            projects={qualifiedProjects}
            selected={selectedProject}
            onSelect={setSelectedProject}
            onAddFolder={() => setShowAddModal(true)}
          />
        </div>

        {!selectedProject ? (
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <MessageSquare className="h-10 w-10 text-surface-700" />
            <h3 className="mt-4 text-base font-medium text-surface-100">
              Select a folder to start chatting
            </h3>
            <p className="mt-1 text-sm text-surface-100/60">
              Choose a folder from the dropdown above.
            </p>
          </div>
        ) : (
          <>
            <MessageList messages={messages} isLoading={chatLoading} statusText={statusText} />
            <ChatInput
              onSend={sendMessage}
              isLoading={chatLoading}
              disabled={!selectedProject}
            />
          </>
        )}
      </div>

      {showAddModal && (
        <AddFolderModal
          onClose={() => setShowAddModal(false)}
          onCreated={(project) => setSelectedProject(project)}
        />
      )}
    </div>
  );
}
