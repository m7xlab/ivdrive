"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";
import {
  Shield,
  Users,
  Mail,
  Clock,
  CheckCircle,
  XCircle,
  ChevronUp,
  ChevronDown,
  AlertTriangle,
  Crown,
  UserMinus,
  Loader2,
  Inbox,
  Copy,
  Check,
  Trash2,
  Send,
  Bell,
  PlusCircle,
  Info,
} from "lucide-react";

// ── Types ──

interface InviteRequest {
  id: string;
  email: string;
  status: string;
  created_at: string;
  approved_at: string | null;
}

interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string | null;
}

interface Announcement {
  id: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "critical";
  created_at: string;
  expires_at: string | null;
  is_active: boolean;
}

type Tab = "invites" | "users" | "announcements";

// ── Helpers ──

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
    pending: {
      bg: "bg-amber-500/10 border-amber-500/20",
      text: "text-amber-400",
      icon: <Clock className="w-3 h-3" />,
    },
    approved: {
      bg: "bg-iv-green/10 border-iv-green/20",
      text: "text-iv-green",
      icon: <CheckCircle className="w-3 h-3" />,
    },
    rejected: {
      bg: "bg-iv-danger/10 border-iv-danger/20",
      text: "text-iv-danger",
      icon: <XCircle className="w-3 h-3" />,
    },
    used: {
      bg: "bg-iv-cyan/10 border-iv-cyan/20",
      text: "text-iv-cyan",
      icon: <CheckCircle className="w-3 h-3" />,
    },
  };
  const s = map[status] || map.pending;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${s.bg} ${s.text}`}
    >
      {s.icon}
      {status}
    </span>
  );
}

// ── Main Component ──

export default function AdminPage() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("invites");
  const [invites, setInvites] = useState<InviteRequest[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [announcements, setAnnouncements] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);
  const [copiedLink, setCopiedLink] = useState<string | null>(null);

  // Announcement form state
  const [annForm, setAnnForm] = useState({
    title: "",
    message: "",
    type: "info" as "info" | "success" | "warning" | "critical",
    expires_at: "",
  });
  const [annFormLoading, setAnnFormLoading] = useState(false);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [inv, usr, ann] = await Promise.all([
        api.adminListInvites(),
        api.adminListUsers(),
        api.adminListAnnouncements(),
      ]);
      setInvites(inv);
      setUsers(usr);
      setAnnouncements(ann);
    } catch {
      showToast("Failed to load data", "err");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && user && !user.is_superuser) {
      router.replace("/");
    }
    if (!authLoading && !user) {
      router.replace("/login");
    }
  }, [authLoading, user, router]);

  useEffect(() => {
    if (user?.is_superuser) fetchData();
  }, [user, fetchData]);

  if (authLoading || !user?.is_superuser) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-iv-border border-t-iv-green" />
      </div>
    );
  }

  // ── Actions ──

  const handleApprove = async (email: string) => {
    setActionLoading(email);
    try {
      const res = await api.adminApproveInvite(email);
      showToast(`Approved ${email}`);
      // Offer link copy
      if (res.invite_link) {
        setCopiedLink(res.invite_link);
      }
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Approve failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (email: string) => {
    setActionLoading(email);
    try {
      await api.adminRejectInvite(email);
      showToast(`Rejected ${email}`);
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Reject failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePromote = async (email: string) => {
    setActionLoading(email);
    try {
      await api.adminPromoteUser(email);
      showToast(`${email} promoted to admin`);
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Promote failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDemote = async (email: string) => {
    if (email === user.email) {
      showToast("Cannot demote yourself", "err");
      return;
    }
    setActionLoading(email);
    try {
      await api.adminDemoteUser(email);
      showToast(`${email} demoted`);
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Demote failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteUser = async (u: AdminUser) => {
    if (u.id === user.id) {
      showToast("Cannot delete your own account", "err");
      return;
    }
    if (!window.confirm(`Delete user "${u.email}"? This will remove all their data permanently.`)) return;
    setActionLoading(u.id);
    try {
      await api.adminDeleteUser(u.id);
      showToast(`User ${u.email} deleted`);
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Delete failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCreateAnnouncement = async () => {
    if (!annForm.title.trim() || !annForm.message.trim()) {
      showToast("Title and message are required", "err");
      return;
    }
    setAnnFormLoading(true);
    try {
      await api.adminCreateAnnouncement({
        title: annForm.title.trim(),
        message: annForm.message.trim(),
        type: annForm.type,
        expires_at: annForm.expires_at ? new Date(annForm.expires_at).toISOString() : null,
      });
      showToast("Announcement created");
      setAnnForm({ title: "", message: "", type: "info", expires_at: "" });
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Create failed", "err");
    } finally {
      setAnnFormLoading(false);
    }
  };

  const handleDeleteAnnouncement = async (ann: Announcement) => {
    if (!window.confirm(`Delete announcement "${ann.title}"?`)) return;
    setActionLoading(`ann-${ann.id}`);
    try {
      await api.adminDeleteAnnouncement(ann.id);
      showToast("Announcement deleted");
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Delete failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteInvite = async (inv: InviteRequest) => {
    if (!window.confirm(`Delete invite for "${inv.email}"?`)) return;
    setActionLoading(`del-${inv.id}`);
    try {
      await api.adminDeleteInvite(inv.id);
      showToast(`Invite for ${inv.email} deleted`);
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Delete failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResendInvite = async (inv: InviteRequest) => {
    setActionLoading(`resend-${inv.id}`);
    try {
      const res = await api.adminResendInvite(inv.email);
      showToast(`Invite resent to ${inv.email}`);
      if (res.invite_link) setCopiedLink(res.invite_link);
      await fetchData();
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : "Resend failed", "err");
    } finally {
      setActionLoading(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    showToast("Link copied!");
    setCopiedLink(null);
  };

  // ── Stats ──

  const pendingCount = invites.filter((i) => i.status === "pending").length;
  const approvedCount = invites.filter((i) => i.status === "approved" || i.status === "used").length;
  const totalUsers = users.length;
  const adminCount = users.filter((u) => u.is_superuser).length;
  const activeAnnouncementsCount = announcements.filter((a) => a.is_active).length;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-iv-green to-iv-cyan flex items-center justify-center">
          <Shield className="w-5 h-5 text-iv-black" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-iv-text">Admin Console</h1>
          <p className="text-sm text-iv-muted">Manage invites and users</p>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-6 right-6 z-50 px-4 py-3 rounded-lg text-sm font-medium shadow-lg border transition-all ${
            toast.type === "ok"
              ? "bg-iv-green/10 border-iv-green/30 text-iv-green"
              : "bg-iv-danger/10 border-iv-danger/30 text-iv-danger"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Copied link banner */}
      {copiedLink && (
        <div className="bg-iv-cyan/10 border border-iv-cyan/20 rounded-lg px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-iv-cyan font-medium mb-1">Invite link generated</p>
            <p className="text-xs text-iv-muted font-mono truncate">{copiedLink}</p>
          </div>
          <button
            onClick={() => copyToClipboard(copiedLink)}
            className="flex-shrink-0 p-2 rounded-lg hover:bg-iv-cyan/10 text-iv-cyan transition-colors"
          >
            <Copy className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Pending", value: pendingCount, color: "text-amber-400", bg: "bg-amber-500/10" },
          { label: "Approved", value: approvedCount, color: "text-iv-green", bg: "bg-iv-green/10" },
          { label: "Users", value: totalUsers, color: "text-iv-cyan", bg: "bg-iv-cyan/10" },
          { label: "Admins", value: adminCount, color: "text-purple-400", bg: "bg-purple-500/10" },
          { label: "Broadcasts", value: activeAnnouncementsCount, color: "text-orange-400", bg: "bg-orange-500/10" },
        ].map((s) => (
          <div
            key={s.label}
            className="glass rounded-xl p-4 border border-iv-border"
          >
            <p className="text-xs text-iv-muted font-medium mb-1">{s.label}</p>
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-iv-surface/50 rounded-lg p-1 w-fit">
        {(
          [
            { id: "invites" as Tab, label: "Invites", icon: Mail, badge: pendingCount },
            { id: "users" as Tab, label: "Users", icon: Users, badge: 0 },
            { id: "announcements" as Tab, label: "Announcements", icon: Bell, badge: activeAnnouncementsCount },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all ${
              tab === t.id
                ? "bg-iv-charcoal text-iv-text shadow-sm"
                : "text-iv-muted hover:text-iv-text"
            }`}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
            {t.badge > 0 && (
              <span className="ml-1 bg-amber-500/20 text-amber-400 text-xs font-bold px-1.5 py-0.5 rounded-full">
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-iv-muted" />
        </div>
      ) : tab === "invites" ? (
        <InvitesTable
          invites={invites}
          actionLoading={actionLoading}
          onApprove={handleApprove}
          onReject={handleReject}
          onDelete={handleDeleteInvite}
          onResend={handleResendInvite}
        />
      ) : tab === "users" ? (
        <UsersTable
          users={users}
          currentUserId={user.id}
          currentEmail={user.email}
          actionLoading={actionLoading}
          onPromote={handlePromote}
          onDemote={handleDemote}
          onDelete={handleDeleteUser}
        />
      ) : (
        <AnnouncementsPanel
          announcements={announcements}
          form={annForm}
          onFormChange={(f) => setAnnForm((prev) => ({ ...prev, ...f }))}
          onSubmit={handleCreateAnnouncement}
          formLoading={annFormLoading}
          actionLoading={actionLoading}
          onDelete={handleDeleteAnnouncement}
        />
      )}
    </div>
  );
}

