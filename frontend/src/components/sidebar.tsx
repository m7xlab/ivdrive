"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Sun,
  Moon,
  Shield,
  Bell,
  X,
  Info,
  CheckCircle,
  AlertTriangle,
  AlertOctagon,
} from "lucide-react";
import { useState, useEffect, useCallback, useRef } from "react";
import { useTheme } from "next-themes";
import { useAuth } from "@/lib/auth-context";
import { api } from "@/lib/api";

// ── Types ──────────────────────────────────────────────────────────────────────

interface UserAnnouncement {
  id: string;
  title: string;
  message: string;
  type: "info" | "success" | "warning" | "critical";
  created_at: string;
  expires_at: string | null;
  dismissed: boolean;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const TYPE_ICON: Record<string, React.ReactNode> = {
  info: <Info className="w-4 h-4 text-iv-cyan" />,
  success: <CheckCircle className="w-4 h-4 text-iv-green" />,
  warning: <AlertTriangle className="w-4 h-4 text-amber-400" />,
  critical: <AlertOctagon className="w-4 h-4 text-iv-danger" />,
};

const TYPE_STYLE: Record<string, { border: string; bg: string; text: string }> = {
  info: { border: "border-iv-cyan/20", bg: "bg-iv-cyan/5", text: "text-iv-cyan" },
  success: { border: "border-iv-green/20", bg: "bg-iv-green/5", text: "text-iv-green" },
  warning: { border: "border-amber-500/20", bg: "bg-amber-500/5", text: "text-amber-400" },
  critical: { border: "border-iv-danger/20", bg: "bg-iv-danger/5", text: "text-iv-danger" },
};

const DISMISSED_KEY = "ivdrive_dismissed_announcements";

function getLocallyDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(DISMISSED_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function addLocallyDismissed(id: string): void {
  const set = getLocallyDismissed();
  set.add(id);
  localStorage.setItem(DISMISSED_KEY, JSON.stringify([...set]));
}

// ── Nav ────────────────────────────────────────────────────────────────────────

const navItems = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/settings", icon: Settings, label: "Settings" },
  { href: "/admin", icon: Shield, label: "Admin", superuserOnly: true },
] as const;

// ── Main Component ─────────────────────────────────────────────────────────────

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Announcements state
  const [announcements, setAnnouncements] = useState<UserAnnouncement[]>([]);
  const [bellOpen, setBellOpen] = useState(false);
  const [modalAnn, setModalAnn] = useState<UserAnnouncement | null>(null);
  const bellRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  // Fetch announcements
  const fetchAnnouncements = useCallback(async () => {
    if (!user) return;
    try {
      const data: UserAnnouncement[] = await api.getUserAnnouncements();
      setAnnouncements(data);

      // Show modal for first undismissed critical announcement (once per session)
      const locallyDismissed = getLocallyDismissed();
      const criticalUndismissed = data.find(
        (a) => a.type === "critical" && !a.dismissed && !locallyDismissed.has(a.id)
      );
      if (criticalUndismissed) {
        setModalAnn(criticalUndismissed);
      }
    } catch {
      // silently ignore
    }
  }, [user]);

