import type { Incoming, ProtocolError, Usage } from '@nosis/protocol';

export type Status =
  | 'starting'
  | 'idle'
  | 'streaming'
  | 'running'
  | 'awaiting_approval'
  | 'cancelling'
  | 'fatal';

export type Entry =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'assistant'; id: string; text: string; settled: boolean; timestamp_utc?: string }
  | {
      kind: 'tool';
      id: string;
      name: string;
      args: unknown;
      index: number;
      count: number;
      state: 'running' | 'ok' | 'error';
      error?: ProtocolError;
    }
  | { kind: 'notice'; id: string; level: 'info' | 'error'; text: string };

export type ApprovalChoice = 'deny' | 'allow';

export type State = {
  status: Status;
  sessionId: string | null;
  workspace: string;
  model: string;
  entries: Entry[];
  approval: { requestId: string; command: string; choice: ApprovalChoice } | null;
  turnId: string | null;
  usage: Usage | null;
};

export type Action =
  | { type: 'message'; message: Incoming }
  | { type: 'submit'; turnId: string; text: string }
  | { type: 'approval_choice'; choice: ApprovalChoice }
  | { type: 'approval_resolved' }
  | { type: 'cancelling' }
  | { type: 'exited'; code: number | null };

export const initialState: State = {
  status: 'starting',
  sessionId: null,
  workspace: '',
  model: '',
  entries: [],
  approval: null,
  turnId: null,
  usage: null,
};

let entryCounter = 0;
function nextId(prefix: string): string {
  entryCounter += 1;
  return `${prefix}-${entryCounter}`;
}

/** Appends to the open assistant entry, creating it on the first delta. */
function appendDelta(entries: Entry[], text: string): Entry[] {
  const last = entries[entries.length - 1];
  if (last && last.kind === 'assistant' && !last.settled) {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...entries, { kind: 'assistant', id: nextId('assistant'), text, settled: false }];
}

function settleAssistant(entries: Entry[], content: string, timestamp_utc?: string): Entry[] {
  const last = entries[entries.length - 1];
  if (last && last.kind === 'assistant' && !last.settled) {
    return [...entries.slice(0, -1), { ...last, text: content, timestamp_utc, settled: true }];
  }
  return [...entries, { kind: 'assistant', id: nextId('assistant'), text: content, timestamp_utc, settled: true }];
}

function resolveTool(
  entries: Entry[],
  toolCallId: string,
  state: 'ok' | 'error',
  error: ProtocolError | null,
): Entry[] {
  return entries.map((entry) =>
    entry.kind === 'tool' && entry.id === toolCallId
      ? { ...entry, state, ...(error ? { error } : {}) }
      : entry,
  );
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'submit':
      return {
        ...state,
        status: 'streaming',
        turnId: action.turnId,
        usage: null,
        entries: [
          ...state.entries,
          { kind: 'user', id: nextId('user'), text: action.text },
        ],
      };

    case 'approval_choice':
      return state.approval === null
        ? state
        : { ...state, approval: { ...state.approval, choice: action.choice } };

    case 'approval_resolved':
      // The runtime resumes the turn once the answer is sent.
      return { ...state, status: 'running', approval: null };

    case 'cancelling':
      return state.status === 'idle' || state.status === 'fatal'
        ? state
        : { ...state, status: 'cancelling', approval: null };

    case 'exited':
      return {
        ...state,
        status: 'fatal',
        entries: [
          ...state.entries,
          {
            kind: 'notice',
            id: nextId('notice'),
            level: 'error',
            text: `Agent process exited (code ${action.code ?? 'unknown'}).`,
          },
        ],
      };

    case 'message':
      return applyMessage(state, action.message);
  }
}

function applyMessage(state: State, message: Incoming): State {
  switch (message.type) {
    case 'ready':
      return {
        ...state,
        status: 'idle',
        sessionId: message.session_id,
        workspace: message.workspace,
        model: message.model,
        entries: message.resumed
          ? [
              ...state.entries,
              {
                kind: 'notice',
                id: nextId('notice'),
                level: 'info',
                text: `Resumed session with ${message.message_count} message(s).`,
              },
            ]
          : state.entries,
      };

    case 'assistant_delta':
      return {
        ...state,
        status: state.status === 'cancelling' ? state.status : 'streaming',
        entries: appendDelta(state.entries, message.text),
      };

    case 'assistant_message':
      return { ...state, entries: settleAssistant(state.entries, message.content, message.timestamp_utc) };

    case 'tool_batch_started':
      return { ...state, status: state.status === 'cancelling' ? state.status : 'running' };

    case 'tool_call':
      return {
        ...state,
        status: state.status === 'cancelling' ? state.status : 'running',
        entries: [
          ...state.entries,
          {
            kind: 'tool',
            id: message.tool_call.id,
            name: message.tool_call.name,
            args: message.tool_call.arguments,
            index: message.tool_index,
            count: message.tool_count,
            state: 'running',
          },
        ],
      };

    case 'context_archived':
      return {
        ...state,
        entries: [...state.entries, { kind: 'notice', id: nextId('notice'), level: 'info', text: `Context compressed (checkpoint ${message.checkpoint_number}).` }],
      };

    case 'tool_result':
      return {
        ...state,
        entries: resolveTool(
          state.entries,
          message.tool_call_id,
          message.ok ? 'ok' : 'error',
          message.error,
        ),
      };

    case 'approval_request':
      return {
        ...state,
        status: 'awaiting_approval',
        approval: {
          requestId: message.request_id,
          command: message.command,
          choice: 'allow',
        },
      };

    case 'turn_completed':
      return { ...state, status: 'idle', turnId: null, approval: null, usage: message.usage };

    case 'turn_cancelled':
      return {
        ...state,
        status: 'idle',
        turnId: null,
        approval: null,
        entries: [
          ...state.entries,
          {
            kind: 'notice',
            id: nextId('notice'),
            level: 'info',
            text: message.persisted ? 'Cancelled.' : 'Cancelled (not saved).',
          },
        ],
      };

    case 'turn_failed':
      return {
        ...state,
        status: 'idle',
        turnId: null,
        approval: null,
        entries: [
          ...state.entries,
          {
            kind: 'notice',
            id: nextId('notice'),
            level: 'error',
            text: `${message.error.type}: ${message.error.message}`,
          },
        ],
      };

    case 'fatal':
      return {
        ...state,
        status: 'fatal',
        entries: [
          ...state.entries,
          {
            kind: 'notice',
            id: nextId('notice'),
            level: 'error',
            text: `${message.error.type}: ${message.error.message}`,
          },
        ],
      };
  }
}
