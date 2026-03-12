import { describe, it, expect, vi, beforeEach } from "vitest";
import { act } from "@testing-library/react";

vi.mock("@/services/api", () => ({
  getCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
}));

beforeEach(() => {
  vi.resetModules();
});

async function getStore() {
  const mod = await import("../useAuth");
  return mod.useAuth;
}

describe("useAuth", () => {
  it("fetchUser sets user on success", async () => {
    const api = await import("@/services/api");
    const mockUser = { id: "1", email: "a@b.com", name: "A", picture_url: null };
    (api.getCurrentUser as ReturnType<typeof vi.fn>).mockResolvedValue(mockUser);

    const useAuth = await getStore();
    await act(async () => {
      await useAuth.getState().fetchUser();
    });

    expect(useAuth.getState().user).toEqual(mockUser);
    expect(useAuth.getState().isLoading).toBe(false);
    expect(useAuth.getState().hasChecked).toBe(true);
  });

  it("fetchUser clears user on error", async () => {
    const api = await import("@/services/api");
    (api.getCurrentUser as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error("401")
    );

    const useAuth = await getStore();
    await act(async () => {
      await useAuth.getState().fetchUser();
    });

    expect(useAuth.getState().user).toBeNull();
    expect(useAuth.getState().isLoading).toBe(false);
    expect(useAuth.getState().hasChecked).toBe(true);
  });

  it("login calls API login", async () => {
    const api = await import("@/services/api");
    const useAuth = await getStore();

    act(() => {
      useAuth.getState().login();
    });

    expect(api.login).toHaveBeenCalled();
  });

  it("logout clears state", async () => {
    const api = await import("@/services/api");
    (api.logout as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);

    const useAuth = await getStore();
    // Set user first
    useAuth.setState({ user: { id: "1", email: "a@b.com", name: "A", picture_url: null } });

    // Mock window.location.href setter (logout does a redirect)
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...originalLocation, href: "" },
    });

    await act(async () => {
      await useAuth.getState().logout();
    });

    expect(useAuth.getState().user).toBeNull();
    expect(useAuth.getState().hasChecked).toBe(true);

    // Restore
    Object.defineProperty(window, "location", {
      writable: true,
      value: originalLocation,
    });
  });
});
