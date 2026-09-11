// Ink only touches react-devtools-core in development, but esbuild
// follows the import statically. Aliasing it to this stub keeps the
// bundle self-contained.
export default {};
export const connectToDevTools = () => {};
