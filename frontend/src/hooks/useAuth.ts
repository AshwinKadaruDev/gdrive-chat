import { create } from "zustand";
import {
  getCurrentUser,
  login as apiLogin,
  logout as apiLogout,
} from "@/services/api";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  hasChecked: boolean;
  fetchUser: () => Promise<void>;
  login: () => void;
  logout: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  isLoading: true,
  hasChecked: false,

  fetchUser: async () => {
    try {
      set({ isLoading: true });
      const user = await getCurrentUser();
      set({ user, isLoading: false, hasChecked: true });
    } catch {
      set({ user: null, isLoading: false, hasChecked: true });
    }
  },

  login: () => {
    apiLogin();
  },

  logout: async () => {
    try {
      await apiLogout();
    } finally {
      set({ user: null, hasChecked: true });
      window.location.href = "/";
    }
  },
}));
