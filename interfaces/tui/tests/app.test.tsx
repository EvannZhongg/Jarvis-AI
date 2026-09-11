import { beforeEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { render } from 'ink-testing-library';
import type { Incoming } from '../src/protocol.js';

const sent: any[] = [];
let emit: (message: Incoming) => void = () => {};

vi.mock('../src/bridge.js', () => ({
  BridgeClient: class {
    constructor(options: any) {
      emit = options.onMessage;
      setTimeout(
        () =>
          options.onMessage({
            type: 'ready',
            session_id: 'sess-1234',
            workspace: '/w',
            model: 'test/model',
            resumed: false,
            message_count: 0,
          }),
        10,
      );
    }
    send(message: any) {
      sent.push(message);
    }
    cancel() {
      sent.push({ type: '__cancel' });
    }
    shutdown() {}
    diagnostics() {
      return '';
    }
  },
}));

const { App } = await import('../src/app.js');

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function renderApp() {
  return render(
    <App
      python="python3"
      workspace="/w"
      sessionId={null}
      providerConfigPath="/p"
      agentConfigPath="/a"
    />,
  );
}

describe('App', () => {
  beforeEach(() => {
    sent.length = 0;
  });

  it('starts the runtime with the workspace and config paths', async () => {
    renderApp();
    await wait(80);
    expect(sent[0]).toMatchObject({
      type: 'start',
      workspace: '/w',
      session_id: null,
      provider_config_path: '/p',
      agent_config_path: '/a',
    });
  });

  it('submits a typed turn once the runtime is idle', async () => {
    const { stdin } = renderApp();
    await wait(80);
    stdin.write('hello there');
    await wait(50);
    stdin.write('\r');
    await wait(80);
    expect(sent.find((m) => m.type === 'user_turn')).toMatchObject({
      text: 'hello there',
    });
  });

  it('queues a turn typed while the agent is busy', async () => {
    const { stdin } = renderApp();
    await wait(80);
    stdin.write('first');
    await wait(40);
    stdin.write('\r');
    await wait(60);

    stdin.write('second');
    await wait(40);
    stdin.write('\r');
    await wait(60);
    const turns = () => sent.filter((m) => m.type === 'user_turn');
    expect(turns()).toHaveLength(1);

    // Completing the first turn releases the queued one.
    emit({ type: 'turn_completed', turn_id: turns()[0].turn_id, usage: null });
    await wait(80);
    expect(turns()).toHaveLength(2);
    expect(turns()[1].text).toBe('second');
  });

  it('defaults to allow and confirms with enter', async () => {
    const { stdin, lastFrame } = renderApp();
    await wait(80);
    emit({
      type: 'approval_request',
      turn_id: 't1',
      request_id: 't1:1',
      command: 'ls -la',
    });
    await wait(60);
    expect(lastFrame()).toContain('❯ Allow');

    stdin.write('\r');
    await wait(60);
    expect(sent.find((m) => m.type === 'approval_response')).toMatchObject({
      request_id: 't1:1',
      approved: true,
    });
  });

  it('denies after moving the selection with an arrow key', async () => {
    const { stdin, lastFrame } = renderApp();
    await wait(80);
    emit({
      type: 'approval_request',
      turn_id: 't1',
      request_id: 't1:1',
      command: 'rm -rf /',
    });
    await wait(60);

    stdin.write('[C'); // right arrow
    await wait(60);
    expect(lastFrame()).toContain('❯ Deny');

    stdin.write('\r');
    await wait(60);
    expect(sent.find((m) => m.type === 'approval_response')).toMatchObject({
      approved: false,
    });
  });

  it('toggles back to allow with the left arrow', async () => {
    const { stdin, lastFrame } = renderApp();
    await wait(80);
    emit({
      type: 'approval_request',
      turn_id: 't1',
      request_id: 't1:1',
      command: 'ls -la',
    });
    await wait(60);
    stdin.write('[C');
    await wait(50);
    stdin.write('[D'); // left arrow
    await wait(50);
    expect(lastFrame()).toContain('❯ Allow');
    stdin.write('\r');
    await wait(60);
    expect(sent.find((m) => m.type === 'approval_response')).toMatchObject({
      approved: true,
    });
  });

  it('denies the command when escape is pressed', async () => {
    const { stdin } = renderApp();
    await wait(80);
    emit({
      type: 'approval_request',
      turn_id: 't1',
      request_id: 't1:1',
      command: 'ls -la',
    });
    await wait(60);
    stdin.write('');
    await wait(60);
    expect(sent.find((m) => m.type === 'approval_response')).toMatchObject({
      approved: false,
    });
  });

  it('cancels the active turn on escape', async () => {
    const { stdin } = renderApp();
    await wait(80);
    stdin.write('long task');
    await wait(40);
    stdin.write('\r');
    await wait(60);
    stdin.write('');
    await wait(60);
    expect(sent.some((m) => m.type === '__cancel')).toBe(true);
  });

  it('renders streamed text and the approval prompt', async () => {
    const { lastFrame } = renderApp();
    await wait(80);
    emit({
      type: 'assistant_delta',
      turn_id: 't1',
      text: 'partial answer',
      model_call_index: 1,
    });
    await wait(60);
    expect(lastFrame()).toContain('partial answer');

    emit({
      type: 'approval_request',
      turn_id: 't1',
      request_id: 't1:1',
      command: 'echo hi',
    });
    await wait(60);
    expect(lastFrame()).toContain('Shell command requires approval');
    expect(lastFrame()).toContain('echo hi');
  });
});
