"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { X, Send, Bot, Loader2, AlertCircle, ChevronDown } from "lucide-react";
import { chatApi, ChatMessage, ChatResponse } from "@/lib/api/chat";

const MAX_MESSAGES = 50;

interface SourceBadge {
  type: string;
  score: number;
}

function SourceBadge({ type, score }: SourceBadge) {
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

export function IVDriveAIWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unread, setUnread] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Intro message when opened for first time
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      setMessages([
        {
          role: "assistant",
          content:
            "Hello! I'm iVDrive AI. Ask me anything about your vehicles — trips, charging, consumption, range, and more. All answers are based only on your real vehicle data.",
        },
      ]);
    }
  }, [isOpen, messages.length]);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
      setUnread(false);
    }
  }, [messages, isOpen, scrollToBottom]);

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
      const res: ChatResponse = await chatApi.sendMessage(trimmed);
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: res.answer,
        sources: res.sources,
      };
      setMessages((prev) => [...prev, assistantMsg]);
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
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-iv-green shadow-lg hover:bg-iv-green/90 transition-all flex items-center justify-center group"
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
    <div className="fixed bottom-6 right-6 z-50 w-[360px] h-[520px] flex flex-col bg-iv-black border border-iv-border rounded-2xl shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 duration-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-iv-border bg-iv-surface">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-iv-green flex items-center justify-center">
            <Bot className="w-5 h-5 text-iv-black" />
          </div>
          <div>
            <p className="text-sm font-semibold text-iv-text">iVDrive AI</p>
            <p className="text-xs text-iv-muted">Powered by your vehicle data</p>
          </div>
        </div>
        <button
          onClick={() => setIsOpen(false)}
          className="p-1.5 rounded-lg hover:bg-iv-border/50 transition-colors"
          aria-label="Close chat"
        >
          <X className="w-4 h-4 text-iv-muted" />
        </button>
      </div>

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
                {msg.sources.map((s, si) => (
                  <SourceBadge key={si} type={s.type} score={s.score} />
                ))}
              </div>
            )}
          </div>
        ))}
        {isLoading && <TypingIndicator />}
        {error && (
          <div className="flex items-center gap-1.5 text-xs text-iv-danger px-1">
            <AlertCircle className="w-3.5 h-3.5" />
            <span>{error}</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Sources legend */}
      {messages.some((m) => m.sources?.length) && (
        <div className="px-3 py-1.5 border-t border-iv-border/50 flex items-center gap-2">
          <span className="text-xs text-iv-muted">Sources:</span>
          <div className="flex gap-1">
            {["Trip", "Charge", "Stats", "Place"].map((l) => (
              <span key={l} className="text-xs px-1.5 py-0.5 rounded bg-iv-cyan/10 text-iv-cyan">
                {l}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-3 border-t border-iv-border">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your vehicle..."
            rows={1}
            className="flex-1 bg-iv-surface border border-iv-border rounded-xl px-3 py-2 text-sm text-iv-text placeholder-iv-muted resize-none focus:outline-none focus:border-iv-cyan/50 transition-colors"
            style={{ maxHeight: "80px" }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="w-10 h-10 rounded-xl bg-iv-green hover:bg-iv-green/90 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors shrink-0"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 text-iv-black animate-spin" />
            ) : (
              <Send className="w-4 h-4 text-iv-black" />
            )}
          </button>
        </div>
      </form>
    </div>
  );
}