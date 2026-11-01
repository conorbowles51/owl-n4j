import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { copyInGesture, needsTwoSteps, readyToCopySentence, selectForManualCopy, type CopyPayload } from "@/lib/copy-text"

/**
 * Copy on plain http (07 4.10): copies inside the click; over 5,000 rows it prepares the text first and copies
 * on the second click; if the browser refuses, the text is shown selected with "Press Ctrl+C".
 */
export interface CopyButtonProps {
  /** Builds the text (and HTML) to copy. Called inside the click for small copies. */
  build: () => CopyPayload
  rows: number
  noun: string
  label?: string
}

type State = { kind: "idle" } | { kind: "ready"; payload: CopyPayload } | { kind: "copied" } | { kind: "manual"; payload: CopyPayload }

export function CopyButton({ build, rows, noun, label = "Copy" }: CopyButtonProps) {
  const [state, setState] = useState<State>({ kind: "idle" })
  const manual = useRef<HTMLPreElement>(null)

  const attempt = (payload: CopyPayload) => {
    if (copyInGesture(payload)) setState({ kind: "copied" })
    else {
      setState({ kind: "manual", payload })
      requestAnimationFrame(() => manual.current && selectForManualCopy(manual.current))
    }
  }

  return (
    <div className="inline-flex flex-col gap-1" data-testid="copy-button">
      <div className="inline-flex flex-wrap items-center gap-2">
        {state.kind === "ready" ? (
          <>
            <span role="status" className="text-sm">{readyToCopySentence(rows, noun)}</span>
            <Button size="sm" onClick={() => attempt(state.payload)}>Copy now</Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              if (needsTwoSteps(rows)) setState({ kind: "ready", payload: build() })
              else attempt(build())
            }}
          >
            {label}
          </Button>
        )}
        {state.kind === "copied" && <span role="status" className="text-sm">Copied {rows.toLocaleString("en-US")} {noun}.</span>}
      </div>
      {state.kind === "manual" && (
        <div role="alert" className="text-sm">
          <p>The browser did not allow copying here. The text is selected below: press Ctrl+C (Command+C on a Mac).</p>
          <pre ref={manual} tabIndex={0} className="mt-1 max-h-40 overflow-auto rounded border bg-muted p-2 text-xs whitespace-pre-wrap">
            {state.payload.text}
          </pre>
        </div>
      )}
    </div>
  )
}
