import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import TopBar from "@/components/layout/TopBar";
import LandingPage from "@/components/auth/LandingPage";
import ProjectList from "@/components/knowledge/ProjectList";
import UnifiedChatContainer from "@/components/chat/UnifiedChatContainer";

function AuthenticatedLayout() {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-surface-950">
      <TopBar />
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/knowledge" element={<ProjectList />} />
          <Route
            path="/deep-search"
            element={<UnifiedChatContainer agentType="RAG" />}
          />
          <Route
            path="/quick-search"
            element={<UnifiedChatContainer agentType="DRIVE" />}
          />
          <Route path="/chat" element={<Navigate to="/deep-search" replace />} />
          <Route
            path="/drive-chat"
            element={<Navigate to="/quick-search" replace />}
          />
          <Route path="*" element={<Navigate to="/knowledge" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  const { user, isLoading, hasChecked, fetchUser } = useAuth();

  useEffect(() => {
    if (!hasChecked) {
      fetchUser();
    }
  }, [hasChecked, fetchUser]);

  if (isLoading && !hasChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-surface-950">
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

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<LandingPage />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/*" element={<AuthenticatedLayout />} />
    </Routes>
  );
}
