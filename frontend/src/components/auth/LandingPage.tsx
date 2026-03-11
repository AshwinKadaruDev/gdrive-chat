import GoogleLoginButton from "./GoogleLoginButton";
import TenexLogo from "@/components/TenexLogo";

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-surface-950 px-4">
      {/* Login card */}
      <div className="w-full max-w-md border border-[var(--border-subtle)] bg-surface-800 px-10 pb-10 pt-12 shadow-[0_0_80px_rgba(255,229,1,0.03)]">
        {/* Brand */}
        <div className="flex justify-center">
          <TenexLogo iconSize={36} />
        </div>

        {/* Divider */}
        <div className="mx-auto my-8 h-px w-12 bg-brand-500" />

        {/* Description */}
        <p className="text-center text-[15px] leading-relaxed text-cream">
          Connect your Google Drive folders and chat with your documents
          using AI-powered search.
        </p>

        {/* Action */}
        <div className="mt-10">
          <GoogleLoginButton />
        </div>

        {/* Hint */}
        <p className="mt-4 text-center text-xs text-surface-100/60">
          Sign in with your Google account to get started
        </p>
      </div>

      {/* Footer */}
      <p className="mt-8 text-xs tracking-wide text-surface-100/40">
        Powered by Tenex
      </p>
    </div>
  );
}
