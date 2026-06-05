"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { X, Send, Bot, Loader2, ChevronDown, Trash2, Plus, MessageSquare } from "lucide-react";
import { chatApi, ChatMessage, SessionInfo } from "@/lib/api/chat";

const MAX_SESSIONS = 15;
const MAX_MESSAGES = 50;

function SourceBadge({ type, score }: { type: string; score: number }) {
  const labels: Record<string, string> = {
    trip_summary: "Trip",
    charging_event: "Charge",
    vehicle_stats: "Stats",
    location: "Place",
  };
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-iv-cyan/10 text-iv-cyan border border-iv-cyan/20">
      {labels[type] || type} {score > 0.9 ? "✓" : ""}
    </span>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 p-3">
      <span className="w-2 h-2 rounded-full bg-iv-muted animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-2 h-2 rounded-full bg-iv-muted animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-2 h-2 rounded-full bg-iv-muted animate-bounce" style={{ animationDelay: "300ms" }} />
    </div>
  );
}

function SessionRow({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: SessionInfo;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const date = session.last_message_at
    ? new Date(session.last_message_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : new Date(session.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" });

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors group ${
        isActive ? "bg-iv-green/20 border border-iv-green/40" : "hover:bg-iv-surface"
      }`}
      onClick={onSelect}
    >
      <MessageSquare className="w-4 h-4 text-iv-muted shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-iv-muted">{date}</p>
        <p className="text-xs text-iv-text/70 truncate">{session.message_count} messages</p>
      </div>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(); }}
        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-iv-danger/20 text-iv-danger transition-all"
        aria-label="Delete session"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
  );
}

export function IVDriveAIWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(false);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load session list on open
  useEffect(() => {
    if (isOpen) {
      chatApi.listSessions().then(setSessions).catch(() => {});
    }
  }, [isOpen]);

  // Intro message when no session selected
  useEffect(() => {
    if (isOpen && messages.length === 0 && !currentSessionId) {
      setMessages([
        {
          role: "assistant",
          content:
            "Hello! I'm iVDrive AI. Ask me anything about your vehicles — trips, charging, consumption, range, and more. All answers are based only on your real vehicle data.",
        },
      ]);
    }
  }, [isOpen, messages.length, currentSessionId]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      setUnread(false);
    }
  }, [messages, isOpen, scrollToBottom]);

  const handleSelectSession = async (sessionId: string) => {
    if (sessionId === currentSessionId) {
      setShowSessions(false);
      return;
    }
    setIsLoading(true);
    try {
      const data = await chatApi.getSessionMessages(sessionId);
      setCurrentSessionId(sessionId);
      const loaded: ChatMessage[] = data.messages.map((m: { role: string; content: string; created_at?: string }) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
        created_at: m.created_at,
      }));
      setMessages(loaded.length > 0 ? loaded : [
        { role: "assistant", content: "Session loaded. What would you like to know?" }
      ]);
    } catch {
      setMessages([{ role: "assistant", content: "Failed to load session." }]);
    } finally {
      setIsLoading(false);
      setShowSessions(false);
    }
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await chatApi.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (sessionId === currentSessionId) {
        setCurrentSessionId(null);
        setMessages([{
          role: "assistant",
          content: "Session deleted. What would you like to know?",
        }]);
      }
    } catch {
      // silently fail
    }
  };

  const handleNewSession = () => {
    setCurrentSessionId(null);
    setMessages([{
      role: "assistant",
      content: "Starting a new conversation. What would you like to know?",
    }]);
    setShowSessions(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg: ChatMessage = { role: "user", content: trimmed };
    setMessages((prev) => [...prev.slice(-MAX_MESSAGES + 1), userMsg]);
    setInput("");
    setIsLoading(true);
    setError(null);

    try {
      const res = await chatApi.sendMessage(trimmed, currentSessionId);
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: res.answer,
        sources: res.sources,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      if (res.session_id && res.session_id !== currentSessionId) {
        setCurrentSessionId(res.session_id);
        // Refresh session list
        chatApi.listSessions().then(setSessions).catch(() => {});
      }
      if (!isOpen) setUnread(true);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to get response";
      setError(message);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${message}` },
      ]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // Collapse widget on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) setIsOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen]);

  if (!isOpen) {
    // Floating button
    return (
           <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-iv-green shadow-lg hover:bg-iv-green/90 transition-all flex items-center justify-center group md:bottom-24 md:left-4 md:right-auto"
        aria-label="Open iVDrive AI Assistant"
        title="iVDrive AI"
      >
        {unread ? (
          <span className="absolute -top-1 -right-1 w-4 h-4 bg-iv-danger rounded-full flex items-center justify-center">
            <span className="w-2 h-2 bg-white rounded-full" />
          </span>
        ) : null}
        <Bot className="w-7 h-7 text-iv-black group-hover:scale-110 transition-transform" />
      </button>
    );
  }

  // Chat panel
  return (
        <div className="fixed bottom-6 right-6 z-50 w-[380px] h-[540px] flex flex-col bg-iv-black border md:fixed md:bottom-0 md:right-0 md:w-full md:h-[92dvh] md:rounded-none md:animate-in md:slide-in-from-bottom-0"> border-iv-border rounded-2xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-iv-border bg-iv-surface shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-iv-green flex items-center justify-center">
            <Bot className="w-5 h-5 text-iv-black" />
          </div>
          <div>
            <p className="text-sm font-semibold text-iv-text">iVDrive AI</p>
            <p className="text-xs text-iv-muted">
              {currentSessionId
                ? `${messages.filter(m => m.role === "assistant").length} messages`
                : "New conversation"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowSessions(!showSessions)}
            className={`p-1.5 rounded-lg transition-colors ${showSessions ? "bg-iv-green/20 text-iv-green" : "hover:bg-iv-border/50 text-iv-muted"}`}
            aria-label="Toggle sessions"
            title="My sessions"
          >
            <MessageSquare className="w-4 h-4" />
          </button>
          <button
            onClick={handleNewSession}
            className="p-1.5 rounded-lg hover:bg-iv-border/50 text-iv-muted transition-colors"
            aria-label="New conversation"
            title="New conversation"
          >
            <Plus className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-1.5 rounded-lg hover:bg-iv-border/50 transition-colors"
            aria-label="Close chat"
          >
            <X className="w-4 h-4 text-iv-muted" />
          </button>
        </div>
      </div>

      {/* Sessions sidebar */}
      {showSessions && (
        <div className="border-b border-iv-border bg-iv-surface/80 max-h-48 overflow-y-auto">
          <div className="flex items-center justify-between px-3 py-2">
            <p className="text-xs font-semibold text-iv-muted uppercase tracking-wider">My Sessions</p>
            <button
              onClick={async () => {
                if (confirm(`Delete all ${sessions.length} sessions?`)) {
                  await chatApi.deleteAllSessions();
                  setSessions([]);
                  setCurrentSessionId(null);
                  setMessages([{
                    role: "assistant",
                    content: "All sessions deleted. What would you like to know?",
                  }]);
                }
              }}
              className="text-xs text-iv-danger hover:text-iv-danger/80 transition-colors"
            >
              Clear all
            </button>
          </div>
          {sessions.length === 0 ? (
            <p className="text-xs text-iv-muted px-3 pb-2">No sessions yet. Start a conversation!</p>
          ) : (
            <div className="px-2 pb-2 space-y-1">
              {sessions.slice(0, MAX_SESSIONS).map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  isActive={s.id === currentSessionId}
                  onSelect={() => handleSelectSession(s.id)}
                  onDelete={(e) => handleDeleteSession(s.id, e as unknown as React.MouseEvent)}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[85%] px-3 py-2 rounded-2xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-iv-green text-iv-black rounded-br-md"
                  : "bg-iv-surface text-iv-text border border-iv-border rounded-bl-md"
              }`}
            >
              {msg.content}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-1 px-1">
                {msg.sources.map((src) => (
                  <SourceBadge key={src.id} type={src.type} score={src.score} />
                ))}
              </div>
            )}
          </div>
        ))}

        {isLoading && <TypingIndicator />}

        {error && (
          <div className="flex items-center gap-2 text-xs text-iv-danger px-2">
            <span>{error}</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-iv-border bg-iv-surface/50 pb-[calc(3rem+env(safe-area-inset-bottom))] md:pb-3">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your vehicle..."
            className="flex-1 bg-iv-surface border border-iv-border rounded-xl px-3 py-2 text-sm text-iv-text placeholder-iv-muted resize-none focus:outline-none focus:border-iv-green/50 transition-colors"
            rows={1}
            style={{ minHeight: "38px", maxHeight: "80px" }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="w-9 h-9 rounded-xl bg-iv-green hover:bg-iv-green/90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors shrink-0"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 text-iv-black animate-spin" />
            ) : (
              <Send className="w-4 h-4 text-iv-black" />
            )}
          </button>
        </form>
        <p className="text-xs text-iv-muted/50 mt-1 text-center">
          {sessions.length}/{MAX_SESSIONS} sessions stored
        </p>
      </div>
    </div>
  );
}