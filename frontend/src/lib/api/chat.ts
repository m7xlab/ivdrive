import { apiFetch } from "./core";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { type: string; id: string; score: number }[];
}

export interface ChatResponse {
  answer: string;
  sources: { type: string; id: string; score: number }[];
  session_id?: string;
}

const SESSION_KEY = "ivdrive_chat_session_id";

export function getChatSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(SESSION_KEY);
}

export function setChatSessionId(sessionId: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SESSION_KEY, sessionId);
}

export const chatApi = {
  async sendMessage(
    message: string,
    vehicleId?: string,
    provider: "minimax" | "gemini" | "openai" = "minimax"
  ): Promise<ChatResponse> {
    const sessionId = getChatSessionId();
    const body: Record<string, string> = { message };
    if (vehicleId) body.vehicle_id = vehicleId;
    if (sessionId) body.session_id = sessionId;
    body.provider = provider;
    const res = await apiFetch("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    });
    const data = await res.json();
    // Persist session_id for next request
    if (data.session_id) {
      setChatSessionId(data.session_id);
    }
    return data;
  },
};
