import { useState } from "react";
import { NavLink } from "react-router-dom";
import { BookOpen, Search, Zap, LogOut, Sun, Moon } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useTheme } from "@/hooks/useTheme";
import TenexLogo from "@/components/TenexLogo";

const tabs = [
  { to: "/knowledge", label: "Knowledge", icon: BookOpen },
  { to: "/deep-search", label: "Deep Search", icon: Search },
  { to: "/quick-search", label: "Quick Search", icon: Zap },
];

function UserAvatar({ name, pictureUrl }: { name: string; pictureUrl: string | null }) {
  const [imgFailed, setImgFailed] = useState(false);

  if (pictureUrl && !imgFailed) {
    return (
      <img
        src={pictureUrl}
        alt={name}
        className="h-7 w-7 rounded-full object-cover"
        referrerPolicy="no-referrer"
        onError={() => setImgFailed(true)}
      />
    );
  }

  return (
    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

export default function TopBar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="flex items-center border-b border-[var(--border-subtle)] bg-surface-900 px-6">
      <TenexLogo iconSize={24} className="mr-8" />

      <nav className="flex gap-1">
        {tabs.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2 border-b-2 px-4 py-3.5 text-sm font-medium transition-colors ${
                isActive
                  ? "border-brand-500 text-brand-500"
                  : "border-transparent text-surface-100 hover:text-fg-primary"
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="ml-auto flex items-center gap-4">
          <div className="flex items-center gap-3">
            <UserAvatar name={user.name} pictureUrl={user.picture_url} />
            <span className="text-sm text-surface-100">{user.name}</span>
          </div>
          <button
            onClick={toggleTheme}
            className="btn-ghost px-2 py-1.5 text-surface-100 hover:text-fg-primary"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <button
            onClick={logout}
            className="btn-ghost px-2 py-1.5 text-surface-100 hover:text-red-400"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      )}
    </header>
  );
}
