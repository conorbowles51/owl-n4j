import { useEffect, useMemo, useRef, useState } from "react"
import { trackUx } from "@/lib/ux-events"
import { Link, Navigate, useLocation, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { GuideDialog } from "@/components/ui/guide-dialog"
import { ReportProblem } from "@/components/ui/report-problem"
import { PHONE_GUIDES } from "../guide"
import { PageHeader } from "@/components/ui/page-header"
import { installKeymap } from "@/lib/keymap"
import { useSwitch } from "@/lib/ui-switches"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import type { CollectClient, CollectTarget } from "../collect.api"
import { KeymapOverlay } from "../ui/KeymapOverlay"
import { PhoneChip } from "../ui/PhoneChip"
import { ConversationsProto } from "./ConversationsProto"
import { NeedsDecisionProto } from "./NeedsDecisionProto"
import { PhoneSummaryProto } from "./PhoneSummaryProto"
import { pickCase } from "./proto-data"

/**
 * The clickable phone prototype (07 12.1 item D, R0): Phone summary, Conversations, Needs a decision and Add to…
 * on synthetic phones, behind the "phone-prototype" switch, which is off. With the switch off the route sends
 * the person back to the case and the sidebar shows nothing. Nothing here reads or writes case data.
 */

const VIEWS = [
  { id: "summary", words: "Phone summary" },
  { id: "conversations", words: "Conversations" },
  { id: "needs-a-decision", words: "Needs a decision" },
] as const

/** Add to… in the prototype keeps additions in this page only (nothing reaches the case). */
function memoryClient(store: Map<string, Set<string>>): CollectClient {
  return {
    async add(_case, target, links) {
      const have = store.get(target.id) ?? new Set<string>()
      let added = 0
      for (const l of links) {
        if (have.has(l.target_id)) continue
        have.add(l.target_id)
        added++
      }
      store.set(target.id, have)
      return { added, skipped: links.length - added, refused: 0 }
    },
  }
}

export default function PhonePrototypePage() {
  const { id: caseId, view = "summary" } = useParams()
  const on = useSwitch("phone-prototype")
  const location = useLocation()
  const fx = useMemo(() => pickCase(location.search), [location.search])
  const [phone, setPhone] = useState(fx.phones[0].label)
  const [owners, setOwners] = useState<Record<string, string | null>>({})
  const [keysOpen, setKeysOpen] = useState(false)
  const store = useMemo(() => new Map<string, Set<string>>(), [])
  const client = useMemo(() => memoryClient(store), [store])
  const targets: CollectTarget[] = useMemo(
    () => [
      { kind: "finding", id: "f1", label: "Meetings were arranged by message (synthetic)", recent: true },
      { kind: "theory", id: "t1", label: "Two phones belong to one person (synthetic)" },
      { kind: "note", id: "n1", label: "Reading notes (synthetic)" },
      { kind: "label", id: "l1", label: "Follow up" },
      { kind: "dossier", id: "d1", label: `${fx.people[1].name} (synthetic dossier)`, linkedPerson: true },
      { kind: "dossier", id: "d2", label: `${fx.people[2].name} (synthetic dossier)` },
      { kind: "timeline", id: "tl", label: "The case Timeline" },
    ],
    [fx]
  )
  const title = VIEWS.find((v) => v.id === view)?.words ?? "Phone summary"
  const lastView = useRef<string | null>(null)
  useEffect(() => {
    if (!on) return
    const screen = `prototype-${view}`
    if (lastView.current && lastView.current !== screen)
      trackUx(caseId ?? null, { event: "screen_switch", from_screen: lastView.current, to_screen: screen })
    lastView.current = screen
  }, [view, on, caseId])
  useEffect(() => {
    installKeymap()
    usePhoneSelection.getState().setCase(`prototype:${caseId}`)
  }, [caseId])
  useEffect(() => {
    document.title = `${title} (prototype) · Loupe`
  }, [title])

  if (!on) return <Navigate to={`/cases/${caseId}`} replace />
  const base = `/cases/${caseId}/phones-prototype`
  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4 text-foreground">
      <p role="note" className="rounded border border-status-model bg-status-model-soft px-3 py-2 text-sm text-status-model">
        Prototype on synthetic phones ({fx.case}). Nothing here is case evidence, and nothing you do here is saved.
      </p>
      <PageHeader
        title={`${title} (prototype)`}
        description="Invented people, numbers and messages, at the shape of real phone reports."
        actions={
          <>
            <Button size="sm" variant="outline" onClick={() => setKeysOpen(true)}>Keys</Button>
            <GuideDialog guides={PHONE_GUIDES} />
            {caseId && (
              <ReportProblem
                caseId={caseId}
                screen={`prototype-${view}`}
                scope={{ phones: fx.phones.length, people: fx.people.length, messages: fx.messages.length }}
                components={["prototype", `prototype-${view}`]}
              />
            )}
          </>
        }
      />
      <nav aria-label="Prototype screens" className="flex flex-wrap items-center gap-2 border-b pb-2">
        {VIEWS.map((v) => (
          <Link key={v.id} to={`${base}/${v.id}${location.search}`} aria-current={view === v.id ? "page" : undefined} className="rounded px-2 py-1 text-sm font-medium hover:bg-muted aria-[current=page]:bg-accent">
            {v.words}
          </Link>
        ))}
        {view === "summary" && (
          <span className="ml-auto flex items-center gap-1 text-sm" role="group" aria-label="Choose a phone">
            {fx.phones.map((p, i) => (
              <button key={p.label} type="button" aria-pressed={phone === p.label} onClick={() => setPhone(p.label)} className="rounded border px-1 py-0.5 aria-[pressed=true]:bg-accent">
                <PhoneChip label={p.label} index={i} className="border-0 bg-transparent" />
              </button>
            ))}
          </span>
        )}
      </nav>
      {view === "conversations" ? (
        <ConversationsProto fx={fx} client={client} targets={targets} />
      ) : view === "needs-a-decision" ? (
        <NeedsDecisionProto fx={fx} reviewer="you" caseId={caseId ?? null} />
      ) : (
        <PhoneSummaryProto fx={fx} phone={phone} base={base} owners={owners} setOwner={(p, k) => setOwners((o) => ({ ...o, [p]: k }))} />
      )}
      <KeymapOverlay open={keysOpen} onOpenChange={setKeysOpen} />
    </div>
  )
}
