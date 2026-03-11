import { describe, it, expect, beforeEach, vi } from "vitest";
import { act } from "@testing-library/react";

// Reset module between tests so Zustand store reinitializes
beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
  document.documentElement.classList.add("dark");
  document.documentElement.style.colorScheme = "";
});

async function getStore() {
  const mod = await import("../useTheme");
  return mod.useTheme;
}

describe("useTheme", () => {
  it("defaults to dark when no localStorage value", async () => {
    const useTheme = await getStore();
    expect(useTheme.getState().theme).toBe("dark");
  });

  it("reads theme from localStorage", async () => {
    localStorage.setItem("tenex-theme", "light");
    const useTheme = await getStore();
    expect(useTheme.getState().theme).toBe("light");
  });

  it("defaults to dark for invalid localStorage value", async () => {
    localStorage.setItem("tenex-theme", "banana");
    const useTheme = await getStore();
    expect(useTheme.getState().theme).toBe("dark");
  });

  it("toggleTheme flips from dark to light", async () => {
    const useTheme = await getStore();
    act(() => useTheme.getState().toggleTheme());

    expect(useTheme.getState().theme).toBe("light");
    expect(localStorage.getItem("tenex-theme")).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("toggleTheme flips from light to dark", async () => {
    localStorage.setItem("tenex-theme", "light");
    const useTheme = await getStore();
    act(() => useTheme.getState().toggleTheme());

    expect(useTheme.getState().theme).toBe("dark");
    expect(localStorage.getItem("tenex-theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });
});
