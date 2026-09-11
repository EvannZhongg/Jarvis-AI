import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AssistantRuntimeProvider, ComposerPrimitive, MessagePrimitive,
  ThreadPrimitive, useAuiState, useExternalStoreRuntime,
  type AppendMessage, type ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { MarkdownTextPrimitive } from "@assistant-ui/react-markdown";
import { ArrowUp, Check, ChevronDown, ChevronRight, LoaderCircle, ShieldCheck, Square, Terminal, X } from "lucide-react";
import { get, sessionUrl, type ModelOption, type Session } from "./api";
import { SessionSocket } from "./session";
import { applyMessage, toMessages, type Notice, type TranscriptItem } from "./transcript";

type Approval = { requestId: string; command: string };

function ToolCard({ toolName, args, result }: ToolCallMessagePartProps) {
  const running = useAuiState((state) => state.thread.isRunning);
  const output = result as { ok: boolean; output?: unknown; error?: { message: string } } | undefined;
  const detail = args.path ?? args.pattern ?? args.command;
  return <details className="tool-card">
    <summary><ChevronRight size={14} className="tool-chevron" /><Terminal size={15} /><span className="tool-name">{toolName}</span><span className="tool-detail">{typeof detail === "string" ? detail : ""}</span>
      {output ? output.ok ? <Check size={15} className="success" /> : <X size={15} className="failure" /> : running ? <LoaderCircle size={15} className="spin" /> : <span className="tool-status">未完成</span>}
    </summary>
    <div className="tool-body"><div className="tool-caption">参数</div><pre>{JSON.stringify(args, null, 2)}</pre>
      {output && (output.ok
        ? output.output !== undefined && <><div className="tool-caption">结果</div><pre>{JSON.stringify(output.output, null, 2)}</pre></>
        : <><div className="tool-caption">执行失败</div><pre>{JSON.stringify(output.error, null, 2)}</pre></>)}
    </div>
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
    <div className="assistant-label"><span className="assistant-avatar"><Terminal size={14} /></span>Nosis</div>
    <div className="assistant-content"><MessagePrimitive.Parts components={{ Text: MarkdownText, tools: { Fallback: ToolCard } }} /></div>
  </MessagePrimitive.Root>;
}

