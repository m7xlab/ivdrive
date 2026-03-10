"use client";

import { useState } from "react";
import Link from "next/link";
import { Mail, ArrowLeft, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await api.forgotPassword(email);
      setSubmitted(true);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Something went wrong. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="glass glow-green rounded-2xl p-8 w-full">
        <div className="flex flex-col items-center text-center gap-4 py-4">
          <div className="w-14 h-14 rounded-full bg-iv-green/10 border border-iv-green/30 flex items-center justify-center">
            <CheckCircle className="w-7 h-7 text-iv-green" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-iv-text">Check your email</h1>
            <p className="text-iv-muted text-sm mt-2 leading-relaxed">
              If an account exists for{" "}
              <strong className="text-iv-text">{email}</strong>, you&apos;ll
              receive a password reset link within a few minutes.
            </p>
          </div>
          <p className="text-xs text-iv-muted leading-relaxed">
            Didn&apos;t receive an email? Check your spam folder or{" "}
            <button
              type="button"
              onClick={() => {
                setSubmitted(false);
                setEmail("");
              }}
              className="text-iv-cyan hover:text-iv-glow transition-colors font-medium"
            >
              try again
            </button>
            .
          </p>
          <Link
            href="/login"
            className="mt-2 flex items-center gap-1.5 text-sm text-iv-muted hover:text-iv-text transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="glass glow-green rounded-2xl p-8 w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-iv-text">Forgot password?</h1>
        <p className="text-iv-muted text-sm mt-1">
          Enter your email address and we&apos;ll send you a link to reset your
          password.
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

        <button
          type="submit"
          disabled={loading || !email}
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
              Sending…
            </span>
          ) : (
            "Send reset link"
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
    </div>
  );
}
