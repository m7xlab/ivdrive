"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Mail, Lock, User, Eye, EyeOff, Sparkles, CheckCircle } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";

export default function RegisterPage() {
  return (
    <Suspense
      fallback={
        <div className="glass glow-green rounded-2xl p-8 w-full flex items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-iv-border border-t-iv-green" />
        </div>
      }
    >
      <RegisterForm />
    </Suspense>
  );
}

function RegisterForm() {
  const { register } = useAuth();
  const searchParams = useSearchParams();
  const tokenFromUrl = searchParams.get("token");

  const [mode, setMode] = useState<"open" | "invite_only" | null>(null);
  const [view, setView] = useState<"register" | "request">(
    tokenFromUrl ? "register" : "register"
  );

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Invite request state
  const [requestEmail, setRequestEmail] = useState("");
  const [requestSent, setRequestSent] = useState(false);
  const [requestMessage, setRequestMessage] = useState("");

  useEffect(() => {
    api.getRegistrationMode().then((res) => {
      const m = res.mode === "invite_only" ? "invite_only" : "open";
      setMode(m);
      // If invite_only and no token, show request form
      if (m === "invite_only" && !tokenFromUrl) {
        setView("request");
      }
    });
  }, [tokenFromUrl]);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);
    try {
      await register(
        email,
        password,
        displayName || undefined,
        tokenFromUrl || undefined
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRequestInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.requestInvite(requestEmail);
      setRequestSent(true);
      setRequestMessage(res.message || "Request submitted!");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  // Loading registration mode
  if (mode === null) {
    return (
      <div className="glass glow-green rounded-2xl p-8 w-full flex items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-iv-border border-t-iv-green" />
      </div>
    );
  }

  // ── Invite Request Form (invite_only mode, no token) ──
  if (view === "request" && !tokenFromUrl) {
    if (requestSent) {
      return (
        <div className="glass glow-green rounded-2xl p-8 w-full">
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="w-14 h-14 rounded-full bg-iv-green/15 flex items-center justify-center">
              <CheckCircle className="w-7 h-7 text-iv-green" />
            </div>
            <h1 className="text-2xl font-bold text-iv-text">You&apos;re on the list!</h1>
            <p className="text-iv-muted text-sm max-w-xs">
              {requestMessage}
            </p>
            <p className="text-iv-muted/60 text-xs mt-2">
              We&apos;ll send you an invitation link once approved.
            </p>
          </div>
          <p className="text-center text-sm text-iv-muted mt-8">
            Already have an invite?{" "}
            <button
              onClick={() => { setView("register"); setRequestSent(false); }}
              className="text-iv-cyan hover:text-iv-glow transition-colors font-medium"
            >
              Register here
            </button>
          </p>
        </div>
      );
    }

    return (
      <div className="glass glow-green rounded-2xl p-8 w-full">
        <div className="mb-6 text-center">
          <div className="w-12 h-12 rounded-full bg-iv-cyan/10 flex items-center justify-center mx-auto mb-4">
            <Sparkles className="w-6 h-6 text-iv-cyan" />
          </div>
          <h1 className="text-2xl font-bold text-iv-text">Request an Invite</h1>
          <p className="text-iv-muted text-sm mt-1">
            iVDrive is currently invite-only. Join the waitlist!
          </p>
        </div>

        <form onSubmit={handleRequestInvite} className="flex flex-col gap-4">
          {error && (
            <div className="bg-iv-danger/10 border border-iv-danger/30 text-iv-danger text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="requestEmail" className="text-sm font-medium text-iv-muted">
              Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
              <input
                id="requestEmail"
                type="email"
                value={requestEmail}
                onChange={(e) => setRequestEmail(e.target.value)}
                placeholder="you@example.com"
                required
                autoComplete="email"
                className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-4 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-cyan transition-colors"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 w-full bg-gradient-to-r from-iv-cyan to-iv-green text-white font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Submitting…
              </span>
            ) : (
              "Join Waitlist"
            )}
          </button>
        </form>

        <div className="mt-6 space-y-2 text-center">
          <p className="text-sm text-iv-muted">
            Already have an invite token?{" "}
            <button
              onClick={() => setView("register")}
              className="text-iv-cyan hover:text-iv-glow transition-colors font-medium"
            >
              Register here
            </button>
          </p>
          <p className="text-sm text-iv-muted">
            Already have an account?{" "}
            <Link href="/login" className="text-iv-cyan hover:text-iv-glow transition-colors font-medium">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    );
  }

  // ── Registration Form (open mode or has token) ──
  return (
    <div className="glass glow-green rounded-2xl p-8 w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-iv-text">Create account</h1>
        <p className="text-iv-muted text-sm mt-1">
          {tokenFromUrl
            ? "You've been invited — complete your registration"
            : "Get started with iVDrive"}
        </p>
      </div>

      <form onSubmit={handleRegister} className="flex flex-col gap-4">
        {error && (
          <div className="bg-iv-danger/10 border border-iv-danger/30 text-iv-danger text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="displayName" className="text-sm font-medium text-iv-muted">
            Display name <span className="text-iv-muted/50 font-normal">(optional)</span>
          </label>
          <div className="relative">
            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="displayName"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="How should we call you?"
              autoComplete="name"
              className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-4 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-sm font-medium text-iv-muted">Email</label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoComplete="email"
              className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-4 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="password" className="text-sm font-medium text-iv-muted flex justify-between">
            <span>Password</span>
            <span className="text-xs text-iv-muted/60 font-normal">Min 8 chars</span>
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 6 characters"
              required
              autoComplete="new-password"
              className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-10 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors"
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="confirmPassword" className="text-sm font-medium text-iv-muted flex justify-between">
            <span>Confirm password</span>
            {confirmPassword.length > 0 && password !== confirmPassword && (
              <span className="text-xs text-iv-danger">Passwords do not match</span>
            )}
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="confirmPassword"
              type={showConfirm ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Repeat your password"
              required
              autoComplete="new-password"
              className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-10 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors"
            />
            <button
              type="button"
              onClick={() => setShowConfirm(!showConfirm)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors"
              tabIndex={-1}
            >
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading || password.length < 8 || password !== confirmPassword}
          className="mt-2 w-full bg-gradient-to-r from-iv-green to-iv-cyan text-white font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Creating account…
            </span>
          ) : (
            "Create account"
          )}
        </button>
      </form>

      <div className="mt-6 space-y-2 text-center">
        {mode === "invite_only" && !tokenFromUrl && (
          <p className="text-sm text-iv-muted">
            Need an invite?{" "}
            <button
              onClick={() => setView("request")}
              className="text-iv-cyan hover:text-iv-glow transition-colors font-medium"
            >
              Request one here
            </button>
          </p>
        )}
        <p className="text-sm text-iv-muted">
          Already have an account?{" "}
          <Link href="/login" className="text-iv-cyan hover:text-iv-glow transition-colors font-medium">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
