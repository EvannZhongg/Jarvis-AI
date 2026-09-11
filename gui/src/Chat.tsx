import { useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider, ComposerPrimitive, MessagePrimitive,
  ThreadPrimitive, useAuiState, useExternalStoreRuntime,
  type AppendMessage, type ThreadMessageLike, type ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { ArrowUp, Check, ChevronDown, ChevronRight, LoaderCircle, ShieldCheck, Terminal, X } from "lucide-react";
import { type ModelOption, type Session, type SessionItem, type ToolCall } from "./api";

type Approval = { id: string; command: string };
type RunEvent =
  | { type: "AssistantMessageEvent"; content: string; timestamp_utc: string }
  | { type: "ToolBatchStartedEvent"; tool_calls: ToolCall[] }
  | { type: "ToolCallEvent"; tool_call: ToolCall }
  | { type: "ToolResultEvent"; tool_result: { tool_call_id: string; output: unknown; error: unknown } }
  | { type: "approval_required"; id: string; command: string }
  | { type: "done"; session: Session }
  | { type: "error"; message: string };

function toMessages(items: SessionItem[]): ThreadMessageLike[] {
  const results = new Map(items.filter((item) => item.role === "tool").map((item) => [item.tool_call_id, JSON.parse(item.content!)]));
  const messages: ThreadMessageLike[] = [];
  items.forEach((item, index) => {
    if (item.role === "tool") return;
    const content: Exclude<ThreadMessageLike["content"], string> = [
      ...(item.content ? [{ type: "text" as const, text: item.content.replace(/^\[\d{4}-\d{2}-\d{2}T[^\]]+\]\s*/, "") }] : []),
      ...(item.tool_calls ?? []).map((call) => ({
        type: "tool-call" as const, toolCallId: call.id, toolName: call.name,
        args: call.arguments, argsText: JSON.stringify(call.arguments),
        result: results.get(call.id), isError: results.get(call.id)?.ok === false,
      })),
    ];
    const previous = messages.at(-1);
    if (item.role === "assistant" && previous?.role === "assistant") {
      messages[messages.length - 1] = { ...previous, content: [...previous.content as typeof content, ...content] };
    } else {
      messages.push({ id: String(index), role: item.role, content, createdAt: item.timestamp_utc ? new Date(item.timestamp_utc) : undefined });
    }
  });
  return messages;
}

function ToolCard({ toolName, args, result }: ToolCallMessagePartProps) {
  const running = useAuiState((state) => state.thread.isRunning);
  const output = result as { ok: boolean; output?: unknown; error?: { message: string } } | undefined;
  const detail = args.path ?? args.pattern ?? args.command;
  return <details className="tool-card">
    <summary><ChevronRight size={14} className="tool-chevron" /><Terminal size={15} /><span className="tool-name">{toolName}</span><span className="tool-detail">{typeof detail === "string" ? detail : ""}</span>
      {output ? output.ok ? <Check size={15} className="success" /> : <X size={15} className="failure" /> : running ? <LoaderCircle size={15} className="spin" /> : <span className="tool-status">未完成</span>}
    </summary>
    <div className="tool-body"><div className="tool-caption">参数</div><pre>{JSON.stringify(args, null, 2)}</pre>{output && <><div className="tool-caption">{output.ok ? "结果" : "执行失败"}</div><pre>{JSON.stringify(output.ok ? output.output : output.error, null, 2)}</pre></>}</div>
  </details>;
}

function UserMessage() {
  return <MessagePrimitive.Root className="user-message"><MessagePrimitive.Parts /></MessagePrimitive.Root>;
}

function MarkdownText() {
  return <MarkdownTextPrimitive />;
}

function AssistantMessage() {
  return <MessagePrimitive.Root className="assistant-message">
    <div className="assistant-label"><span className="assistant-avatar"><Terminal size={14} /></span>Jarvis</div>
    <div className="assistant-content"><MessagePrimitive.Parts components={{ Text: MarkdownText, tools: { Fallback: ToolCard } }} /></div>
  </MessagePrimitive.Root>;
}

