import type { ToolCall } from "@nosis/protocol";

export type SessionItem = {
  role: "user" | "assistant" | "tool";
  content: string | null;
  timestamp_utc?: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
};

export type Session = { session_id: string; items: SessionItem[] };
export type SessionSummary = { session_id: string; title: string };
export type ModelOption = { id: string; model: string };
export type ModelOptions = { default: string; models: ModelOption[] };
export type Directory = {
  root: string;
  path: string;
  entries: { name: string; type: "directory" | "file" | "symlink" | "other" }[];
};

export async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail ?? `请求失败 (${response.status})`);
  }
  return response.json();
}

export function sessionUrl(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}`;
}