export function Chat({ session, disabled, models, model, onModelChange, onBusyChange, onTurnEnd }: {
  session: Session; disabled: boolean; onBusyChange: (busy: boolean) => void; onTurnEnd: () => void;
  models: ModelOption[]; model: string; onModelChange: (model: string) => void;
}) {
  const [items, setItems] = useState<TranscriptItem[]>(session.items);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const socketRef = useRef<SessionSocket | null>(null);
  const turnCounter = useRef(0);
  const messages = useMemo(() => toMessages(items), [items]);

  // Socket callbacks fire outside React's render, so the transcript and
  // turn state they fold onto are kept in refs.
  const itemsRef = useRef(items);
  const runningRef = useRef(false);

  const showItems = useCallback((next: TranscriptItem[]) => {
    itemsRef.current = next;
    setItems(next);
  }, []);

  // A new provider takes effect on the next connection; the transcript
  // is reloaded from the stored session, so context carries over.
  useEffect(() => {
    socketRef.current?.close();
    socketRef.current = null;
    return () => {
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [model]);

  const endTurn = useCallback(async () => {
    runningRef.current = false;
    setRunning(false);
    onBusyChange(false);
    setApproval(null);
    try {
      // The protocol omits tool output; the stored session has it.
      const stored = await get<Session>(sessionUrl(session.session_id));
      showItems(stored.items);
    } catch {
      // A turn that never persisted keeps the live transcript.
    }
    onTurnEnd();
  }, [session.session_id, onBusyChange, onTurnEnd, showItems]);

  function connect(): SessionSocket {
    const socket = new SessionSocket({
      sessionId: session.session_id,
      provider: model,
      onMessage: (message) => {
        const applied = applyMessage(itemsRef.current, message);
        showItems(applied.items);
        if (applied.notice) setNotice(applied.notice);
        if (applied.approval !== undefined) setApproval(applied.approval);
        if (applied.finished) void endTurn();
      },
      onClose: () => {
        socketRef.current = null;
        if (runningRef.current) {
          setNotice({
            level: "error",
            text: "连接已断开，本轮对话未完成。已执行的工具操作不会撤销。",
          });
          void endTurn();
        }
      },
      onError: () => setNotice({ level: "error", text: "无法连接 Nosis。" }),
    });
    socketRef.current = socket;
    return socket;
  }

  async function onNew(message: AppendMessage) {
    const text = message.content.filter((part) => part.type === "text").map((part) => part.text).join("\n").trim();
    if (!text || runningRef.current) return;

    showItems([...itemsRef.current, { role: "user", content: text }]);
    runningRef.current = true;
    setRunning(true);
    onBusyChange(true);
    setNotice(null);

    turnCounter.current += 1;
    const socket = socketRef.current ?? connect();
    socket.send({ type: "user_turn", turn_id: `turn-${turnCounter.current}`, text });
  }

  function respond(approved: boolean) {
    if (!approval) return;
    socketRef.current?.send({ type: "approval_response", request_id: approval.requestId, approved });
    setApproval(null);
  }

  const runtime = useExternalStoreRuntime({ messages, convertMessage: (message) => message, isRunning: running, isDisabled: disabled, onNew });

  return <AssistantRuntimeProvider runtime={runtime}>
    <ThreadPrimitive.Root className="thread">
      <ThreadPrimitive.Viewport className="thread-viewport">
        <ThreadPrimitive.Empty>
          <div className="welcome"><div className="welcome-symbol"><Terminal size={26} /></div><div className="eyebrow">YOUR PERSONAL AGENT</div><h1>一起，把想法变成现实。</h1><p>聊聊你的项目，或者交给 Nosis 一个任务。</p></div>
        </ThreadPrimitive.Empty>
        <div className="messages"><ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} /></div>
      </ThreadPrimitive.Viewport>
      <div className="composer-area">
        {approval && <div className="approval-card" role="region" aria-label="Shell 执行确认"><div className="approval-title"><ShieldCheck size={17} /> 允许执行这条命令？</div><pre>{approval.command}</pre><div className="approval-actions"><button onClick={() => respond(false)}>拒绝</button><button className="approve-button" onClick={() => respond(true)}>允许执行</button></div></div>}
        {notice && <div className={notice.level === "error" ? "error-banner" : "notice-banner"} role="alert">{notice.text}</div>}
        {running && <div className="activity" role="status"><LoaderCircle size={13} className="spin" />{approval ? "等待你的确认" : "Nosis 正在处理…"}
          {!approval && <button className="stop-button" aria-label="停止执行" onClick={() => socketRef.current?.send({ type: "cancel" })}><Square size={11} /> 停止</button>}
        </div>}
        <ComposerPrimitive.Root className="composer"><ComposerPrimitive.Input placeholder="Ask Nosis…" aria-label="消息" rows={2} autoFocus /><div className="composer-bottom">
          <label className="model-selector" title={models.find((option) => option.id === model)?.model}>
            <select aria-label="选择模型" value={model} disabled={disabled || running} onChange={(event) => onModelChange(event.target.value)}>
              {models.map((option) => <option key={option.id} value={option.id}>{option.model}</option>)}
            </select><ChevronDown size={12} />
          </label>
          <span className="composer-hint">Enter 发送 · Shift + Enter 换行</span><ComposerPrimitive.Send className="send-button" aria-label="发送消息"><ArrowUp size={19} /></ComposerPrimitive.Send></div></ComposerPrimitive.Root>
        <div className="composer-footer">Nosis · 你的项目搭档</div>
      </div>
    </ThreadPrimitive.Root>
  </AssistantRuntimeProvider>;
}
