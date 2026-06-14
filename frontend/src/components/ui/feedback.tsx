"use client";

/**
 * App-wide feedback primitives styled to the iVDrive design system.
 *
 *   const confirm = useConfirm();
 *   if (await confirm({ title, message, variant: "danger", confirmText: "Delete" })) { ... }
 *
 *   const toast = useToast();
 *   toast.error("Failed to save");   toast.success("Saved");
 *
 * Replaces the native window.confirm()/alert() dialogs. Mount <FeedbackProvider>
 * once near the app root.
 */
import {
  createContext, useCallback, useContext, useRef, useState, type ReactNode,
} from "react";
import {
  AlertTriangle, CheckCircle2, Info, XCircle, X,
} from "lucide-react";

// ─── Confirm ──────────────────────────────────────────────────────────────
type ConfirmVariant = "default" | "danger";
type ConfirmOptions = {
  title: string;
  message?: ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: ConfirmVariant;
};
type PendingConfirm = ConfirmOptions & { resolve: (ok: boolean) => void };

const ConfirmCtx = createContext<(o: ConfirmOptions) => Promise<boolean>>(
  async () => false,
);
export const useConfirm = () => useContext(ConfirmCtx);

// ─── Toast ──────────────────────────────────────────────────────────────────
type ToastType = "success" | "error" | "info" | "warning";
type ToastItem = { id: number; type: ToastType; message: ReactNode };
type ToastApi = {
  show: (type: ToastType, message: ReactNode) => void;
  success: (m: ReactNode) => void;
  error: (m: ReactNode) => void;
  info: (m: ReactNode) => void;
  warning: (m: ReactNode) => void;
};

const ToastCtx = createContext<ToastApi>({
  show: () => {}, success: () => {}, error: () => {}, info: () => {}, warning: () => {},
});
export const useToast = () => useContext(ToastCtx);

// ─── Provider ────────────────────────────────────────────────────────────────
export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const confirm = useCallback((opts: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setPending({ ...opts, resolve });
    });
  }, []);

  const close = useCallback((ok: boolean) => {
    setPending((p) => {
      p?.resolve(ok);
      return null;
    });
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const show = useCallback((type: ToastType, message: ReactNode) => {
    const id = ++idRef.current;
    setToasts((t) => [...t, { id, type, message }]);
    setTimeout(() => dismiss(id), 4500);
  }, [dismiss]);

  const toastApi: ToastApi = {
    show,
    success: (m) => show("success", m),
    error: (m) => show("error", m),
    info: (m) => show("info", m),
    warning: (m) => show("warning", m),
  };

  return (
    <ConfirmCtx.Provider value={confirm}>
      <ToastCtx.Provider value={toastApi}>
        {children}
        {pending && <ConfirmDialog pending={pending} onClose={close} />}
        <ToastViewport toasts={toasts} onDismiss={dismiss} />
      </ToastCtx.Provider>
    </ConfirmCtx.Provider>
  );
}

// ─── Confirm dialog ──────────────────────────────────────────────────────────
function ConfirmDialog({ pending, onClose }: {
  pending: PendingConfirm; onClose: (ok: boolean) => void;
}) {
  const danger = pending.variant === "danger";
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
      <div
        role="button"
        tabIndex={0}
        aria-label="Cancel"
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => onClose(false)}
        onKeyDown={(e) => e.key === "Escape" && onClose(false)}
      />
      <div className="glass iv-pop-in relative w-full max-w-sm rounded-2xl p-6">
        <div className="flex items-start gap-3 mb-2">
          <span className={`shrink-0 mt-0.5 p-1.5 rounded-lg ${danger ? "bg-red-500/15 text-red-400" : "bg-iv-cyan/15 text-iv-cyan"}`}>
            <AlertTriangle size={18} />
          </span>
          <h2 className="text-lg font-semibold text-iv-text leading-snug">{pending.title}</h2>
        </div>
        {pending.message && (
          <p className="text-sm text-iv-muted leading-relaxed mb-6 pl-[2.6rem]">{pending.message}</p>
        )}
        <div className="flex gap-3">
          <button
            onClick={() => onClose(false)}
            className="flex-1 rounded-xl border border-iv-border px-4 py-2.5 text-sm font-medium text-iv-muted transition-colors hover:bg-iv-surface hover:text-iv-text"
          >
            {pending.cancelText || "Cancel"}
          </button>
          <button
            autoFocus
            onClick={() => onClose(true)}
            className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all ${
              danger
                ? "bg-red-500/20 text-red-400 hover:bg-red-500/30"
                : "bg-iv-cyan/20 text-iv-cyan hover:bg-iv-cyan/30"
            }`}
          >
            {pending.confirmText || "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Toast viewport ──────────────────────────────────────────────────────────
const TOAST_STYLE: Record<ToastType, { icon: ReactNode; accent: string }> = {
  success: { icon: <CheckCircle2 size={18} />, accent: "text-emerald-400" },
  error: { icon: <XCircle size={18} />, accent: "text-red-400" },
  info: { icon: <Info size={18} />, accent: "text-iv-cyan" },
  warning: { icon: <AlertTriangle size={18} />, accent: "text-amber-400" },
};

function ToastViewport({ toasts, onDismiss }: {
  toasts: ToastItem[]; onDismiss: (id: number) => void;
}) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed top-4 right-4 z-[300] flex flex-col gap-2 w-full max-w-sm pointer-events-none">
      {toasts.map((t) => {
        const s = TOAST_STYLE[t.type];
        return (
          <div
            key={t.id}
            className="glass iv-toast-in pointer-events-auto flex items-start gap-3 rounded-xl px-4 py-3 shadow-lg"
          >
            <span className={`shrink-0 mt-0.5 ${s.accent}`}>{s.icon}</span>
            <div className="flex-1 text-sm text-iv-text leading-snug">{t.message}</div>
            <button
              onClick={() => onDismiss(t.id)}
              className="shrink-0 text-iv-muted hover:text-iv-text transition-colors"
              aria-label="Dismiss"
            >
              <X size={15} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
