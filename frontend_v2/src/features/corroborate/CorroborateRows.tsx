import { useState } from "react"
import { Button } from "@/components/ui/button"
import { useSwitch } from "@/lib/ui-switches"
type Member = { type: string; id: string; label?: string }
import { QuestionMenu } from "./QuestionMenu"
import type { Scope } from "./api"
import { addPart } from "./selection-store"

/**
 * "Corroborate these" for a list that can hold more rows than it shows (lx-corroselect C): ``read`` returns every row of
 * the selection, fetching what is not loaded, so the count is the whole set, never the rows on screen.
 */
export function CorroborateRows({ caseId, screen, words, count, read, disabled, scope }: {
  caseId: string
  screen: string
  words: string
  /** The whole count this will read, stated on the button. */
  count: number
  read: () => Promise<Member[] | { members: Member[]; skipped: { type: string; count: number }[] }>
  disabled?: boolean
  /** A window the question opens already limited to (the Timeline range). The person can change it. */
  scope?: Scope
}) {
  const on = useSwitch("corroborate-v2")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [menu, setMenu] = useState(false)
  if (!on) return null
  const go = async () => {
    setBusy(true)
    setError(null)
    try {
      const got = await read()
      const members = Array.isArray(got) ? got : got.members
      addPart(caseId, { screen, label: `${words} (${members.length.toLocaleString("en-US")})`, members, skipped: Array.isArray(got) ? [] : got.skipped })
      setMenu(true)
    } catch (e) {
      setError(`Not every row could be read, so nothing was selected: ${e instanceof Error ? e.message : "it failed"}`)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Button size="sm" variant="outline" disabled={disabled || busy || count === 0} onClick={() => void go()}
        title={count === 0 ? "Nothing is selected" : `Corroborate all ${count.toLocaleString("en-US")}, not only the rows on screen`}>
        {busy ? "Reading every row…" : `Corroborate ${count.toLocaleString("en-US")}`}
      </Button>
      {error && <span role="alert" className="text-xs">{error}</span>}
      {menu && <QuestionMenu caseId={caseId} initialScope={scope} onClose={() => setMenu(false)} />}
    </>
  )
}
