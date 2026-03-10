"use client";

import { useState } from "react";
import Link from "next/link";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { login, verify2FA, verifyRecoveryCode } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [requires2FA, setRequires2FA] = useState(false);
  const [token2FA, setToken2FA] = useState("");
  const [code2FA, setCode2FA] = useState("");
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await login(email, password);
      if (res && res.requires_2fa) {
        setRequires2FA(true);
        // Note: Pydantic alias '2fa_token' maps to 'res["2fa_token"]' or 'res.tfa_token'
        setToken2FA(res["2fa_token"] || res.tfa_token);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Invalid email or password";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify2FA = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (useRecoveryCode) {
        await verifyRecoveryCode(token2FA, recoveryCode);
      } else {
        await verify2FA(token2FA, code2FA);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Invalid verification code";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (requires2FA) {
    return (
      <div className="glass glow-green rounded-2xl p-8 w-full">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-iv-text">
            {useRecoveryCode ? "Recovery Code" : "Two-Factor Authentication"}
          </h1>
          <p className="text-iv-muted text-sm mt-1">
            {useRecoveryCode
              ? "Enter one of your 8-character recovery codes."
              : "Enter the 6-digit code from your authenticator app."}
          </p>
        </div>

        <form onSubmit={handleVerify2FA} className="flex flex-col gap-4">
          {error && (
            <div className="bg-iv-danger/10 border border-iv-danger/30 text-iv-danger text-sm rounded-lg px-4 py-3">
              {error}
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="code" className="text-sm font-medium text-iv-muted">
              {useRecoveryCode ? "Recovery Code" : "Verification Code"}
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
              {useRecoveryCode ? (
                <input
                  id="recovery_code"
                  type="text"
                  maxLength={8}
                  value={recoveryCode}
                  onChange={(e) => setRecoveryCode(e.target.value.toUpperCase())}
                  placeholder="ABC123XY"
                  required
                  className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-4 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors text-center text-xl tracking-widest font-mono"
                />
              ) : (
                <input
                  id="code"
                  type="text"
                  maxLength={6}
                  value={code2FA}
                  onChange={(e) => setCode2FA(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  required
                  className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-4 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors text-center text-xl tracking-widest font-mono"
                />
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={
              loading ||
              (useRecoveryCode ? recoveryCode.length !== 8 : code2FA.length !== 6)
            }
            className="mt-2 w-full bg-gradient-to-r from-iv-green to-iv-cyan text-white font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Verifying..." : "Verify Code"}
          </button>

          <div className="flex flex-col gap-2 mt-2">
            <button
              type="button"
              onClick={() => {
                setUseRecoveryCode(!useRecoveryCode);
                setError("");
                setRecoveryCode("");
                setCode2FA("");
              }}
              className="text-xs text-iv-cyan hover:text-iv-glow transition-colors text-center font-medium"
            >
              {useRecoveryCode
                ? "Use authenticator app instead"
                : "Lost your phone? Use a recovery code"}
            </button>

            <button
              type="button"
              onClick={() => {
                setRequires2FA(false);
                setToken2FA("");
                setCode2FA("");
                setRecoveryCode("");
                setUseRecoveryCode(false);
                setError("");
              }}
              className="text-xs text-iv-muted hover:text-iv-text transition-colors text-center"
            >
              Back to login
            </button>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="glass glow-green rounded-2xl p-8 w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-iv-text">Welcome back</h1>
        <p className="text-iv-muted text-sm mt-1">
          Sign in to your iVDrive account
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && (
          <div className="bg-iv-danger/10 border border-iv-danger/30 text-iv-danger text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-sm font-medium text-iv-muted">
            Email
          </label>
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
          <div className="flex items-center justify-between">
            <label
              htmlFor="password"
              className="text-sm font-medium text-iv-muted"
            >
              Password
            </label>
            <Link
              href="/forgot-password"
              className="text-xs text-iv-cyan hover:text-iv-glow transition-colors font-medium"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-iv-muted" />
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              autoComplete="current-password"
              className="w-full bg-iv-surface border border-iv-border rounded-lg py-2.5 pl-10 pr-10 text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green transition-colors"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-iv-muted hover:text-iv-text transition-colors"
              tabIndex={-1}
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4" />
              ) : (
                <Eye className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="mt-2 w-full bg-gradient-to-r from-iv-green to-iv-cyan text-white font-semibold py-2.5 rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg
                className="animate-spin h-4 w-4"
                viewBox="0 0 24 24"
                fill="none"
              >
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
              Signing in…
            </span>
          ) : (
            "Sign in"
          )}
        </button>
      </form>

      <p className="text-center text-sm text-iv-muted mt-6">
        Don&apos;t have an account?{" "}
        <Link
          href="/register"
          className="text-iv-cyan hover:text-iv-glow transition-colors font-medium"
        >
          Register
        </Link>
      </p>
    </div>
  );
}
