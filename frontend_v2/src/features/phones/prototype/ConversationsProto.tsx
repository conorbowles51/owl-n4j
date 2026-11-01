import { useVirtualizer } from "@tanstack/react-virtual"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { register } from "@/lib/keymap"
import { usePhoneSelection } from "@/stores/phone-selection.store"
import { CASE_ZONE, messageView, stripDays, type FixtureCase, type FixtureMessage } from "../fixtures"
import { dayWords } from "../ui/TimeStrip"
import { participantsLine } from "../types"
import { timeOfDay, zoneWords } from "../lib/time-words"
import { AddToMenu } from "../ui/AddToMenu"
import { BadgeRow } from "../ui/OriginMark"
import { DockedPanel } from "../ui/DockedPanel"
import { PhoneChip } from "../ui/PhoneChip"
import { RecordPanelContent } from "../ui/RecordPanel"
import { fmt } from "../ui/ResultCount"
import { EMPTY_SCOPE, ScopeBar, type Scope } from "../ui/ScopeBar"
import { TimeStrip } from "../ui/TimeStrip"
import type { CollectClient, CollectTarget } from "../collect.api"

/** Prototype: Conversations (07 J-3, J-4, 5): thread rail, scope bar, stream with day headers, time strip,
 * docked record panel, keys, multi-select and Add to…. Synthetic data; nothing is saved. */

type Item = { kind: "day"; date: string; label: string } | { kind: "msg"; m: FixtureMessage; withSeconds: boolean }

const localDay = (iso: string, zone: string) => new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso))

