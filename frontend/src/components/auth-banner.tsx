"use client";

import { useState } from "react";
import { AlertTriangle, KeyRound, Loader2, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import type { Vehicle } from "@/lib/hooks/use-vehicles";
import { PasswordInput } from "@/components/password-input";

/**
 * Shown at the top of a vehicle card (or above the dashboard) when the
 * connector has flagged the user-driven reauth. The reason comes from the
 * backend's `needs_user_reauth_reason` field. Examples:
 *
 *   - "Škoda rejected the saved login (authentication failed) — please reconnect."
 *   - "Consistent 403s across multiple endpoints"
 *   - "Password rejected or account locked by Škoda."
 *
 * The card displays the reason, lets the user trigger a forced reauth by
 * submitting their password again, and dismisses itself once successful.
 */
export function AuthReauthBanner({ vehicle }: { vehicle: Vehicle }) {
  const reason = vehicle.needs_user_reauth_reason;

  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  
  const queryClient = useQueryClient();

  if (!reason) return null;

  async function handleReauth(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      // We POST credentials back so the user can re-attempt silent login manually.
      const res = await fetch(`/api/v1/vehicles/${vehicle.id}/reauthenticate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skoda_username: username, skoda_password: password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      setOpen(false);
      setPassword("");
      queryClient.invalidateQueries({ queryKey: ["vehicles"] });
    } catch (e: any) {
      setErr(e?.message || "Failed to reauthenticate");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="alert"
      className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 flex items-start gap-3"
    >
      <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-amber-100">Reconnection required</p>
        <p className="text-xs text-amber-200/80 mt-0.5">{reason}</p>

        {open ? (
          <form onSubmit={handleReauth} className="mt-3 space-y-2">
            <input
              type="email"
              placeholder="Škoda email"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              className="w-full bg-iv-surface border border-iv-border rounded-lg px-3 py-2 text-sm"
            />
            <PasswordInput
              placeholder="Škoda password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              wrapperClassName="w-full"
              className="w-full bg-iv-surface border border-iv-border rounded-lg px-3 py-2 text-sm"
            />
            {err && <p className="text-xs text-red-300">{err}</p>}
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={submitting}
                className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-iv-black text-sm font-medium disabled:opacity-50 flex items-center gap-1.5"
              >
                {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Reconnect
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                disabled={submitting}
                className="px-3 py-1.5 rounded-lg bg-iv-surface border border-iv-border text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-iv-black text-sm font-medium"
          >
            <KeyRound className="w-3.5 h-3.5" />
            Reconnect Škoda
          </button>
        )}
      </div>
    </div>
  );
}

/** Inline pill that shows the last successful auth method (silent_login vs refresh). */
export function AuthMethodPill({ vehicle }: { vehicle: Vehicle }) {
  const method = vehicle.last_auth_method;
  if (!method) return null;

  const isSilent = method === "silent_login";
  return (
    <span
      title={
        isSilent
          ? "Re-authenticated silently using stored credentials (no user prompt)."
          : "Token refreshed using the long-lived refresh token."
      }
      className={
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium " +
        (isSilent
          ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
          : "bg-iv-surface text-iv-muted border border-iv-border")
      }
    >
      <span
        className={
          "w-1.5 h-1.5 rounded-full " + (isSilent ? "bg-emerald-400" : "bg-iv-muted")
        }
      />
      {isSilent ? "silent login" : "refresh"}
      {vehicle.last_auth_at && (
        <span className="text-iv-muted/70 ml-1">
          · {new Date(vehicle.last_auth_at).toLocaleTimeString()}
        </span>
      )}
    </span>
  );
}

/** Compact error pill for non-auth errors (e.g. transient Skoda 500s). */
export function ConnectorErrorPill({ vehicle }: { vehicle: Vehicle }) {
  const text = vehicle.last_error_text;
  if (!text) return null;
  // Auth errors are surfaced by AuthReauthBanner — only show non-auth ones here.
  if (
    text.toLowerCase().includes("auth") ||
    text.toLowerCase().includes("rejected") ||
    text.toLowerCase().includes("password") ||
    text.toLowerCase().includes("reconnect")
  ) {
    return null;
  }
  return (
    <p
      title={text}
      className="text-[11px] text-amber-300/80 mt-1 truncate max-w-full"
    >
      {text}
    </p>
  );
}