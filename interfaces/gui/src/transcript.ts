import type { ThreadMessageLike } from "@assistant-ui/react";
import type { Incoming, ToolCall } from "@nosis/protocol";
import type { SessionItem } from "./api";

/** A transcript item, plus the streaming state the live turn needs. */
export type TranscriptItem = SessionItem & { streaming?: boolean };

export type Notice = { level: "info" | "error"; text: string };

/** What a protocol message changes about the view. */
export type Applied = {
  items: TranscriptItem[];
  notice?: Notice;
  approval?: { requestId: string; command: string } | null;
  /** Set once the turn ended, so the caller can reload the session. */
  finished?: boolean;
};

type ToolOutcome = { ok: boolean; error?: { type: string; message: string } };

/**
 * Folds a bridge message into the transcript.
 *
 * Mirrors interfaces/tui/src/state.ts: text arrives as deltas and is
 * settled by the matching assistant_message.
 */
export function applyMessage(
  items: TranscriptItem[],
  message: Incoming,
): Applied {
  switch (message.type) {
    case "assistant_delta":
      return { items: appendDelta(items, message.text) };

    case "assistant_message":
      return { items: settleAssistant(items, message.content, message.timestamp_utc) };

    case "context_archived":
      return { items, notice: { level: "info", text: `上下文已压缩（checkpoint ${message.checkpoint_number}）。` } };

    case "tool_batch_started":
      return {
        items: [
          ...items,
          { role: "assistant", content: null, tool_calls: message.tool_calls },
        ],
      };

    case "tool_result":
      return {
        items: [
          ...items,
          {
            role: "tool",
            tool_call_id: message.tool_call_id,
            // The protocol omits tool output; it is filled in from the
            // stored session once the turn completes.
            content: JSON.stringify(
              message.ok
                ? ({ ok: true } satisfies ToolOutcome)
                : ({ ok: false, error: message.error ?? undefined }),
            ),
          },
        ],
      };

    case "approval_request":
      return {
        items,
        approval: {
          requestId: message.request_id,
          command: message.command,
        },
      };

    case "turn_completed":
      return { items, approval: null, finished: true };

    case "turn_cancelled":
      return {
        items: settle(items),
        approval: null,
        finished: true,
        notice: {
          level: "info",
          text: message.persisted ? "已取消。" : "已取消，本轮未保存。",
        },
      };

    case "turn_failed":
    case "fatal":
      return {
        items: settle(items),
        approval: null,
        finished: true,
        notice: {
          level: "error",
          text: `${message.error.type}: ${message.error.message}`,
        },
      };

    // 'ready' and 'tool_call' carry no transcript change: the session id
    // is read from the REST API, and the batch already listed the calls.
    default:
      return { items };
  }
}

function appendDelta(items: TranscriptItem[], text: string): TranscriptItem[] {
  const last = items[items.length - 1];
  if (last?.role === "assistant" && last.streaming) {
    return [
      ...items.slice(0, -1),
      { ...last, content: (last.content ?? "") + text },
    ];
  }
  return [...items, { role: "assistant", content: text, streaming: true }];
}

function settleAssistant(
  items: TranscriptItem[],
  content: string,
  timestamp_utc?: string,
): TranscriptItem[] {
  const last = items[items.length - 1];
  if (last?.role === "assistant" && last.streaming) {
    return [...items.slice(0, -1), { ...last, content, timestamp_utc, streaming: false }];
  }
  return [...items, { role: "assistant", content, timestamp_utc }];
}

/** Closes any open assistant text when a turn ends without settling it. */
function settle(items: TranscriptItem[]): TranscriptItem[] {
  const last = items[items.length - 1];
  if (last?.role !== "assistant" || !last.streaming) return items;
  return [...items.slice(0, -1), { ...last, streaming: false }];
}

/** Groups stored items into the messages assistant-ui renders. */
export function toMessages(items: TranscriptItem[]): ThreadMessageLike[] {
  const results = new Map(
    items
      .filter((item) => item.role === "tool" && item.content)
      .map((item) => [item.tool_call_id, JSON.parse(item.content!)]),
  );
  const messages: ThreadMessageLike[] = [];

  items.forEach((item, index) => {
    if (item.role === "tool") return;
    const content: Exclude<ThreadMessageLike["content"], string> = [
      ...(item.content
        ? [{ type: "text" as const, text: item.content }]
        : []),
      ...(item.tool_calls ?? []).map((call: ToolCall) => ({
        type: "tool-call" as const,
        toolCallId: call.id,
        toolName: call.name,
        args: call.arguments,
        argsText: JSON.stringify(call.arguments),
        result: results.get(call.id),
        isError: results.get(call.id)?.ok === false,
      })),
    ];

    messages.push({
      id: String(index),
      role: item.role,
      content,
      createdAt: item.timestamp_utc
        ? new Date(item.timestamp_utc)
        : undefined,
    });
  });

  return messages;
}
