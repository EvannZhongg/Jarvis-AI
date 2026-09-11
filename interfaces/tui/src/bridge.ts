import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { MessageDecoder, type Incoming, type Outgoing } from './protocol.js';

export type BridgeOptions = {
  python: string;
  cwd: string;
  onMessage: (message: Incoming) => void;
  onExit: (code: number | null) => void;
  onProtocolError: (error: Error) => void;
};

/** Owns the Python agent process and the protocol stream. */
export class BridgeClient {
  private child: ChildProcessWithoutNullStreams;
  private decoder = new MessageDecoder();
  private stderr: string[] = [];

  constructor(options: BridgeOptions) {
    this.child = spawn(options.python, ['-m', 'interfaces.bridge'], {
      cwd: options.cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
    }) as ChildProcessWithoutNullStreams;

    this.child.stdout.setEncoding('utf8');
    this.child.stdout.on('data', (chunk: string) => {
      let messages: Incoming[];
      try {
        messages = this.decoder.push(chunk);
      } catch (error) {
        options.onProtocolError(error as Error);
        return;
      }
      for (const message of messages) options.onMessage(message);
    });

    // Diagnostics only; kept for crash reporting.
    this.child.stderr.setEncoding('utf8');
    this.child.stderr.on('data', (chunk: string) => {
      this.stderr.push(chunk);
      if (this.stderr.length > 50) this.stderr.shift();
    });

    this.child.on('exit', (code) => options.onExit(code));
  }

  send(message: Outgoing): void {
    if (this.child.exitCode !== null || this.child.killed) return;
    this.child.stdin.write(`${JSON.stringify(message)}\n`);
  }

  /** Cancels the active turn. Ink consumes Ctrl+C, so signal explicitly. */
  cancel(): void {
    this.child.kill('SIGINT');
  }

  shutdown(): void {
    this.send({ type: 'shutdown' });
    this.child.stdin.end();
    const child = this.child;
    setTimeout(() => {
      if (child.exitCode === null) child.kill('SIGKILL');
    }, 2000).unref();
  }

  diagnostics(): string {
    return this.stderr.join('');
  }
}