  useEffect(() => {
    fetchAnnouncements();
    // Refresh every 5 minutes
    const interval = setInterval(fetchAnnouncements, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchAnnouncements]);

  // Close popover on outside click
  useEffect(() => {
    if (!bellOpen) return;
    const handler = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setBellOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [bellOpen]);

  const undismissedCount = announcements.filter((a) => !a.dismissed).length;

  const handleDismiss = async (id: string) => {
    addLocallyDismissed(id);
    setAnnouncements((prev) =>
      prev.map((a) => (a.id === id ? { ...a, dismissed: true } : a))
    );
    try {
      await api.dismissAnnouncement(id);
    } catch {
      // best-effort
    }
  };

  const handleModalDismiss = async () => {
    if (!modalAnn) return;
    await handleDismiss(modalAnn.id);
    setModalAnn(null);
  };

  return (
    <>
      {/* ── Critical announcement modal ─────────────────────────────────── */}
      {modalAnn && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 backdrop-blur-sm px-4">
          <div
            className={`bg-iv-charcoal border rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 ${
              TYPE_STYLE[modalAnn.type]?.border || "border-iv-border"
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className={`mt-0.5 p-2 rounded-lg ${TYPE_STYLE[modalAnn.type]?.bg || "bg-iv-surface"}`}
              >
                {TYPE_ICON[modalAnn.type] || TYPE_ICON.info}
              </div>
              <div className="flex-1">
                <h2 className="text-base font-bold text-iv-text">{modalAnn.title}</h2>
                <span
                  className={`text-[10px] font-bold uppercase ${
                    TYPE_STYLE[modalAnn.type]?.text || "text-iv-muted"
                  }`}
                >
                  {modalAnn.type}
                </span>
              </div>
            </div>
            <p className="text-sm text-iv-muted leading-relaxed">{modalAnn.message}</p>
            <button
              onClick={handleModalDismiss}
              className="w-full py-2.5 rounded-lg text-sm font-semibold bg-iv-green/15 text-iv-green border border-iv-green/25 hover:bg-iv-green/25 transition-colors"
            >
              Got it
            </button>
          </div>
        </div>
      )}

      {/* ── Sidebar (desktop only) ──────────────────────────────────────── */}
      <aside
        className={`fixed left-0 top-0 h-screen bg-iv-charcoal/80 backdrop-blur-xl border-r border-iv-border hidden md:flex flex-col z-50 transition-all duration-300 ${
          collapsed ? "w-[72px]" : "w-[240px]"
        }`}
      >
        <div className="flex items-center gap-3 p-4 border-b border-iv-border">
          <Image
            src="/logo.png"
            alt="iVDrive"
            width={40}
            height={40}
            className="rounded-lg flex-shrink-0"
          />
          {!collapsed && (
            <div className="flex flex-col">
              <span className="text-lg font-bold leading-none">
                <span className="gradient-text">iV</span>
                <span className="text-iv-glow">Drive</span>
              </span>
              <span className="text-[10px] font-semibold text-iv-warning tracking-widest uppercase mt-0.5">
                Beta
              </span>
            </div>
          )}
        </div>

        <nav className="flex-1 py-4 space-y-1 px-2">
          {navItems
            .filter((item) => !("superuserOnly" in item && item.superuserOnly) || user?.is_superuser)
            .map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/" || pathname.startsWith("/vehicles")
                  : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all ${
                    isActive
                      ? "bg-iv-green/15 text-iv-green"
                      : "text-iv-muted hover:text-iv-text hover:bg-iv-surface"
                  }`}
                >
                  <item.icon size={20} className="flex-shrink-0" />
                  {!collapsed && <span className="text-sm font-medium">{item.label}</span>}
                </Link>
              );
            })}
        </nav>

        <div className="border-t border-iv-border p-3 space-y-2">
          {!collapsed && user && (
            <div className="px-2 py-1">
              <p className="text-xs text-iv-muted truncate">{user.email}</p>
            </div>
          )}

