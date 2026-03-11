import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AddFolderModal from "../AddFolderModal";

const VALID_URL = "https://drive.google.com/drive/folders/1aBcD_eFgHiJk";

const mockValidateMutate = vi.fn();
const mockCreateMutateAsync = vi.fn();

vi.mock("@/hooks/useProjects", () => ({
  useValidateFolder: () => ({
    mutate: mockValidateMutate,
    isPending: false,
  }),
  useCreateProject: () => ({
    mutateAsync: mockCreateMutateAsync,
    isPending: false,
    isError: false,
  }),
}));

function renderModal(onClose = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AddFolderModal onClose={onClose} />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

describe("AddFolderModal", () => {
  it("renders a single URL input without a name field", () => {
    renderModal();
    expect(screen.getByLabelText(/paste a google drive folder url/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/folder name/i)).not.toBeInTheDocument();
  });

  it("has the Add Folder button disabled initially", () => {
    renderModal();
    const btn = screen.getByRole("button", { name: /add folder/i });
    expect(btn).toBeDisabled();
  });

  it("shows 'Checking folder...' during validation", async () => {
    // Make validate hang (don't call onSuccess)
    mockValidateMutate.mockImplementation(() => {});

    renderModal();
    const input = screen.getByLabelText(/paste a google drive folder url/i);
    fireEvent.change(input, { target: { value: VALID_URL } });

    // Advance past debounce
    vi.advanceTimersByTime(700);

    await waitFor(() => {
      expect(screen.getByText(/checking folder/i)).toBeInTheDocument();
    });
  });

  it("shows folder name preview on successful validation", async () => {
    mockValidateMutate.mockImplementation((_url: string, opts: Record<string, Function>) => {
      opts.onSuccess({ folder_name: "Product Docs", folder_id: "abc", gdrive_folder_url: VALID_URL });
    });

    renderModal();
    const input = screen.getByLabelText(/paste a google drive folder url/i);
    fireEvent.change(input, { target: { value: VALID_URL } });
    vi.advanceTimersByTime(700);

    await waitFor(() => {
      expect(screen.getByText("Product Docs")).toBeInTheDocument();
    });

    // Button should now be enabled
    const btn = screen.getByRole("button", { name: /add folder/i });
    expect(btn).not.toBeDisabled();
  });

  it("shows error message on validation failure", async () => {
    mockValidateMutate.mockImplementation((_url: string, opts: Record<string, Function>) => {
      opts.onError({
        response: { status: 422, data: { detail: "You don't have access to this folder." } },
      });
    });

    renderModal();
    const input = screen.getByLabelText(/paste a google drive folder url/i);
    fireEvent.change(input, { target: { value: VALID_URL } });
    vi.advanceTimersByTime(700);

    await waitFor(() => {
      expect(screen.getByText(/don't have access/i)).toBeInTheDocument();
    });

    // Button stays disabled
    const btn = screen.getByRole("button", { name: /add folder/i });
    expect(btn).toBeDisabled();
  });

  it("calls createProject with correct args on submit", async () => {
    mockValidateMutate.mockImplementation((_url: string, opts: Record<string, Function>) => {
      opts.onSuccess({ folder_name: "My Folder", folder_id: "abc", gdrive_folder_url: VALID_URL });
    });
    mockCreateMutateAsync.mockResolvedValue({ id: "proj-1" });

    const onClose = vi.fn();
    renderModal(onClose);

    const input = screen.getByLabelText(/paste a google drive folder url/i);
    fireEvent.change(input, { target: { value: VALID_URL } });
    vi.advanceTimersByTime(700);

    await waitFor(() => {
      expect(screen.getByText("My Folder")).toBeInTheDocument();
    });

    vi.useRealTimers();

    const btn = screen.getByRole("button", { name: /add folder/i });
    fireEvent.click(btn);

    await waitFor(() => {
      expect(mockCreateMutateAsync).toHaveBeenCalledWith({
        gdrive_folder_url: VALID_URL,
        name: "My Folder",
      });
    });
  });

  it("closes on Escape key", () => {
    const onClose = vi.fn();
    renderModal(onClose);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
