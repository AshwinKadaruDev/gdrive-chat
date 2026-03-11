import { create } from "zustand";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
  root.style.colorScheme = theme;
}

function getInitialTheme(): Theme {
  const stored = localStorage.getItem("tenex-theme");
  if (stored === "light" || stored === "dark") return stored;
  return "dark";
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: getInitialTheme(),

  toggleTheme: () => {
    const next = get().theme === "dark" ? "light" : "dark";
    localStorage.setItem("tenex-theme", next);
    applyTheme(next);
    set({ theme: next });
  },
}));
