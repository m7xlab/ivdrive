"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Lock, Eye, EyeOff, CheckCircle, AlertCircle, ArrowLeft } from "lucide-react";
import { api } from "@/lib/api";

// Inner component uses useSearchParams — must be wrapped in Suspense per Next.js rules.
function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (success) {
      timer = setTimeout(() => router.push("/login"), 3000);
    }
    return () => clearTimeout(timer);
  }, [success, router]);

  const passwordsMatch = password === confirmPassword;
  const isValid = password.length >= 8 && confirmPassword.length > 0 && passwordsMatch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    setError("");
    setLoading(true);

    try {
      await api.resetPassword(token, password);
      setSuccess(true);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to reset password. The link may have expired.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  // No token in URL
  if (!token) {
    return (
      <div className="flex flex-col items-center text-center gap-4 py-4">
        <div className="w-14 h-14 rounded-full bg-iv-danger/10 border border-iv-danger/30 flex items-center justify-center">
          <AlertCircle className="w-7 h-7 text-iv-danger" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-iv-text">Invalid link</h1>
          <p className="text-iv-muted text-sm mt-2 leading-relaxed">
            This password reset link is invalid or has expired.
          </p>
        </div>
        <Link
          href="/forgot-password"
          className="mt-2 inline-flex items-center gap-1.5 text-sm text-iv-cyan hover:text-iv-glow transition-colors font-medium"
        >
          Request a new link
        </Link>
      </div>
    );
  }

  if (success) {
    return (
      <div className="flex flex-col items-center text-center gap-4 py-4">
        <div className="w-14 h-14 rounded-full bg-iv-green/10 border border-iv-green/30 flex items-center justify-center">
          <CheckCircle className="w-7 h-7 text-iv-green" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-iv-text">Password reset!</h1>
          <p className="text-iv-muted text-sm mt-2 leading-relaxed">
            Your password has been updated successfully. Redirecting you to
            login…
          </p>
        </div>
        <Link
          href="/login"
          className="mt-2 flex items-center gap-1.5 text-sm text-iv-muted hover:text-iv-text transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Go to login
        </Link>
      </div>
    );
  }

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-iv-text">Reset your password</h1>
        <p className="text-iv-muted text-sm mt-1">
          Enter a new password for your iVDrive account.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && (
          <div className="bg-iv-danger/10 border border-iv-danger/30 text-iv-danger text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        {/* New password */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="password" className="text-sm font-medium text-iv-muted">
            New password
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min. 8 characters"
              required
              minLength={8}
              autoComplete="new-password"
              className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-10 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors"
              tabIndex={-1}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {password.length > 0 && password.length < 8 && (
            <p className="text-xs text-iv-danger">Password must be at least 8 characters.</p>
          )}
        </div>

        {/* Confirm password */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="confirmPassword" className="text-sm font-medium text-iv-muted">
            Confirm new password
          </label>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="confirmPassword"
              type={showConfirm ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Repeat your new password"
              required
              autoComplete="new-password"
              className={`w-full bg-iv-surface border rounded-lg py-2.5 pl-10 pr-10 text-iv-text placeholder:text-iv-muted/50 focus:outline-none transition-colors ${
                confirmPassword.length > 0 && !passwordsMatch
                  ? "border-iv-danger focus:border-iv-danger"
                  : "border-iv-border focus:border-iv-green"
              }`}
            />
            <button
              type="button"
              onClick={() => setShowConfirm(!showConfirm)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors"
              tabIndex={-1}
              aria-label={showConfirm ? "Hide password" : "Show password"}
            >
              {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {confirmPassword.length > 0 && !passwordsMatch && (
            <p className="text-xs text-iv-danger">Passwords do not match.</p>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !isValid}
          className="mt-2 w-full bg-gradient-to-r from-iv-green to-iv-cyan text-white font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Resetting…
            </span>
          ) : (
            "Set new password"
          )}
        </button>
      </form>

      <div className="mt-6 text-center">
        <Link
          href="/login"
          className="flex items-center justify-center gap-1.5 text-sm text-iv-muted hover:text-iv-text transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to login
        </Link>
      </div>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="glass glow-green rounded-2xl p-8 w-full">
      <Suspense
        fallback={
          <div className="flex items-center justify-center py-8">
            <svg className="animate-spin h-6 w-6 text-iv-green" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        }
      >
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
