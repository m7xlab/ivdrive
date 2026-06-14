"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { X, Send, Bot, Loader2, MessageSquare, Trash2, Plus, Sparkles } from "lucide-react";
import { chatApi, ChatMessage, SessionInfo } from "@/lib/api/chat";
import { ChartRenderer } from "./ChartRenderer";
import { useAuth } from "@/lib/auth-context";

const MAX_SESSIONS = 15;
const MAX_MESSAGES = 50;

function parseMessageContent(content: string) {
  // Regex to match ```json_chart ... ``` — tolerate any/no whitespace after the
  // language tag, since the LLM doesn't always emit a leading newline.
  const regex = /```json_chart\s*([\s\S]*?)```/g;
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: content.substring(lastIndex, match.index) });
    }
    parts.push({ type: "chart", content: match[1] });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: "text", content: content.substring(lastIndex) });
  }

  return parts.length > 0 ? parts : [{ type: "text", content }];
}

function SourceBadge({ type, score }: { type: string; score: number }) {
  const labels: Record<string, string> = {
    trip_summary: "Trip",
    charging_event: "Charge",
    vehicle_stats: "Stats",
    location: "Place",
    all_vehicles_summary: "Fleet",
    battery_health_summary: "Battery",
  };
  return (
    <span className="text-[10px] uppercase font-medium px-2 py-0.5 rounded-full bg-iv-surface text-iv-muted">
      {labels[type] || type} {score > 0.9 ? "✓" : ""}
    </span>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-1.5 px-4 py-3 bg-iv-surface rounded-2xl rounded-bl-sm w-fit">
      <span className="w-1.5 h-1.5 rounded-full bg-iv-muted animate-bounce" style={{ animationDelay: "0ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-iv-muted animate-bounce" style={{ animationDelay: "150ms" }} />
      <span className="w-1.5 h-1.5 rounded-full bg-iv-muted animate-bounce" style={{ animationDelay: "300ms" }} />
    </div>
  );
}

export function IVDriveAIWidget() {
  const { user } = useAuth();
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

  useEffect(() => {
    if (isOpen) {
      chatApi.listSessions().then(setSessions).catch(() => {});
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && messages.length === 0 && !currentSessionId) {
      setMessages([
        {
          role: "assistant",
          content: "Hello! I'm iVDrive AI. Ask me anything about your vehicles — trips, charging, consumption, range, and more. All answers are based only on your real vehicle data.",
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

  const handleNewSession = () => {
    setCurrentSessionId(null);
    setMessages([{
      role: "assistant",
      content: "Starting a new conversation. What would you like to know?",
    }]);
    setShowSessions(false);
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await chatApi.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        handleNewSession();
      }
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  const handleDeleteAllSessions = async () => {
    try {
      await chatApi.deleteAllSessions();
      setSessions([]);
      handleNewSession();
    } catch (err) {
      console.error("Failed to delete all sessions", err);
    }
  };

  // Grow the input up to max-h-32 (128px) as the user types, then collapse back.
  const adjustInputHeight = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "44px";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    adjustInputHeight();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg: ChatMessage = { role: "user", content: trimmed };
    // Add the user message AND an empty assistant placeholder we stream into.
    setMessages((prev) => [...prev.slice(-MAX_MESSAGES + 1), userMsg, { role: "assistant", content: "" }]);
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "44px";
    setIsLoading(true);
    setError(null);

    let acc = "";
    const setAssistant = (content: string, sources?: ChatMessage["sources"]) => {
      setMessages((prev) => {
        const copy = [...prev];
        // The assistant placeholder is always the last message.
        copy[copy.length - 1] = { role: "assistant", content, sources };
        return copy;
      });
    };

    try {
      await chatApi.sendMessageStream(trimmed, currentSessionId, {
        onDelta: (text) => {
          acc += text;
          setAssistant(acc);
        },
        onDone: ({ session_id, sources }) => {
          setAssistant(acc, sources);
          if (session_id && session_id !== currentSessionId) {
            setCurrentSessionId(session_id);
            chatApi.listSessions().then(setSessions).catch(() => {});
          }
          if (!isOpen) setUnread(true);
        },
        onError: (detail) => {
          setError(detail);
          setAssistant(`Error: ${detail}`);
        },
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to get response";
      setError(message);
      setAssistant(`Error: ${message}`);
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

  // Premium tier check — hide entirely if not enabled
  if (!user || !user.ai_enabled) {
    return null;
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 w-[60px] h-[60px] rounded-full bg-[#007AFF] shadow-xl shadow-blue-500/30 hover:scale-105 hover:shadow-2xl transition-all duration-300 flex items-center justify-center group border border-white/10 backdrop-blur-md"
        aria-label="Open iVDrive AI Assistant"
      >
        {unread && (
          <span className="absolute 0 top-0 right-0 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center border-2 border-iv-black shadow-sm" />
        )}
        <MessageSquare className="w-7 h-7 text-white group-hover:scale-110 transition-transform duration-300" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-[400px] h-[600px] flex flex-col bg-iv-charcoal/80 dark:bg-iv-black/80 backdrop-blur-2xl border border-iv-border rounded-[2rem] shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 duration-300 ease-out">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-iv-border bg-iv-charcoal/40 dark:bg-iv-black/20 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-[#007AFF] to-[#34C759] flex items-center justify-center shadow-inner">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-iv-text tracking-tight">iVDrive Intelligence</p>
              {user.ai_tier !== "free" && (
                <span className="text-[9px] uppercase font-bold px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">
                  {user.ai_tier}
                </span>
              )}
            </div>
            <p className="text-xs text-iv-muted font-medium">
              {currentSessionId ? "Active Session" : "New Chat"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setShowSessions(!showSessions)}
            className={`p-2 rounded-full transition-colors ${showSessions ? "bg-iv-surface" : "hover:bg-iv-surface"}`}
          >
            <MessageSquare className="w-4 h-4 text-iv-muted" />
          </button>
          <button
            onClick={handleNewSession}
            className="p-2 rounded-full hover:bg-iv-surface transition-colors"
          >
            <Plus className="w-4 h-4 text-iv-muted" />
          </button>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 rounded-full hover:bg-iv-surface transition-colors"
          >
            <X className="w-4 h-4 text-iv-muted" />
          </button>
        </div>
      </div>

      {/* Sessions sidebar overlay */}
      {showSessions && (
        <div className="absolute top-[73px] left-0 right-0 z-10 bg-iv-charcoal/90 dark:bg-iv-black/95 backdrop-blur-xl border-b border-iv-border shadow-lg max-h-80 overflow-y-auto rounded-b-3xl flex flex-col">
          <div className="p-2 flex-1 overflow-y-auto">
            {sessions.length === 0 ? (
              <p className="p-4 text-center text-xs text-iv-muted">No previous sessions</p>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => handleSelectSession(s.id)}
                  className={`flex items-center justify-between p-3 rounded-2xl cursor-pointer transition-colors group ${
                    s.id === currentSessionId ? "bg-blue-500/10 text-blue-500" : "hover:bg-iv-surface text-iv-text"
                  }`}
                >
                  <div className="truncate">
                    <p className="text-sm font-medium">
                      {new Date(s.last_message_at || s.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </p>
                    <p className="text-xs opacity-60">{s.message_count} messages</p>
                  </div>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    className="p-1.5 opacity-0 group-hover:opacity-100 transition-opacity rounded-full hover:bg-red-500/10 hover:text-red-500 text-iv-muted"
                    aria-label="Delete session"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>
          {sessions.length > 0 && (
            <div className="p-2 border-t border-iv-border bg-iv-charcoal/50 dark:bg-iv-black/20 shrink-0">
              <button
                onClick={handleDeleteAllSessions}
                className="w-full py-2.5 text-xs font-semibold text-red-500 hover:bg-red-500/10 rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                <Trash2 className="w-4 h-4" /> Clear All History
              </button>
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5 no-scrollbar">
        {messages.map((msg, i) => (
          // While the assistant reply is still streaming (placeholder empty),
          // show the typing indicator in its place instead of an empty bubble.
          msg.role === "assistant" && msg.content === "" ? (
            <TypingIndicator key={i} />
          ) : (
          <div
            key={i}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
          >
            <div
              className={`max-w-[85%] px-4 py-2.5 text-[15px] leading-relaxed shadow-sm ${
                msg.role === "user"
                  ? "bg-[#007AFF] text-white rounded-2xl rounded-br-sm"
                  : "bg-iv-surface text-iv-text border border-iv-border rounded-2xl rounded-bl-sm"
              }`}
            >
              {parseMessageContent(msg.content).map((part, idx) => (
                <div key={idx}>
                  {part.type === "text" && <span className="whitespace-pre-wrap">{part.content}</span>}
                  {part.type === "chart" && <ChartRenderer chartJson={part.content} />}
                </div>
              ))}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2 px-1">
                {msg.sources.map((src) => (
                  <SourceBadge key={src.id} type={src.type} score={src.score} />
                ))}
              </div>
            )}
          </div>
          )
        ))}
        {error && <div className="text-xs text-red-500 px-2">{error}</div>}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 bg-iv-charcoal/50 dark:bg-iv-black/20 backdrop-blur-md border-t border-iv-border shrink-0">
        <form onSubmit={handleSubmit} className="relative flex items-end gap-2 bg-iv-surface rounded-3xl p-1 shadow-inner border border-iv-border">
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your vehicle..."
            className="flex-1 bg-transparent border-none px-4 py-2.5 text-[15px] text-iv-text placeholder:text-iv-muted resize-none focus:outline-none focus:ring-0 max-h-32 min-h-[44px]"
            rows={1}
            style={{ height: "44px" }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="w-9 h-9 mb-1 mr-1 rounded-full bg-[#007AFF] hover:bg-blue-600 disabled:bg-black/10 dark:disabled:bg-white/10 disabled:text-black/30 dark:disabled:text-white/30 flex items-center justify-center transition-all shrink-0 text-white"
          >
            {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4 ml-0.5" />}
          </button>
        </form>
        <div className="text-center mt-2">
          <span className="text-[10px] font-medium text-black/40 dark:text-white/40 tracking-wide uppercase">iVDrive AI Engine</span>
        </div>
      </div>
    </div>
  );
}
