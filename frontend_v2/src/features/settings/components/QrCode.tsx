/** Draws the rows the server sent. On a white ground in either theme, with the quiet border scanners need. */
export function QrCode({ rows, label }: { rows: string[]; label: string }) {
  const size = rows.length
  const border = 4
  const dark = rows
    .flatMap((row, y) => Array.from(row, (cell, x) => (cell === "1" ? `M${x} ${y}h1v1h-1z` : "")))
    .join("")
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`${-border} ${-border} ${size + border * 2} ${size + border * 2}`}
      shapeRendering="crispEdges"
      className="size-56 rounded-md"
    >
      <rect x={-border} y={-border} width={size + border * 2} height={size + border * 2} fill="#fff" />
      <path d={dark} fill="#000" />
    </svg>
  )
}
