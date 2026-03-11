import { useState } from "react";
import { useProjects } from "@/hooks/useProjects";
import {
  useUnifiedChat,
  useUnifiedChatSessions,
  useDeleteChatSession,
} from "@/hooks/useUnifiedChat";
import ProjectSelector from "./ProjectSelector";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import AddFolderModal from "@/components/knowledge/AddFolderModal";
import {
  MessageSquare,
  Plus,
  FolderPlus,
  FolderOpen,
  Trash2,
  Search,
} from "lucide-react";
import type { Project, AgentType, ChatSession } from "@/types";

interface Props {
  agentType: AgentType;
}

export default function UnifiedChatContainer({ agentType }: Props) {
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [folderSearch, setFolderSearch] = useState("");
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
  const deleteMutation = useDeleteChatSession(agentType, projectId);

  const qualifiedProjects =
    agentType === "RAG"
      ? (projects?.filter((p) => p.sync_status === "COMPLETED") ?? [])
      : (projects?.filter((p) => !!p.gdrive_folder_id) ?? []);

  // Show all sessions in sidebar (folder indicator tells user which folder)
  const allSessions: ChatSession[] = sessions ?? [];

  // Lock folder selector once a conversation is active
  const folderLocked = sessionId !== null;

  // Lookup maps for folder names in the sidebar
  const projectsByFolderId = new Map(
    (projects ?? []).map((p) => [p.gdrive_folder_id, p])
  );
  const projectsById = new Map(
    (projects ?? []).map((p) => [p.id, p])
  );

  function handleSelectSession(session: ChatSession) {
    // Auto-select the folder this conversation belongs to
    const project =
      agentType === "DRIVE"
        ? projectsByFolderId.get(session.gdrive_folder_id ?? "")
        : projectsById.get(session.project_id ?? "");
    if (project) setSelectedProject(project);
    selectSession(session.id);
  }

  function handleNewChat() {
    startNewChat();
    setSelectedProject(null);
  }

  function handleDeleteSession(e: React.MouseEvent, session: ChatSession) {
    e.stopPropagation();
    deleteMutation.mutate(session.id);
    if (sessionId === session.id) {
      handleNewChat();
    }
  }

  function getFolderName(session: ChatSession): string | undefined {
    if (agentType === "DRIVE") {
      return projectsByFolderId.get(session.gdrive_folder_id ?? "")?.name;
    }
    return projectsById.get(session.project_id ?? "")?.name;
  }

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
            onClick={handleNewChat}
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
          {allSessions.length > 0 ? (
            <div className="space-y-0.5">
              {allSessions.map((session) => {
                const folderName = getFolderName(session);

                return (
                  <button
                    key={session.id}
                    onClick={() => handleSelectSession(session)}
                    className={`group w-full border-l-[3px] px-5 py-1.5 text-left text-[13px] transition-colors ${
                      sessionId === session.id
                        ? "border-l-brand-500 bg-brand-500/[0.06] text-fg-primary"
                        : "border-l-transparent text-cream hover:bg-[var(--hover-overlay)]"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <MessageSquare className="h-3 w-3 flex-shrink-0" />
                      <span className="flex-1 truncate">
                        {session.title ?? "Untitled"}
                      </span>
                      <Trash2
                        className="h-3 w-3 flex-shrink-0 text-surface-100 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100"
                        onClick={(e) => handleDeleteSession(e, session)}
                      />
                    </div>
                    <div className="ml-5 mt-px flex items-center gap-1.5 text-[10px] text-surface-100/60">
                      {folderName && (
                        <>
                          <FolderOpen className="h-2.5 w-2.5 flex-shrink-0" />
                          <span className="truncate">{folderName}</span>
                          <span className="text-surface-100/40">·</span>
                        </>
                      )}
                      <span className="whitespace-nowrap">{new Date(session.created_at).toLocaleDateString()}</span>
                    </div>
                  </button>
                );
              })}
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
        {!selectedProject ? (
          /* ── Welcome / Folder Picker ── */
          <div className="flex flex-1 flex-col items-center justify-center px-6">
            <FolderOpen className="h-10 w-10 text-surface-700" />
            <h3 className="mt-4 text-base font-medium text-fg-primary">
              What would you like to chat about?
            </h3>
            <p className="mt-1 text-sm text-surface-100/60">
              Pick a connected folder or add a new one.
            </p>

            <div className="mt-6 flex w-full max-w-md flex-col gap-2">
              {qualifiedProjects.length > 5 && (
                <div className="relative mb-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-surface-100/50" />
                  <input
                    type="text"
                    value={folderSearch}
                    onChange={(e) => setFolderSearch(e.target.value)}
                    placeholder="Search folders..."
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-surface-800 py-2 pl-9 pr-3 text-sm text-fg-primary placeholder-surface-100/40 focus:border-brand-500/40 focus:outline-none"
                  />
                </div>
              )}

              <div className="max-h-[280px] space-y-2 overflow-y-auto">
                {[...qualifiedProjects]
                  .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                  .filter((p) => !folderSearch || p.name.toLowerCase().includes(folderSearch.toLowerCase()))
                  .map((project) => (
                    <button
                      key={project.id}
                      onClick={() => { setSelectedProject(project); setFolderSearch(""); }}
                      className="flex w-full items-center gap-3 rounded-xl border border-[var(--border-subtle)] bg-surface-800 px-4 py-3 text-left transition-colors hover:border-brand-500/40 hover:bg-surface-800/80"
                    >
                      <FolderOpen className="h-5 w-5 flex-shrink-0 text-brand-500" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-fg-primary">
                          {project.name}
                        </p>
                        <p className="text-xs text-surface-100/50">
                          {project.files_total} files
                        </p>
                      </div>
                    </button>
                  ))}
              </div>

              <button
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-3 rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-3 text-left transition-colors hover:border-brand-500/40 hover:bg-surface-800/40"
              >
                <FolderPlus className="h-5 w-5 flex-shrink-0 text-surface-100" />
                <span className="text-sm text-surface-100">
                  Add new folder...
                </span>
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* Active folder indicator */}
            <div className="border-b border-[var(--border-subtle)] px-4 py-3">
              <ProjectSelector
                projects={qualifiedProjects}
                selected={selectedProject}
                onSelect={setSelectedProject}
                onAddFolder={() => setShowAddModal(true)}
                disabled={folderLocked}
              />
            </div>

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
