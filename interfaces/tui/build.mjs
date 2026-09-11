import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

await build({
  entryPoints: [resolve(here, 'src/cli.tsx')],
  outfile: resolve(here, 'dist/app.js'),
  bundle: true,
  platform: 'node',
  target: 'node22',
  format: 'esm',
  jsx: 'automatic',
  legalComments: 'none',
  alias: {
    // Ink imports this only on its development path.
    'react-devtools-core': resolve(here, 'stubs/react-devtools-core.js'),
  },
  define: {
    'process.env.DEV': '"false"',
    'process.env.NODE_ENV': '"production"',
  },
  // Some transitive dependencies are CommonJS and call require() at
  // runtime, which an ESM bundle does not provide by default.
  banner: {
    js: [
      "import { createRequire as __createRequire } from 'node:module';",
      'const require = __createRequire(import.meta.url);',
    ].join('\n'),
  },
});

console.log('built dist/app.js');