// ── Invites Table ──

function InvitesTable({
  invites,
  actionLoading,
  onApprove,
  onReject,
  onDelete,
  onResend,
}: {
  invites: InviteRequest[];
  actionLoading: string | null;
  onApprove: (email: string) => void;
  onReject: (email: string) => void;
  onDelete: (inv: InviteRequest) => void;
  onResend: (inv: InviteRequest) => void;
}) {
  const [sortAsc, setSortAsc] = useState(false);
  const sorted = [...invites].sort((a, b) => {
    const diff = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    return sortAsc ? diff : -diff;
  });

  if (invites.length === 0) {
    return (
      <div className="glass rounded-xl border border-iv-border p-12 text-center">
        <Inbox className="w-10 h-10 text-iv-muted/30 mx-auto mb-3" />
        <p className="text-iv-muted text-sm">No invite requests yet</p>
      </div>
    );
  }

  return (
    <div className="glass rounded-xl border border-iv-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-iv-border">
              <th className="text-left px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                Email
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                Status
              </th>
              <th
                className="text-left px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider cursor-pointer select-none"
                onClick={() => setSortAsc(!sortAsc)}
              >
                <span className="inline-flex items-center gap-1">
                  Requested
                  {sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </span>
              </th>
              <th className="text-right px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-iv-border/50">
            {sorted.map((inv) => (
              <tr
                key={inv.id}
                className="hover:bg-iv-surface/30 transition-colors"
              >
                <td className="px-5 py-3.5">
                  <span className="text-sm text-iv-text font-medium">{inv.email}</span>
                </td>
                <td className="px-5 py-3.5">
                  <StatusBadge status={inv.status} />
                </td>
                <td className="px-5 py-3.5 text-sm text-iv-muted">
                  {timeAgo(inv.created_at)}
                </td>
                <td className="px-5 py-3.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {inv.status === "pending" && (
                      <>
                        <button
                          onClick={() => onApprove(inv.email)}
                          disabled={!!actionLoading}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-iv-green/10 text-iv-green border border-iv-green/20 hover:bg-iv-green/20 transition-colors disabled:opacity-50"
                        >
                          {actionLoading === inv.email ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <CheckCircle className="w-3 h-3" />
                          )}
                          Approve
                        </button>
                        <button
                          onClick={() => onReject(inv.email)}
                          disabled={!!actionLoading}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-iv-danger/10 text-iv-danger border border-iv-danger/20 hover:bg-iv-danger/20 transition-colors disabled:opacity-50"
                        >
                          <XCircle className="w-3 h-3" />
                          Reject
                        </button>
                      </>
                    )}
                    {inv.status === "approved" && (
                      <button
                        onClick={() => onResend(inv)}
                        disabled={!!actionLoading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-iv-cyan/10 text-iv-cyan border border-iv-cyan/20 hover:bg-iv-cyan/20 transition-colors disabled:opacity-50"
                      >
                        {actionLoading === `resend-${inv.id}` ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Send className="w-3 h-3" />
                        )}
                        Resend
                      </button>
                    )}
                    {(inv.status === "approved" || inv.status === "pending") && (
                      <button
                        onClick={() => onDelete(inv)}
                        disabled={!!actionLoading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-iv-danger/10 text-iv-danger border border-iv-danger/20 hover:bg-iv-danger/20 transition-colors disabled:opacity-50"
                      >
                        {actionLoading === `del-${inv.id}` ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3" />
                        )}
                        Delete
                      </button>
                    )}
                    {inv.status !== "pending" && inv.status !== "approved" && (
                      <span className="text-xs text-iv-muted/50">—</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Announcements Panel ──

const ANNOUNCEMENT_TYPE_STYLES: Record<string, { bg: string; text: string; border: string; label: string }> = {
  info: { bg: "bg-iv-cyan/10", text: "text-iv-cyan", border: "border-iv-cyan/20", label: "Info" },
  success: { bg: "bg-iv-green/10", text: "text-iv-green", border: "border-iv-green/20", label: "Success" },
  warning: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20", label: "Warning" },
  critical: { bg: "bg-iv-danger/10", text: "text-iv-danger", border: "border-iv-danger/20", label: "Critical" },
};

function AnnouncementsPanel({
  announcements,
  form,
  onFormChange,
  onSubmit,
  formLoading,
  actionLoading,
  onDelete,
}: {
  announcements: Announcement[];
  form: { title: string; message: string; type: "info" | "success" | "warning" | "critical"; expires_at: string };
  onFormChange: (f: Partial<{ title: string; message: string; type: "info" | "success" | "warning" | "critical"; expires_at: string }>) => void;
  onSubmit: () => void;
  formLoading: boolean;
  actionLoading: string | null;
  onDelete: (ann: Announcement) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Create form */}
      <div className="glass rounded-xl border border-iv-border p-6 space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <PlusCircle className="w-4 h-4 text-iv-green" />
          <h3 className="text-sm font-semibold text-iv-text">New Announcement</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-iv-muted mb-1.5 font-medium">Title</label>
            <input
              type="text"
              value={form.title}
              onChange={(e) => onFormChange({ title: e.target.value })}
              placeholder="e.g. Scheduled maintenance tonight"
              className="w-full bg-iv-surface border border-iv-border rounded-lg px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green/50"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-iv-muted mb-1.5 font-medium">Type</label>
              <select
                value={form.type}
                onChange={(e) => onFormChange({ type: e.target.value as "info" | "success" | "warning" | "critical" })}
                className="w-full bg-iv-surface border border-iv-border rounded-lg px-3 py-2 text-sm text-iv-text focus:outline-none focus:border-iv-green/50"
              >
                <option value="info">Info</option>
                <option value="success">Success</option>
                <option value="warning">Warning</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-iv-muted mb-1.5 font-medium">Expires at (optional)</label>
              <input
                type="datetime-local"
                value={form.expires_at}
                onChange={(e) => onFormChange({ expires_at: e.target.value })}
                className="w-full bg-iv-surface border border-iv-border rounded-lg px-3 py-2 text-sm text-iv-text focus:outline-none focus:border-iv-green/50"
              />
            </div>
          </div>
        </div>
        <div>
          <label className="block text-xs text-iv-muted mb-1.5 font-medium">Message</label>
          <textarea
            value={form.message}
            onChange={(e) => onFormChange({ message: e.target.value })}
            placeholder="Announcement content visible to all users…"
            rows={3}
            className="w-full bg-iv-surface border border-iv-border rounded-lg px-3 py-2 text-sm text-iv-text placeholder:text-iv-muted/50 focus:outline-none focus:border-iv-green/50 resize-none"
          />
        </div>
        <button
          onClick={onSubmit}
          disabled={formLoading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-iv-green/15 text-iv-green border border-iv-green/25 hover:bg-iv-green/25 transition-colors disabled:opacity-50"
        >
          {formLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          Broadcast
        </button>
      </div>

      {/* List */}
      {announcements.length === 0 ? (
        <div className="glass rounded-xl border border-iv-border p-12 text-center">
          <Bell className="w-10 h-10 text-iv-muted/30 mx-auto mb-3" />
          <p className="text-iv-muted text-sm">No announcements yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {announcements.map((ann) => {
            const s = ANNOUNCEMENT_TYPE_STYLES[ann.type] || ANNOUNCEMENT_TYPE_STYLES.info;
            return (
              <div
                key={ann.id}
                className={`glass rounded-xl border p-4 flex items-start gap-4 ${s.border}`}
              >
                <div className={`mt-0.5 p-2 rounded-lg ${s.bg}`}>
                  <Info className={`w-4 h-4 ${s.text}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-iv-text">{ann.title}</span>
                    <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full ${s.bg} ${s.text} border ${s.border}`}>
                      {s.label}
                    </span>
                    {!ann.is_active && (
                      <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-full bg-iv-muted/10 text-iv-muted border border-iv-border">
                        Expired
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-iv-muted leading-relaxed">{ann.message}</p>
                  <p className="text-[10px] text-iv-muted/50 mt-1.5">
                    Created {timeAgo(ann.created_at)}
                    {ann.expires_at && ` · Expires ${new Date(ann.expires_at).toLocaleDateString()}`}
                  </p>
                </div>
                <button
                  onClick={() => onDelete(ann)}
                  disabled={!!actionLoading}
                  className="flex-shrink-0 p-2 rounded-lg text-iv-muted hover:text-iv-danger hover:bg-iv-danger/10 transition-colors disabled:opacity-50"
                >
                  {actionLoading === `ann-${ann.id}` ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4" />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Users Table ──

function UsersTable({
  users,
  currentUserId,
  currentEmail,
  actionLoading,
  onPromote,
  onDemote,
  onDelete,
}: {
  users: AdminUser[];
  currentUserId: string;
  currentEmail: string;
  actionLoading: string | null;
  onPromote: (email: string) => void;
  onDemote: (email: string) => void;
  onDelete: (u: AdminUser) => void;
}) {
  if (users.length === 0) {
    return (
      <div className="glass rounded-xl border border-iv-border p-12 text-center">
        <Users className="w-10 h-10 text-iv-muted/30 mx-auto mb-3" />
        <p className="text-iv-muted text-sm">No users registered</p>
      </div>
    );
  }

  return (
    <div className="glass rounded-xl border border-iv-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-iv-border">
              <th className="text-left px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                User
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                Role
              </th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                Joined
              </th>
              <th className="text-right px-5 py-3 text-xs font-semibold text-iv-muted uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-iv-border/50">
            {users.map((u) => (
              <tr
                key={u.id}
                className="hover:bg-iv-surface/30 transition-colors"
              >
                <td className="px-5 py-3.5">
                  <div>
                    <span className="text-sm text-iv-text font-medium">
                      {u.display_name || u.email.split("@")[0]}
                    </span>
                    {u.email === currentEmail && (
                      <span className="ml-2 text-[10px] text-iv-cyan font-medium">(you)</span>
                    )}
                    <p className="text-xs text-iv-muted mt-0.5">{u.email}</p>
                  </div>
                </td>
                <td className="px-5 py-3.5">
                  {u.is_superuser ? (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-500/10 border border-purple-500/20 text-purple-400">
                      <Crown className="w-3 h-3" />
                      Admin
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-iv-surface border border-iv-border text-iv-muted">
                      <Users className="w-3 h-3" />
                      User
                    </span>
                  )}
                </td>
                <td className="px-5 py-3.5 text-sm text-iv-muted">
                  {u.created_at ? timeAgo(u.created_at) : "—"}
                </td>
                <td className="px-5 py-3.5 text-right">
                  {u.id === currentUserId ? (
                    <span className="text-xs text-iv-muted/50">—</span>
                  ) : (
                    <div className="flex items-center justify-end gap-2">
                      {u.is_superuser ? (
                        <button
                          onClick={() => onDemote(u.email)}
                          disabled={!!actionLoading}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-iv-danger/10 text-iv-danger border border-iv-danger/20 hover:bg-iv-danger/20 transition-colors disabled:opacity-50"
                        >
                          {actionLoading === u.email ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <UserMinus className="w-3 h-3" />
                          )}
                          Demote
                        </button>
                      ) : (
                        <button
                          onClick={() => onPromote(u.email)}
                          disabled={!!actionLoading}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20 transition-colors disabled:opacity-50"
                        >
                          {actionLoading === u.email ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <Crown className="w-3 h-3" />
                          )}
                          Promote
                        </button>
                      )}
                      <button
                        onClick={() => onDelete(u)}
                        disabled={!!actionLoading}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-iv-danger/10 text-iv-danger border border-iv-danger/20 hover:bg-iv-danger/20 transition-colors disabled:opacity-50"
                      >
                        {actionLoading === u.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3" />
                        )}
                        Delete
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
