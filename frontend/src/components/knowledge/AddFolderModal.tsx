import { useState, useEffect, useRef, useCallback } from "react";
import { useCreateProject, useValidateFolder } from "@/hooks/useProjects";
import { X, FolderPlus, Loader2, Check } from "lucide-react";
import type { Project } from "@/types";

interface AddFolderModalProps {
  onClose: () => void;
  onCreated?: (project: Project) => void;
  triggerRef?: React.RefObject<HTMLButtonElement | null>;
}

const GDRIVE_URL_PATTERN =
  /^https:\/\/drive\.google\.com\/(drive\/)?(u\/\d+\/)?folders\/[a-zA-Z0-9_-]+/;

type ModalState = "idle" | "validating" | "validated" | "error" | "creating";

const ERROR_MESSAGES: Record<string, string> = {
  not_found:
    "We couldn't find that folder. Double-check the URL and make sure the folder hasn't been deleted.",
  no_access:
    "You don't have access to this folder. Ask the owner to share it with your Google account.",
  not_a_folder:
    "That URL points to a file, not a folder. Please paste a link to a Google Drive folder.",
  drive_error:
    "Something went wrong connecting to Google Drive. Please try again.",
  duplicate: "This folder has already been added.",
};

function getErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "response" in error) {
    const resp = (error as { response?: { data?: { detail?: string }; status?: number; headers?: Headers } }).response;
    // Check for duplicate (409)
    if (resp?.status === 409) {
      return ERROR_MESSAGES.duplicate;
    }
    // Try to match known error codes from response detail text
    const detail = resp?.data?.detail;
    if (typeof detail === "string") {
      for (const [code, msg] of Object.entries(ERROR_MESSAGES)) {
        if (detail === msg || detail.toLowerCase().includes(code.replace("_", " "))) {
          return msg;
        }
      }
      return detail;
    }
  }
  return "Please enter a valid Google Drive folder URL.";
}

export default function AddFolderModal({ onClose, onCreated, triggerRef }: AddFolderModalProps) {
  const [url, setUrl] = useState("");
  const [state, setState] = useState<ModalState>("idle");
  const [folderName, setFolderName] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const urlRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const validateFolder = useValidateFolder();
  const createProject = useCreateProject();

  const handleClose = useCallback(() => {
    onClose();
    triggerRef?.current?.focus();
  }, [onClose, triggerRef]);

  useEffect(() => {
    urlRef.current?.focus();
  }, []);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleClose();
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [handleClose]);

  const doValidate = useCallback(
    (value: string) => {
      if (!value || !GDRIVE_URL_PATTERN.test(value)) {
        if (value) {
          setState("error");
          setErrorMessage("Please enter a valid Google Drive folder URL.");
        } else {
          setState("idle");
          setErrorMessage("");
        }
        return;
      }

      setState("validating");
      setErrorMessage("");
      setFolderName("");

      validateFolder.mutate(value, {
        onSuccess: (data) => {
          setFolderName(data.folder_name);
          setState("validated");
        },
        onError: (err) => {
          setState("error");
          setErrorMessage(getErrorMessage(err));
        },
      });
    },
    [validateFolder]
  );

  const handleUrlChange = (value: string) => {
    setUrl(value);

    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!value) {
      setState("idle");
      setErrorMessage("");
      setFolderName("");
      return;
    }

    if (!GDRIVE_URL_PATTERN.test(value)) {
      // Don't show error while typing, wait for blur
      setState("idle");
      return;
    }

    debounceRef.current = setTimeout(() => doValidate(value), 600);
  };

  const handleBlur = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    // Only validate on blur if we haven't validated yet (avoid double-fire)
    if (url && state !== "validated" && state !== "validating") doValidate(url);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (state !== "validated") return;

    setState("creating");
    try {
      const newProject = await createProject.mutateAsync({
        gdrive_folder_url: url.trim(),
        name: folderName,
      });
      onCreated?.(newProject);
      handleClose();
    } catch (err) {
      setState("error");
      setErrorMessage(getErrorMessage(err));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative mx-4 w-full max-w-md border border-[var(--border-subtle)] bg-surface-850 p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <FolderPlus className="h-5 w-5 text-brand-500" />
            <h2 className="text-lg font-semibold text-fg-primary">
              Add Google Drive Folder
            </h2>
          </div>
          <button
            onClick={handleClose}
            className="p-1 text-surface-100 transition-colors hover:text-fg-primary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="folder-url"
              className="mb-1.5 block text-sm font-medium text-cream"
            >
              Paste a Google Drive folder URL
            </label>
            <input
              ref={urlRef}
              id="folder-url"
              type="url"
              value={url}
              onChange={(e) => handleUrlChange(e.target.value)}
              onBlur={handleBlur}
              placeholder="https://drive.google.com/drive/folders/..."
              className={`input-field ${
                state === "error"
                  ? "border-red-500 focus:border-red-500"
                  : state === "validated"
                    ? "border-green-500/50 focus:border-green-500/50"
                    : ""
              }`}
              disabled={state === "creating" || state === "validating"}
              required
            />
          </div>

          {/* Validation status */}
          {state === "validating" && (
            <div className="flex items-center gap-2 px-3 py-2 text-sm text-surface-100">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking folder...
            </div>
          )}

          {state === "validated" && folderName && (
            <div className="flex items-center justify-between rounded border border-green-500/20 bg-green-950/20 px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-fg-primary">
                <span>📁</span>
                <span className="font-medium">{folderName}</span>
              </div>
              <Check className="h-4 w-4 text-green-400" />
            </div>
          )}

          {state === "error" && errorMessage && (
            <div className="bg-red-950/30 px-3 py-2 text-sm text-red-400">
              {errorMessage}
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="btn-secondary flex-1"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={state !== "validated"}
              className="btn-primary flex-1"
            >
              {state === "creating" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Adding...
                </>
              ) : "Add Folder"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
