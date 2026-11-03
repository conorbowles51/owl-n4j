import { markdownToPlainText } from "@/lib/markdown-text"
import type { TimelineEvent } from "../api"

/** Existing Timeline events with no usable date (03 section 15.6): counted and listed, never dropped. */
export function UndatedEvents({ events }: { events: TimelineEvent[] }) {
  return (
    <details className="border-t px-4 py-2 text-sm">
      <summary className="cursor-pointer font-medium">
        No time recorded: {events.length.toLocaleString("en-US")} {events.length === 1 ? "event has" : "events have"} no usable date
      </summary>
      <ul aria-label="Events with no time recorded" className="mt-2 flex max-h-64 flex-col gap-1 overflow-auto">
        {events.map((e) => (
          <li key={e.key} className="flex flex-col">
            <span className="font-medium">{e.name}</span>
            <span className="text-xs text-muted-foreground">
              {e.type}
              {e.date ? ` · date as entered: ${e.date}` : " · no date entered"}
              {e.summary ? ` · ${markdownToPlainText(e.summary).slice(0, 160)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}