export function ConversationsProto({ fx, client, targets }: { fx: FixtureCase; client: CollectClient; targets: CollectTarget[] }) {
  const [params, setParams] = useSearchParams()
  const phone = params.get("phone") ?? fx.phones[0].label
  const person = params.get("person")
  const app = params.get("app")
  const state = params.get("state")
  const [threadId, setThreadId] = useState<string | null>(params.get("thread"))
  const [find, setFind] = useState("")
  const [panel, setPanel] = useState(false)
  const [goTo, setGoTo] = useState(false)
  const sel = usePhoneSelection()
  const zone = fx.phones.find((p) => p.label === phone)?.zone ?? CASE_ZONE
  const listRef = useRef<HTMLDivElement>(null)

  const threads = useMemo(
    () => fx.threads.filter((t) => t.phone === phone && (!person || t.participants.includes(person)) && (!app || t.app === app)).sort((a, b) => b.count - a.count),
    [fx, phone, person, app]
  )
  const shownThreads = threads.filter((t) => {
    if (!find) return true
    const names = t.participants.map((k) => fx.people.find((p) => p.key === k)?.name ?? "").join(" ")
    return `${names} ${t.app}`.toLowerCase().includes(find.toLowerCase())
  })

  const messages = useMemo(() => {
    const ms = fx.messages.filter((m) => m.phone === phone && (!threadId || m.thread === threadId) && (threadId || !person || m.from === person || m.to.includes(person)) && (!app || m.app === app) && (!state || (state === "deleted" && (m.deleted === "Deleted" || m.deleted === "Trash"))))
    const timed = ms.filter((m) => m.time).sort((a, b) => a.time!.localeCompare(b.time!))
    return [...timed, ...ms.filter((m) => !m.time)]
  }, [fx, phone, threadId, person, app, state])
  const total = useMemo(() => fx.messages.filter((m) => m.phone === phone && (!threadId || m.thread === threadId)).length, [fx, phone, threadId])

  const items = useMemo(() => {
    const out: Item[] = []
    let day = ""
    messages.forEach((m, i) => {
      const d = m.time ? localDay(m.time, zone) : "none"
      if (d !== day) {
        day = d
        out.push({ kind: "day", date: d, label: m.time ? `${dayWords(d)}, ${zoneWords(m.time, zone)}` : `${fmt(messages.length - i)} messages have no time and are listed at the end` })
      }
      const prev = messages[i - 1]
      const sameMinute = !!(prev?.time && m.time && prev.time.slice(0, 16) === m.time.slice(0, 16))
      out.push({ kind: "msg", m, withSeconds: sameMinute })
    })
    return out
  }, [messages, zone])
  const order = useMemo(() => messages.map((m) => m.id), [messages])
  const days = useMemo(() => items.flatMap((it, i) => (it.kind === "day" && it.date !== "none" ? [{ date: it.date, index: i }] : [])), [items])

  const virtual = useVirtualizer({ count: items.length, getScrollElement: () => listRef.current, estimateSize: (i) => (items[i].kind === "day" ? 32 : 64), overscan: 10 })
  const focusId = sel.focus && order.includes(sel.focus) ? sel.focus : order[0]
  const focused = messages.find((m) => m.id === focusId)

  const scrollToId = useCallback(
    (id: string) => {
      const i = items.findIndex((it) => it.kind === "msg" && it.m.id === id)
      if (i >= 0) virtual.scrollToIndex(i, { align: "auto" })
    },
    [items, virtual]
  )
  const move = useCallback(
    (delta: number, extend = false) => {
      const i = Math.min(order.length - 1, Math.max(0, order.indexOf(focusId ?? "") + delta))
      const id = order[i]
      if (!id) return
      if (extend) sel.extendTo(id, order)
      else sel.focusOn(id)
      scrollToId(id)
    },
    [order, focusId, sel, scrollToId]
  )
  const jumpDay = useCallback(
    (delta: number) => {
      const cur = focused?.time ? localDay(focused.time, zone) : days[0]?.date
      const di = days.findIndex((d) => d.date === cur)
      const target = days[Math.min(days.length - 1, Math.max(0, di + delta))]
      if (!target) return
      const it = items[target.index + 1]
      if (it?.kind === "msg") {
        sel.focusOn(it.m.id)
        virtual.scrollToIndex(target.index, { align: "start" })
      }
    },
    [focused, zone, days, items, sel, virtual]
  )
  const goToDate = (date: string) => {
    const d = days.find((x) => x.date >= date)
    if (!d) return
    const it = items[d.index + 1]
    if (it?.kind === "msg") sel.focusOn(it.m.id)
    virtual.scrollToIndex(d.index, { align: "start" })
    setGoTo(false)
  }

  useEffect(
    () =>
      register("Conversations", [
        { key: "j", label: "Next message", run: () => move(1) },
        { key: "k", label: "Previous message", run: () => move(-1) },
        { key: "ArrowDown", label: "Next message", run: () => move(1) },
        { key: "ArrowUp", label: "Previous message", run: () => move(-1) },
        { key: "Shift+J", label: "Extend the selection down", run: () => move(1, true) },
        { key: "Shift+K", label: "Extend the selection up", run: () => move(-1, true) },
        { key: " ", label: "Select this message", run: () => focusId && sel.toggle(focusId) },
        { key: "r", label: "Open the record panel", run: () => setPanel(true) },
        { key: "g", label: "Go to date", run: () => setGoTo(true) },
        { key: "Alt+J", label: "Next day", run: () => jumpDay(1) },
        { key: "Alt+K", label: "Previous day", run: () => jumpDay(-1) },
        { key: "Escape", label: "Close the record panel", run: () => setPanel(false) },
      ]),
    [move, jumpDay, focusId, sel]
  )

  const scope: Scope = {
    ...EMPTY_SCOPE,
    people: person ? [{ key: person, label: fx.people.find((p) => p.key === person)?.name ?? person }] : [],
    phones: [{ id: phone, label: phone, index: fx.phones.findIndex((p) => p.label === phone), extractionDate: fx.phones.find((p) => p.label === phone)?.extraction_date }],
    kinds: [...(app ? [app] : []), ...(state ? ["deleted or in trash"] : [])],
  }
  const onScope = (s: Scope) => {
    const next = new URLSearchParams(params)
    if (!s.people.length) next.delete("person")
    if (!s.kinds.includes(app ?? "")) next.delete("app")
    if (!s.kinds.includes("deleted or in trash")) next.delete("state")
    setParams(next)
  }
  const selectedIds = sel.whole ? order : sel.ids.filter((id) => order.includes(id))
  const thread = threadId ? fx.threads.find((t) => t.id === threadId) : null

  return (
    <div className="flex h-[calc(100dvh-13rem)] min-h-[480px] overflow-hidden rounded border">
      <nav aria-label={`Threads (${fmt(threads.length)})`} className="flex w-72 shrink-0 flex-col border-r bg-card">
        <div className="border-b p-2">
          <label className="text-xs font-medium" htmlFor="thread-find">Find a thread</label>
          <input id="thread-find" className="mt-1 w-full rounded border bg-background px-2 py-1 text-sm" value={find} onChange={(e) => setFind(e.target.value)} placeholder="Name or app" />
          <p className="mt-1 text-xs">{shownThreads.length < threads.length ? `Showing ${fmt(shownThreads.length)} of ${fmt(threads.length)} threads` : `${fmt(threads.length)} threads, busiest first`}</p>
        </div>
        <ul className="min-h-0 flex-1 overflow-auto" aria-label="Threads">
          <li className="px-2 pt-2 text-xs font-semibold"><PhoneChip label={phone} index={scope.phones[0].index} /></li>
          {shownThreads.map((t) => {
            const names = t.participants.map((k) => fx.people.find((p) => p.key === k)?.name ?? "Unknown").join(", ")
            return (
              <li key={t.id}>
                <button type="button" aria-current={threadId === t.id ? "true" : undefined} onClick={() => (setThreadId(t.id), sel.clear())} className="w-full px-2 py-1.5 text-left text-sm hover:bg-muted aria-[current=true]:bg-accent">
                  <span className="block truncate font-medium">{names}</span>
                  <span className="block text-xs">{t.app} · {fmt(t.count)} messages{t.group ? " · group" : ""}</span>
                </button>
              </li>
            )
          })}
        </ul>
      </nav>
      <section aria-label="Conversation" className="flex min-w-0 flex-1 flex-col">
        <ScopeBar scope={scope} onChange={onScope} count={{ shown: messages.length, total, noun: "messages", unconfirmed: messages.length }} />
        <div className="flex flex-wrap items-center gap-2 border-b px-3 py-1.5 text-sm">
          {thread ? (
            <span className="font-medium">{thread.participants.map((k) => fx.people.find((p) => p.key === k)?.name).join(", ")} on {thread.app}</span>
          ) : (
            <span>Pick a thread or a person. The busiest are listed first.</span>
          )}
          <span className="ml-auto flex items-center gap-1">
            <Button size="sm" variant="outline" onClick={() => jumpDay(-1)}>Previous day</Button>
            <Button size="sm" variant="outline" onClick={() => jumpDay(1)}>Next day</Button>
            <Button size="sm" variant="outline" onClick={() => setGoTo((v) => !v)}>Go to date</Button>
            <Button size="sm" variant="outline" onClick={() => setPanel(true)} disabled={!focused}>Record panel</Button>
            <AddToMenu caseId="prototype" noun="messages" origin="Added from Conversations (prototype)" client={client} targets={targets} links={selectedIds.map((id) => ({ target_type: "phone_record", target_id: id, source_anchor: {} }))} />
          </span>
          {goTo && (
            <label className="flex w-full items-center gap-2">
              Go to date
              <input type="date" className="rounded border bg-background px-1" onChange={(e) => e.target.value && goToDate(e.target.value)} autoFocus />
            </label>
          )}
          {selectedIds.length > 0 && <span role="status">{fmt(selectedIds.length)} selected</span>}
        </div>
        <div ref={listRef} role="feed" aria-label="Messages" aria-busy="false" tabIndex={0} className="min-h-0 flex-1 overflow-auto focus-visible:outline-2 focus-visible:outline-ring">
          {messages.length === 0 ? (
            <p className="p-4 text-sm">No messages match these filters. <button type="button" className="underline" onClick={() => setParams({ phone })}>Remove the filters</button></p>
          ) : (
            <div style={{ height: virtual.getTotalSize(), position: "relative" }}>
              {virtual.getVirtualItems().map((v) => {
                const it = items[v.index]
                if (it.kind === "day")
                  return (
                    <h3 key={`d-${it.date}-${v.index}`} ref={virtual.measureElement} data-index={v.index} className="absolute left-0 w-full border-b bg-muted px-3 py-1 text-xs font-semibold" style={{ top: v.start }}>
                      {it.label}
                    </h3>
                  )
                const m = it.m
                const view = messageView(fx, m)
                const isFocus = m.id === focusId
                const isSel = sel.whole !== null || sel.ids.includes(m.id)
                return (
                  <article
                    key={m.id}
                    ref={virtual.measureElement}
                    data-index={v.index}
                    aria-posinset={order.indexOf(m.id) + 1}
                    aria-setsize={messages.length}
                    aria-selected={isSel}
                    onClick={(e) => (e.shiftKey ? sel.extendTo(m.id, order) : sel.focusOn(m.id))}
                    className={`absolute left-0 w-full border-b px-3 py-1.5 text-sm ${isSel ? "bg-accent" : ""} ${isFocus ? "outline-2 -outline-offset-2 outline-ring" : ""}`}
                    style={{ top: v.start }}
                  >
                    <div className="flex flex-wrap items-center gap-x-2">
                      <span className="font-medium">{m.time ? timeOfDay(m.time, zone, it.withSeconds) : "No time"}</span>
                      <span aria-label={m.direction === "outgoing" ? "Sent" : "Received"}>{m.direction === "outgoing" ? "↗" : "↙"}</span>
                      <span>{participantsLine(view)}</span>
                      <span className="text-muted-foreground">{m.app}</span>
                      <BadgeRow badges={view.badges} />
                    </div>
                    <p className="whitespace-pre-wrap break-words">{m.body || <em>No text in this message</em>}</p>
                  </article>
                )
              })}
            </div>
          )}
        </div>
        <TimeStrip days={stripDays(fx, phone, threadId ?? undefined)} zone={zoneWords(new Date().toISOString(), zone)} onPickDay={goToDate} />
      </section>
      <DockedPanel title="Record" open={panel && !!focused} onClose={() => setPanel(false)} returnFocus={() => listRef.current}>
        {focused && <RecordPanelContent record={messageView(fx, focused)} onAround={() => {}} onWindow={() => {}} onCorrect={() => {}} />}
      </DockedPanel>
    </div>
  )
}