export function Chat({ session, disabled, models, model, onModelChange, onBusyChange, onDone }: {
  session: Session; disabled: boolean; onBusyChange: (busy: boolean) => void; onDone: () => void;
  models: ModelOption[]; model: string; onModelChange: (model: string) => void;
}) {
  const [items, setItems] = useState(session.items);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [approval, setApproval] = useState<Approval | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const messages = useMemo(() => toMessages(items), [items]);

  useEffect(() => () => { socketRef.current?.close(); }, []);

  async function onNew(message: AppendMessage) {
    const input = message.content.filter((part) => part.type === "text").map((part) => part.text).join("\n").trim();
    if (!input || socketRef.current) return;
    setItems((previous) => [...previous, { role: "user", content: input }]);
    setRunning(true);
    onBusyChange(true);
    setError("");
    let finished = false;
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/sessions/${encodeURIComponent(session.session_id)}/run`);
    socketRef.current = socket;
    socket.onopen = () => socket.send(JSON.stringify({ message: input, model }));
    socket.onmessage = ({ data }) => {
      const event: RunEvent = JSON.parse(data);
      switch (event.type) {
        case "AssistantMessageEvent":
          setItems((previous) => [...previous, { role: "assistant", content: event.content, timestamp_utc: event.timestamp_utc }]);
          break;
        case "ToolBatchStartedEvent":
          setItems((previous) => [...previous, { role: "assistant", content: null, tool_calls: event.tool_calls }]);
          break;
        case "ToolResultEvent": {
          const result = event.tool_result;
          setItems((previous) => [...previous, { role: "tool", tool_call_id: result.tool_call_id, content: JSON.stringify(result.error ? { ok: false, error: result.error } : { ok: true, output: result.output }) }]);
          break;
        }
        case "approval_required": setApproval(event); break;
        case "done":
          finished = true;
          setItems(event.session.items);
          onDone();
          break;
        case "error":
          finished = true;
          setError(event.message);
          break;
      }
    };
    socket.onclose = () => {
      socketRef.current = null;
      setRunning(false);
      onBusyChange(false);
      setApproval(null);
      if (!finished) setError("连接已断开，本轮对话未完成。已完成的工具操作可能已生效。");
    };
    socket.onerror = () => setError("无法连接 Jarvis。");
  }

  function respond(approved: boolean) {
    if (approval && socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "approval", id: approval.id, approved }));
      setApproval(null);
    }
  }

  const runtime = useExternalStoreRuntime({ messages, convertMessage: (message) => message, isRunning: running, isDisabled: disabled, onNew });

  return <AssistantRuntimeProvider runtime={runtime}>
    <ThreadPrimitive.Root className="thread">
      <ThreadPrimitive.Viewport className="thread-viewport">
        <ThreadPrimitive.Empty>
          <div className="welcome"><div className="welcome-symbol"><Terminal size={26} /></div><div className="eyebrow">YOUR PERSONAL AGENT</div><h1>一起，把想法变成现实。</h1><p>聊聊你的项目，或者交给 Jarvis 一个任务。</p></div>
        </ThreadPrimitive.Empty>
        <div className="messages"><ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} /></div>
      </ThreadPrimitive.Viewport>
      <div className="composer-area">
        {approval && <div className="approval-card" role="region" aria-label="Shell 执行确认"><div className="approval-title"><ShieldCheck size={17} /> 允许执行这条命令？</div><pre>{approval.command}</pre><div className="approval-actions"><button onClick={() => respond(false)}>拒绝</button><button className="approve-button" onClick={() => respond(true)}>允许执行</button></div></div>}
        {error && <div className="error-banner" role="alert">{error}</div>}
        {running && <div className="activity" role="status"><LoaderCircle size={13} className="spin" />{approval ? "等待你的确认" : "Jarvis 正在处理…"}</div>}
        <ComposerPrimitive.Root className="composer"><ComposerPrimitive.Input placeholder="Ask Jarvis…" aria-label="消息" rows={2} autoFocus /><div className="composer-bottom">
          <label className="model-selector" title={models.find((option) => option.id === model)?.model}>
            <select aria-label="选择模型" value={model} disabled={disabled || running} onChange={(event) => onModelChange(event.target.value)}>
              {models.map((option) => <option key={option.id} value={option.id}>{option.model}</option>)}
            </select><ChevronDown size={12} />
          </label>
          <span className="composer-hint">Enter 发送 · Shift + Enter 换行</span><ComposerPrimitive.Send className="send-button" aria-label="发送消息"><ArrowUp size={19} /></ComposerPrimitive.Send></div></ComposerPrimitive.Root>
        <div className="composer-footer">Jarvis · 你的项目搭档</div>
      </div>
    </ThreadPrimitive.Root>
  </AssistantRuntimeProvider>;
}
