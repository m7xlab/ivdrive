import { apiFetch } from "./core";

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
};