          {/* ── Notification Bell ─────────────────────────────────────── */}
          {user && (
            <div ref={bellRef} className="relative">
              <button
                onClick={() => setBellOpen((o) => !o)}
                className="flex items-center gap-3 px-3 py-2 rounded-lg text-iv-muted hover:text-iv-text hover:bg-iv-surface transition-all w-full relative"
                title="Announcements"
              >
                <span className="relative flex-shrink-0">
                  <Bell size={18} />
                  {undismissedCount > 0 && (
                    <span className="absolute -top-1.5 -right-1.5 w-4 h-4 text-[9px] font-bold bg-iv-danger text-white rounded-full flex items-center justify-center leading-none">
                      {undismissedCount > 9 ? "9+" : undismissedCount}
                    </span>
                  )}
                </span>
                {!collapsed && (
                  <span className="text-sm flex-1 text-left">
                    Notifications
                    {undismissedCount > 0 && (
                      <span className="ml-2 text-xs font-bold text-iv-danger">
                        ({undismissedCount})
                      </span>
                    )}
                  </span>
                )}
              </button>

              {/* Popover */}
              {bellOpen && (
                <div
                  className={`absolute bottom-full mb-2 z-[100] bg-iv-charcoal border border-iv-border rounded-xl shadow-2xl overflow-hidden ${
                    collapsed ? "left-full ml-2 w-80" : "left-0 w-80"
                  }`}
                >
                  <div className="flex items-center justify-between px-4 py-3 border-b border-iv-border">
                    <span className="text-sm font-semibold text-iv-text">Announcements</span>
                    <button
                      onClick={() => setBellOpen(false)}
                      className="text-iv-muted hover:text-iv-text transition-colors"
                    >
                      <X size={14} />
                    </button>
                  </div>
                  <div className="max-h-80 overflow-y-auto divide-y divide-iv-border/50">
                    {announcements.length === 0 ? (
                      <p className="text-xs text-iv-muted text-center py-8">No announcements</p>
                    ) : (
                      announcements.map((ann) => {
                        const s = TYPE_STYLE[ann.type] || TYPE_STYLE.info;
                        return (
                          <div
                            key={ann.id}
                            className={`px-4 py-3 transition-colors ${
                              ann.dismissed ? "opacity-50" : ""
                            } ${s.bg}`}
                          >
                            <div className="flex items-start gap-2">
                              <span className="mt-0.5 flex-shrink-0">
                                {TYPE_ICON[ann.type] || TYPE_ICON.info}
                              </span>
                              <div className="flex-1 min-w-0">
                                <p className="text-xs font-semibold text-iv-text truncate">{ann.title}</p>
                                <p className="text-xs text-iv-muted mt-0.5 leading-relaxed">{ann.message}</p>
                              </div>
                              {!ann.dismissed && (
                                <button
                                  onClick={() => handleDismiss(ann.id)}
                                  className="flex-shrink-0 text-iv-muted hover:text-iv-text transition-colors mt-0.5"
                                  title="Dismiss"
                                >
                                  <X size={12} />
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                  {undismissedCount > 0 && (
                    <div className="border-t border-iv-border px-4 py-2.5">
                      <button
                        onClick={async () => {
                          for (const a of announcements) {
                            if (!a.dismissed) await handleDismiss(a.id);
                          }
                        }}
                        className="text-xs text-iv-muted hover:text-iv-text transition-colors"
                      >
                        Dismiss all
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          <button
            onClick={() => setTheme(isDark ? "light" : "dark")}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-iv-muted hover:text-iv-text hover:bg-iv-surface transition-all w-full"
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
          >
            {mounted ? (
              isDark ? <Sun size={18} className="flex-shrink-0" /> : <Moon size={18} className="flex-shrink-0" />
            ) : (
              <Sun size={18} className="flex-shrink-0" />
            )}
            {!collapsed && <span className="text-sm">{mounted ? (isDark ? "Light Mode" : "Dark Mode") : "Theme"}</span>}
          </button>

          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-iv-muted hover:text-iv-danger hover:bg-iv-danger/10 transition-all w-full"
          >
            <LogOut size={18} className="flex-shrink-0" />
            {!collapsed && <span className="text-sm">Logout</span>}
          </button>
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center justify-center w-full py-1 text-iv-muted hover:text-iv-text transition-colors"
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>
      </aside>
    </>
  );
}

// ── Bottom Navigation Bar (mobile only) ───────────────────────────────────────

export function BottomNav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const visibleItems = navItems.filter(
    (item) => !("superuserOnly" in item && item.superuserOnly) || user?.is_superuser
  );

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex md:hidden items-stretch bg-iv-charcoal/95 backdrop-blur-xl border-t border-iv-border">
      {visibleItems.map((item) => {
        const isActive =
          item.href === "/"
            ? pathname === "/" || pathname.startsWith("/vehicles")
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`relative flex flex-1 flex-col items-center justify-center gap-1 py-3 text-[10px] font-semibold tracking-wide transition-colors ${
              isActive
                ? "text-iv-green"
                : "text-iv-muted hover:text-iv-text"
            }`}
          >
            {isActive && (
              <span className="absolute top-0 left-1/2 -translate-x-1/2 h-[2px] w-8 rounded-full bg-iv-green" />
            )}
            <item.icon size={22} />
            <span>{item.label}</span>
          </Link>
        );
      })}

      {/* Logout button as rightmost item */}
      <button
        onClick={logout}
        className="flex flex-1 flex-col items-center justify-center gap-1 py-3 text-[10px] font-semibold tracking-wide text-iv-muted hover:text-iv-danger transition-colors"
      >
        <LogOut size={22} />
        <span>Logout</span>
      </button>
    </nav>
  );
}
