import { useState } from "react"
import { Button } from "@/components/ui/button"
import { confirmDerivedText } from "../api"
import { useObjectUrl } from "./use-object-url"

export interface MachineTextItem {
  id: string
  file_uid: string
  kind: "ocr" | "transcript"
  filename: string | null
  words: string | null
}

export interface MachineTextFacts {
  total: number
  unconfirmed: number
  items: MachineTextItem[]
  items_cap: number
}

const fmt = (n: number) => n.toLocaleString("en-US")

function Original({ caseId, item }: { caseId: string; item: MachineTextItem }) {
  const shown = useObjectUrl(caseId, item.file_uid, true)
  if (shown && "error" in shown) return <p className="text-xs">{shown.error}</p>
  if (!shown) return <p role="status" className="text-xs text-muted-foreground">Loading the original</p>
  return item.kind === "transcript" ? (
    <audio controls src={shown.url} aria-label={`Listen to ${item.filename ?? "the audio"}`} className="w-full" />
  ) : (
    <img src={shown.url} alt={item.filename ?? "The image the text was read from"} className="max-h-48 object-contain" />
  )
}

/**
 * Machine text is confirmed on use (07 5 Media, M-7): before machine text is exported, quoted or added, each
 * unconfirmed text is shown with its original inline: confirm it, or keep it marked. Either way the use goes ahead;
 * a text kept marked prints and shows its mark. `onSettled(true)` once every listed text has an answer.
 */
export function MachineTextPrompt({ caseId, facts, onSettled }: { caseId: string; facts: MachineTextFacts; onSettled: (settled: boolean) => void }) {
  const [answers, setAnswers] = useState<Record<string, "confirmed" | "marked">>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const items = facts.items
  const answer = (id: string, value: "confirmed" | "marked") => {
    const next = { ...answers, [id]: value }
    setAnswers(next)
    onSettled(items.every((x) => next[x.id]))
  }
  const confirm = async (x: MachineTextItem) => {
    setBusy(x.id)
    setError(null)
    try {
      await confirmDerivedText(caseId, x.id)
      answer(x.id, "confirmed")
    } catch (e) {
      setError(e instanceof Error ? e.message : "The confirmation could not be saved.")
    } finally {
      setBusy(null)
    }
  }
  const keepAll = () => {
    const next = { ...answers }
    for (const x of items) next[x.id] = next[x.id] ?? "marked"
    setAnswers(next)
    onSettled(true)
  }
  if (!facts.unconfirmed) return null
  const more = facts.unconfirmed - items.length
  return (
    <section aria-label="Machine-generated text to check" className="flex flex-col gap-2 rounded border p-2 text-sm">
      <p className="font-medium">
        {facts.unconfirmed === 1 ? "1 machine-generated text in this export is" : `${fmt(facts.unconfirmed)} machine-generated texts in this export are`} not yet confirmed by a person.
      </p>
      {items.map((x) => (
        <div key={x.id} className="flex flex-col gap-1 border-t pt-2">
          <p>{x.kind === "transcript" ? "This transcript is machine-generated. Listen and confirm, or keep it marked." : "This text was read from an image by a machine. Look and confirm, or keep it marked."}</p>
          <p className="text-xs text-muted-foreground">{x.filename ?? "File not named in the report"}: {x.words}</p>
          <Original caseId={caseId} item={x} />
          {answers[x.id] ? (
            <p role="status" className="text-xs">{answers[x.id] === "confirmed" ? "Confirmed by you." : "Kept marked: it prints with its mark."}</p>
          ) : (
            <div className="flex gap-1">
              <Button size="sm" variant="outline" disabled={busy === x.id} onClick={() => confirm(x)}>Confirm</Button>
              <Button size="sm" variant="ghost" disabled={busy === x.id} onClick={() => answer(x.id, "marked")}>Keep it marked</Button>
            </div>
          )}
        </div>
      ))}
      {more > 0 && <p>{fmt(more)} more are not listed here; they print with their mark. Confirm them on the Media screen.</p>}
      {items.some((x) => !answers[x.id]) && (
        <Button size="sm" variant="ghost" className="self-start" onClick={keepAll}>Keep the rest marked</Button>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  )
}
