import { describe, expect, it } from "vitest";
import type { Incoming } from "@jarvis/protocol";
import { applyMessage, toMessages, type TranscriptItem } from "../src/transcript";

const TOOL_CALL = { id: "call-1", name: "shell", arguments: { command: "ls" } };

/** Folds a sequence of bridge messages, as the socket callback does. */
function fold(messages: Incoming[], initial: TranscriptItem[] = []) {
  return messages.reduce(
    (state, message) => {
      const applied = applyMessage(state.items, message);
      return {
        items: applied.items,
        notice: applied.notice ?? state.notice,
        approval:
          applied.approval !== undefined ? applied.approval : state.approval,
        finished: applied.finished ?? state.finished,
      };
    },
    {
      items: initial,
      notice: undefined,
      approval: null,
      finished: false,
    } as ReturnType<typeof applyMessage> & { approval: unknown },
  );
}

describe("applyMessage", () => {
  it("streams deltas into a single assistant item", () => {
    const { items } = fold([
      { type: "assistant_delta", turn_id: "t1", text: "he", model_call_index: 1 },
      { type: "assistant_delta", turn_id: "t1", text: "llo", model_call_index: 1 },
    ]);

    expect(items).toEqual([
      { role: "assistant", content: "hello", streaming: true },
    ]);
  });

  it("settles the streamed item and strips the runtime timestamp", () => {
    const { items } = fold([
      { type: "assistant_delta", turn_id: "t1", text: "hi", model_call_index: 1 },
      {
        type: "assistant_message",
        turn_id: "t1",
        content: "[2026-09-09T08:00:00+08:00] hi there",
        timestamp_utc: "2026-09-09T00:00:00.000000Z",
        model_call_index: 1,
      },
    ]);

    expect(items).toEqual([
      { role: "assistant", content: "hi there", streaming: false },
    ]);
  });

  it("records a tool batch and its outcome", () => {
    const { items } = fold([
      {
        type: "tool_batch_started",
        turn_id: "t1",
        model_call_index: 1,
        tool_calls: [TOOL_CALL],
      },
      {
        type: "tool_result",
        turn_id: "t1",
        tool_call_id: "call-1",
        name: "shell",
        ok: true,
        error: null,
        tool_index: 1,
        tool_count: 1,
      },
    ]);

    expect(items[0]).toEqual({
      role: "assistant",
      content: null,
      tool_calls: [TOOL_CALL],
    });
    // The protocol carries no output, only the status.
    expect(JSON.parse(items[1].content!)).toEqual({ ok: true });
  });

  it("keeps the error from a failed tool", () => {
    const { items } = fold([
      {
        type: "tool_result",
        turn_id: "t1",
        tool_call_id: "call-1",
        name: "shell",
        ok: false,
        error: { type: "PermissionError", message: "denied" },
        tool_index: 1,
        tool_count: 1,
      },
    ]);

    expect(JSON.parse(items[0].content!)).toEqual({
      ok: false,
      error: { type: "PermissionError", message: "denied" },
    });
  });

  it("raises and then clears an approval request", () => {
    const requested = fold([
      {
        type: "approval_request",
        turn_id: "t1",
        request_id: "t1:1",
        command: "rm -rf build",
      },
    ]);
    expect(requested.approval).toEqual({
      requestId: "t1:1",
      command: "rm -rf build",
    });

    const completed = applyMessage(requested.items, {
      type: "turn_completed",
      turn_id: "t1",
      usage: null,
    });
    expect(completed.approval).toBeNull();
    expect(completed.finished).toBe(true);
  });

  it("settles open text and reports a cancelled turn", () => {
    const { items, notice, finished } = fold([
      { type: "assistant_delta", turn_id: "t1", text: "partial", model_call_index: 1 },
      { type: "turn_cancelled", turn_id: "t1", persisted: false },
    ]);

    expect(items).toEqual([
      { role: "assistant", content: "partial", streaming: false },
    ]);
    expect(notice).toEqual({ level: "info", text: "已取消，本轮未保存。" });
    expect(finished).toBe(true);
  });

  it("reports a failed turn as an error notice", () => {
    const { notice, finished } = fold([
      {
        type: "turn_failed",
        turn_id: "t1",
        error: { type: "ContextWindowExceededError", message: "too long" },
      },
    ]);

    expect(notice).toEqual({
      level: "error",
      text: "ContextWindowExceededError: too long",
    });
    expect(finished).toBe(true);
  });

  it("ignores messages that carry no transcript change", () => {
    const items: TranscriptItem[] = [{ role: "user", content: "hi" }];
    for (const message of [
      {
        type: "ready" as const,
        session_id: "s1",
        workspace: "/tmp",
        model: "m",
        resumed: false,
        message_count: 0,
      },
      {
        type: "tool_call" as const,
        turn_id: "t1",
        tool_call: TOOL_CALL,
        tool_index: 1,
        tool_count: 1,
      },
    ]) {
      expect(applyMessage(items, message).items).toBe(items);
    }
  });
});

describe("toMessages", () => {
  /** Reads the parts of a message; toMessages never produces plain text. */
  function parts(message: { content: unknown }) {
    return message.content as {
      type: string;
      isError?: boolean;
      result?: unknown;
    }[];
  }

  it("merges consecutive assistant items into one message", () => {
    const messages = toMessages([
      { role: "user", content: "run it" },
      { role: "assistant", content: "Working on it.", tool_calls: [TOOL_CALL] },
      { role: "tool", tool_call_id: "call-1", content: '{"ok":true}' },
      { role: "assistant", content: "Done." },
    ]);

    expect(messages).toHaveLength(2);
    expect(messages[0].role).toBe("user");
    expect(messages[1].role).toBe("assistant");
    // Text, the tool call, and the follow-up text share one message.
    expect(messages[1].content).toHaveLength(3);
  });

  it("attaches the stored result to its tool call", () => {
    const messages = toMessages([
      { role: "assistant", content: null, tool_calls: [TOOL_CALL] },
      {
        role: "tool",
        tool_call_id: "call-1",
        content: '{"ok":false,"error":{"message":"denied"}}',
      },
    ]);

    const part = parts(messages[0])[0];
    expect(part.type).toBe("tool-call");
    expect(part.isError).toBe(true);
  });

  it("strips the runtime timestamp from stored messages", () => {
    const messages = toMessages([
      { role: "user", content: "[2026-09-09T08:00:00+08:00] hello" },
    ]);

    expect(messages[0].content).toEqual([{ type: "text", text: "hello" }]);
  });

  it("skips a tool item whose output was never stored", () => {
    const messages = toMessages([
      { role: "assistant", content: null, tool_calls: [TOOL_CALL] },
      { role: "tool", tool_call_id: "call-1", content: null },
    ]);

    const part = parts(messages[0])[0];
    expect(part.result).toBeUndefined();
  });
});
