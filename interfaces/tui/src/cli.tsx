#!/usr/bin/env node
import { render } from 'ink';
import { homedir } from 'node:os';
import { join, resolve } from 'node:path';
import { App } from './app.js';

type Options = {
  workspace: string;
  sessionId: string | null;
  providerConfigPath: string;
  agentConfigPath: string;
};

const USAGE = `Usage: jarvis [options]

Options:
  --workspace <path>      Workspace directory (default: current directory)
  --session <id>          Resume an existing session
  --config <path>         Provider configuration file
  --agent-config <path>   Agent behaviour configuration file
  -h, --help              Show this message
`;

function parseArguments(argv: string[]): Options {
  const configDirectory = join(homedir(), '.jarvis');
  const options: Options = {
    workspace: process.cwd(),
    sessionId: null,
    providerConfigPath: join(configDirectory, 'provider_config.json'),
    agentConfigPath: join(configDirectory, 'agent_config.json'),
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === '--help' || argument === '-h') {
      process.stdout.write(USAGE);
      process.exit(0);
    }
    const value = argv[index + 1];
    if (value === undefined) {
      process.stderr.write(`Missing value for ${argument}\n`);
      process.exit(2);
    }
    index += 1;
    switch (argument) {
      case '--workspace':
        options.workspace = resolve(value);
        break;
      case '--session':
        options.sessionId = value;
        break;
      case '--config':
        options.providerConfigPath = resolve(value);
        break;
      case '--agent-config':
        options.agentConfigPath = resolve(value);
        break;
      default:
        process.stderr.write(`Unknown option: ${argument}\n${USAGE}`);
        process.exit(2);
    }
  }

  return options;
}

const options = parseArguments(process.argv.slice(2));

const python = process.env.JARVIS_PYTHON;
if (!python) {
  process.stderr.write(
    'JARVIS_PYTHON is not set. Run Jarvis through the "jarvis" command.\n',
  );
  process.exit(2);
}

render(
  <App
    python={python}
    workspace={options.workspace}
    sessionId={options.sessionId}
    providerConfigPath={options.providerConfigPath}
    agentConfigPath={options.agentConfigPath}
  />,
  // Ink would otherwise unmount on Ctrl+C; we use it to cancel a turn.
  { exitOnCtrlC: false, patchConsole: false },
);
