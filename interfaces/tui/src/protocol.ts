// Wire protocol shared with interfaces/bridge. Keep in sync with
// interfaces/bridge/protocol.py.

export type ToolCall = {
  id: string;
  name: string;
  arguments: unknown;
};

export type ProtocolError = {
  type: string;
  message: string;
};

export type Usage = {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
};

export type Incoming =
  | {
      type: 'ready';
      session_id: string;
      workspace: string;
      model: string;
      resumed: boolean;
      message_count: number;
    }
  | { type: 'assistant_delta'; turn_id: string; text: string; model_call_index: number }
  | {
      type: 'assistant_message';
      turn_id: string;
      content: string;
      timestamp_utc: string;
      model_call_index: number;
    }
  | {
      type: 'tool_batch_started';
      turn_id: string;
      model_call_index: number;
      tool_calls: ToolCall[];
    }
  | {
      type: 'tool_call';
      turn_id: string;
      tool_call: ToolCall;
      tool_index: number;
      tool_count: number;
    }
  | {
      type: 'tool_result';
      turn_id: string;
      tool_call_id: string;
      name: string;
      ok: boolean;
      error: ProtocolError | null;
      tool_index: number;
      tool_count: number;
    }
  | { type: 'approval_request'; turn_id: string; request_id: string; command: string }
  | { type: 'turn_completed'; turn_id: string; usage: Usage | null }
  | { type: 'turn_cancelled'; turn_id: string; persisted: boolean }
  | { type: 'turn_failed'; turn_id: string; error: ProtocolError }
  | { type: 'fatal'; error: ProtocolError };

export type Outgoing =
  | {
      type: 'start';
      workspace: string;
      session_id: string | null;
      provider_config_path: string;
      agent_config_path: string;
    }
  | { type: 'user_turn'; turn_id: string; text: string }
  | { type: 'approval_response'; request_id: string; approved: boolean }
  | { type: 'shutdown' };

/**
 * Splits a byte stream into protocol messages.
 *
 * Chunk boundaries do not respect line boundaries, so a partial line is
 * held back until its newline arrives.
 */
export class MessageDecoder {
  private buffer = '';

  push(chunk: string): Incoming[] {
    this.buffer += chunk;
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() ?? '';

    const messages: Incoming[] = [];
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed === '') continue;
      messages.push(JSON.parse(trimmed) as Incoming);
    }
    return messages;
  }
}

// The runtime stamps outgoing messages with a local timestamp for the
// model; it is noise in the transcript.
const TIMESTAMP_PREFIX = /^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*/;

export function stripTimestamp(content: string): string {
  return content.replace(TIMESTAMP_PREFIX, '');
}

export function formatArguments(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value !== 'object') return String(value);
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) return '';
  return entries
    .map(([key, item]) => `${key}=${typeof item === 'string' ? item : JSON.stringify(item)}`)
    .join(' ');
}
