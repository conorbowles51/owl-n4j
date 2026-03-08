/**
 * BuildFooter — Shows the current build name, commit, and timestamp.
 * Injected at compile time via Vite's `define` in vite.config.js.
 *
 * Renders as a fixed bar at the bottom-right of the viewport so it
 * persists across every view without requiring layout changes.
 */
export default function BuildFooter() {
  return (
    <div
      className="fixed bottom-0 right-0 z-40 px-3 py-0.5 pointer-events-auto"
      style={{ fontSize: '10px', lineHeight: '16px' }}
    >
      <span
        className="text-light-400/60 hover:text-light-600 cursor-default transition-colors select-none"
        title={`Commit: ${__BUILD_COMMIT__} • Built: ${__BUILD_TIMESTAMP__}`}
      >
        {__BUILD_NAME__} ({__BUILD_COMMIT__})
      </span>
    </div>
  );
}
