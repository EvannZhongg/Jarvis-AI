import { useCallback, useEffect, useState } from "react";
import { ChevronRight, MessageSquare, Plus } from "lucide-react";
import { Chat } from "./Chat";
import { Workspace } from "./Workspace";
import type { Usage } from "@nosis/protocol";
import { get, sessionUrl, type ModelOption, type ModelOptions, type Session, type SessionSummary } from "./api";

export function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [session, setSession] = useState<Session>(() => ({ session_id: crypto.randomUUID(), items: [] }));
  const [busy, setBusy] = useState(false);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [workspaceVersion, setWorkspaceVersion] = useState(0);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState("");

  const refreshSessions = useCallback(async () => {
    try {
      setSessions(await get<SessionSummary[]>("/api/sessions"));
    } catch (error) {
      setError(String(error));
    }
  }, []);

  useEffect(() => { void refreshSessions(); }, [refreshSessions]);
  // Usage belongs to the shown conversation, so switching sessions clears it.
  useEffect(() => { setUsage(null); }, [session.session_id]);
  useEffect(() => {
    get<ModelOptions>("/api/models").then((options) => {
      setModels(options.models);
      setModel(options.default);
    }).catch((error) => setError(String(error)));
  }, []);

  async function selectSession(id: string) {
    setLoading(true);
    setError("");
    try {
      setSession(await get<Session>(sessionUrl(id)));
    } catch (error) {
      setError(String(error));
    } finally {
      setLoading(false);
    }
  }

  const selectedTitle = sessions.find((item) => item.session_id === session.session_id)?.title ?? "New chat";

  return (
    <div className="app-shell">
      <aside className="sessions-panel" aria-label="Sessions">
        <div className="brand"><span>Nosis<span className="brand-dot">.</span></span></div>
        <button className="new-chat" disabled={busy || loading} onClick={() => {
          setSession({ session_id: crypto.randomUUID(), items: [] });
          setError("");
        }}><Plus size={17} /> New chat</button>
        <div className="section-label">Sessions <span>{sessions.length}</span></div>
        <nav className="session-list">
          {sessions.map((item) => (
            <button key={item.session_id} className={`session-button ${item.session_id === session.session_id ? "selected" : ""}`}
              title={item.title} disabled={busy || loading} onClick={() => void selectSession(item.session_id)}>
              <MessageSquare size={15} /><span>{item.title}</span>
            </button>
          ))}
          {sessions.length === 0 && <p className="session-empty">从一段对话开始。</p>}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" /> Personal workspace</div>
      </aside>

      <main className="chat-panel">
        <header className="chat-header"><div className="breadcrumb">Chat <ChevronRight size={14} /><span>{selectedTitle}</span></div><span className="status-label"><span className={`status-dot ${busy ? "working" : ""}`} />{busy ? "Working" : "Ready"}{usage?.total_tokens ? ` · ${usage.total_tokens} tokens` : ""}</span></header>
        {error && <div className="error-banner" role="alert">{error}</div>}
        <Chat key={session.session_id} session={session} disabled={loading || !model}
          models={models} model={model} onModelChange={setModel} onBusyChange={setBusy} onUsageChange={setUsage} onTurnEnd={() => {
          void refreshSessions();
          setWorkspaceVersion((value) => value + 1);
        }} />
      </main>
      <Workspace version={workspaceVersion} />
    </div>
  );
}
