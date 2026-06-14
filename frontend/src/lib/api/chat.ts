import { apiFetch, API_BASE, getCookie } from "./core";

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (data: { session_id?: string; sources?: ChatResponse["sources"] }) => void;
  onStatus?: () => void;
  onError?: (detail: string) => void;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { type: string; id: string; score: number }[];
  created_at?: string;
}

export interface ChatResponse {
  answer: string;
  sources: { type: string; id: string; score: number }[];
  session_id?: string;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_at: string | null;
}

// In-memory current session — never persisted to localStorage
let _currentSessionId: string | null = null;

export function getCurrentSessionId(): string | null {
  return _currentSessionId;
}

function setCurrentSessionId(sid: string | null): void {
  _currentSessionId = sid;
}

// ── Session management ────────────────────────────────────────────────────────

export const chatApi = {
  /** List user's chat sessions (newest first) */
  async listSessions(): Promise<SessionInfo[]> {
    const res = await apiFetch("/api/v1/chat/sessions");
    return res.json();
  },

  /** Load all messages for a given session */
  async getSessionMessages(sessionId: string): Promise<{ id: string; messages: ChatMessage[] }> {
    const res = await apiFetch(`/api/v1/chat/sessions/${sessionId}`);
    return res.json();
  },

  /** Delete a specific session */
  async deleteSession(sessionId: string): Promise<void> {
    await apiFetch(`/api/v1/chat/sessions/${sessionId}`, { method: "DELETE" });
  },

  /** Delete all sessions */
  async deleteAllSessions(): Promise<{ deleted_count: number }> {
    const res = await apiFetch("/api/v1/chat/sessions", { method: "DELETE" });
    return res.json();
  },

  /** Send a message — pass sessionId to continue conversation, none to start new */
  async sendMessage(
    message: string,
    sessionId?: string | null,
    vehicleId?: string,
    provider: "minimax" | "gemini" | "openai" = "minimax"
  ): Promise<ChatResponse> {
    const body: Record<string, string> = { message };
    if (sessionId) body.session_id = sessionId;
    if (vehicleId) body.vehicle_id = vehicleId;
    body.provider = provider;

    const res = await apiFetch("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();

    // Update in-memory current session
    if (data.session_id) {
      setCurrentSessionId(data.session_id);
    }

    return data;
  },

  /**
   * Streaming variant — consumes Server-Sent Events from /chat/stream.
   * Keeps the connection alive via `status` heartbeats during the slow agentic
   * phase (avoids the proxy timeout), then delivers the answer incrementally.
   */
  async sendMessageStream(
    message: string,
    sessionId: string | null | undefined,
    handlers: StreamHandlers,
    vehicleId?: string,
    provider: "minimax" | "gemini" | "openai" = "minimax",
  ): Promise<void> {
    const body: Record<string, string> = { message, provider };
    if (sessionId) body.session_id = sessionId;
    if (vehicleId) body.vehicle_id = vehicleId;

    const csrf = getCookie("csrf_token");
    const res = await fetch(`${API_BASE}/api/v1/chat/stream`, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!res.ok || !res.body) {
      throw new Error(`Chat request failed (${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line.
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        const payload = dataLine.slice(5).trim();
        if (!payload) continue;
        let evt: { type: string; text?: string; session_id?: string; sources?: ChatResponse["sources"]; detail?: string };
        try {
          evt = JSON.parse(payload);
        } catch {
          continue;
        }
        if (evt.type === "delta" && evt.text) {
          handlers.onDelta(evt.text);
        } else if (evt.type === "done") {
          if (evt.session_id) setCurrentSessionId(evt.session_id);
          handlers.onDone({ session_id: evt.session_id, sources: evt.sources });
        } else if (evt.type === "status") {
          handlers.onStatus?.();
        } else if (evt.type === "error") {
          handlers.onError?.(evt.detail || "Something went wrong.");
        }
      }
    }
  },
};