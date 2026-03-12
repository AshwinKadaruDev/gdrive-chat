export interface User {
  id: string;
  email: string;
  name: string;
  picture_url: string | null;
}

export interface Project {
  id: string;
  name: string;
  gdrive_folder_id: string | null;
  gdrive_folder_url: string | null;
  sync_status: SyncStatus;
  files_total: number;
  files_processed: number;
  last_synced_at: string | null;
  sync_error: string | null;
  created_at: string;
}

export type SyncStatus =
  | "PENDING"
  | "SYNCING"
  | "COMPLETED"
  | "FAILED";

export interface ChatSession {
  id: string;
  project_id?: string | null;
  gdrive_folder_id?: string | null;
  title: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface Citation {
  chunk_id: string;
  file_id: string;
  file_name: string;
  source_url: string | null;
  location: string | null;
  snippet: string;
}

