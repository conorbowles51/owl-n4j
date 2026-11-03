/** A plain note on the map when the base map held on this server cannot be drawn: never a silent blank. */
export function BasemapNote({ text }: { text: string }) {
  return (
    <div
      role="status"
      className="pointer-events-none absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-md border border-border bg-background/90 px-3 py-1.5 text-xs text-foreground shadow"
    >
      {text}
    </div>
  )
}
