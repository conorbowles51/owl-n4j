import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { agentAPI } from "../api"

export interface AgentBrief { name: string; text: string; warnings?: string[] }
export function AgentBriefAttachment({ brief, onChange, disabled, onBusyChange }: {
  brief: AgentBrief | null; onChange: (brief: AgentBrief | null) => void; disabled: boolean; onBusyChange?: (busy: boolean) => void
}) {
  const file = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const [error, setError] = useState("")
  const [reading, setReading] = useState(false)
  useEffect(() => () => controller.current?.abort(), [])
  return <div className="mx-auto mb-2 max-w-3xl text-xs">
    <input ref={file} type="file" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" aria-label="Attach a brief" className="sr-only" disabled={disabled || reading} onChange={async (event) => {
      const chosen = event.target.files?.[0]
      if (!chosen) return
      const input = event.target
      const request = new AbortController()
      controller.current = request
      setError("")
      setReading(true); onBusyChange?.(true)
      try {
        if (!/\.(txt|md|pdf|docx)$/i.test(chosen.name)) throw new Error("Choose a text, Markdown, PDF or Word (.docx) brief. Other source files can be added through Evidence.")
        if (chosen.size > 10 * 1024 * 1024) throw new Error("This brief is too large. Choose a file below 10 MiB.")
        const result = /\.(pdf|docx)$/i.test(chosen.name)
          ? await agentAPI.previewBrief(chosen, request.signal)
          : { text: await chosen.text(), warnings: [] }
        if (request.signal.aborted) return
        if (result.text.length > 250_000) throw new Error("This brief exceeds 250,000 characters. Split it into separate instructions.")
        if (!result.text.trim()) throw new Error("This brief has no readable text. Add a text brief or a PDF with selectable text.")
        onChange({ name: chosen.name, text: result.text, warnings: result.warnings })
      } catch (e) { if (!request.signal.aborted) setError(e instanceof Error ? e.message : "Could not read this brief.") }
      finally { input.value = ""; if (!request.signal.aborted) { setReading(false); onBusyChange?.(false) } }
    }} />
    {!brief ? <div className="flex flex-wrap items-center gap-2"><Button size="sm" variant="ghost" disabled={disabled || reading} onClick={() => file.current?.click()}>{reading ? "Preparing brief…" : "Attach brief or template"}</Button><span className="text-muted-foreground">TXT, Markdown, PDF or DOCX · PDF and Word text is extracted for review.</span></div> : <div className="rounded border border-border bg-muted/20 p-2">
      <div className="flex items-center justify-between gap-2"><span>{brief.name} · {brief.text.length.toLocaleString()} characters · included with your next message</span><Button size="sm" variant="ghost" disabled={disabled} onClick={() => onChange(null)}>Remove</Button></div>
      {!!brief.warnings?.length && <ul className="my-2 list-disc pl-4 text-amber-700 dark:text-amber-400">{brief.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}
      <details open><summary className="cursor-pointer text-muted-foreground">Review attached brief</summary><pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-sans">{brief.text}</pre></details>
    </div>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
  </div>
}
