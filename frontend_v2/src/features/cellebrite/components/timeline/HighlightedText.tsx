import { Fragment } from "react"

import { splitForHighlight } from "./timelineUtils"

export function HighlightedText({
  text,
  highlights,
  className,
}: {
  text: string
  highlights: string[]
  className?: string
}) {
  const parts = splitForHighlight(text, highlights)
  if (parts.length === 0) return null
  if (parts.length === 1 && !parts[0].match) return <span className={className}>{parts[0].text}</span>

  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.match ? (
          <mark key={`${part.text}-${index}`} className="rounded-sm bg-amber-200 px-0.5 text-slate-950">
            {part.text}
          </mark>
        ) : (
          <Fragment key={`${part.text}-${index}`}>{part.text}</Fragment>
        )
      )}
    </span>
  )
}
