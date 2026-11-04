import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { useCase } from "@/features/cases/hooks/use-cases"
import { describeSetup, getExternalProcessing, getPhoneSetup, saveClockOffset, savePhoneSetting, type DecisionNote, type PhoneSetup as Setup, type SetupKind } from "../api"
import { readingsAPI } from "../review/readings.api"
import { fmt } from "../ui/count-sentence"
import { clockPeriodWords, clockRequest, decidedWords, offsetAmountWords, setupError, ZONES } from "./setup-words"

/**
 * The working controls of the Needs a decision box (03 section 7.3, 07 section 5): default region, device zone,
 * applying a zone to times with no offset, and clock offset. Each states what would change, in true counts, before
 * it is saved, and needs a reason; saving writes a decision and a feed line, and the phone is read again. An assumed
 * value says it is assumed. Undo goes back to what held before the decision and leaves both in the record.
 */
export function PhoneSetup({ caseId, extraction }: { caseId: string; extraction: string }) {
  const qc = useQueryClient()
  const setup = useQuery({ queryKey: ["phone-setup", caseId, extraction], queryFn: () => getPhoneSetup(caseId, extraction), enabled: !!caseId && !!extraction })
  const kase = useCase(caseId)
  const role = kase.data?.user_role
  const canEdit = !!role && ["owner", "editor", "admin_access"].includes(role)
  const [watching, setWatching] = useState(false)
  const progress = useQuery({
    queryKey: ["phone-reading-progress", caseId],
    queryFn: () => readingsAPI.progress(caseId),
    enabled: watching,
    refetchInterval: watching ? 1000 : false,
  })
  const mine = progress.data?.phones.find((p) => p.extraction_id === extraction)
  const reread = watching && mine ? mine : null
  useEffect(() => {
    if (!watching || !mine || mine.state !== "done") return
    setWatching(false)
    void qc.invalidateQueries({ queryKey: ["phone-setup", caseId, extraction] })
    void qc.invalidateQueries({ queryKey: ["phone-profile", caseId, extraction] })
    void qc.invalidateQueries({ queryKey: ["phones", caseId] })
  }, [watching, mine, qc, caseId, extraction])
  const saved = () => {
    void qc.invalidateQueries({ queryKey: ["phone-setup", caseId, extraction] })
    void qc.invalidateQueries({ queryKey: ["phone-reading-progress", caseId] })
    setWatching(true)
  }
  if (setup.isLoading) return <p className="mt-2 text-xs">Loading this phone's settings</p>
  if (setup.isError || !setup.data) return <p role="alert" className="mt-2 text-xs">{setupError(setup.error, "This phone's settings could not be loaded.")}</p>
  const s = setup.data
  return (
    <div className="mt-3 flex flex-col gap-2 border-t pt-2 text-xs" aria-label="Phone settings">
      {!canEdit && <p>You can view this case. A case owner or editor can change these settings.</p>}
      {reread && (
        <p role="status">
          {reread.state === "waiting"
            ? "Waiting to read this phone again. Counts on this page update when it finishes."
            : `Reading this phone again: ${fmt(reread.records_done)} of ${fmt(reread.records_total)} records.`}
        </p>
      )}
      <Choice
        title="Default country"
        anchor="set-region"
        canEdit={canEdit}
        statement={
          <>
            {s.region.words}
            {s.region.assumed ? ". This country is assumed, not known." : "."}
            {s.region.unread > 0 && ` ${fmt(s.region.unread)} more could not be read as numbers there.`}
          </>
        }
        decision={s.region.decision}
        undo={() => savePhoneSetting(caseId, extraction, "region", s.region.undo_to, `Undo of: ${s.region.decision?.reason ?? ""}`)}
        options={s.regions.map((r) => ({ value: r.code, label: r.name }))}
        placeholder="Choose a country"
        kind="region"
        caseId={caseId}
        extraction={extraction}
        onSave={(value, reason) => savePhoneSetting(caseId, extraction, "region", value, reason)}
        onSaved={saved}
      />
      <Choice
        title="Phone's time zone"
        anchor="set-zone"
        canEdit={canEdit}
        statement={zoneStatement(s)}
        decision={s.zone.decision}
        undo={() => savePhoneSetting(caseId, extraction, "device_zone", s.zone.undo_to, `Undo of: ${s.zone.decision?.reason ?? ""}`)}
        options={ZONES().map((z) => ({ value: z, label: z.replace(/_/g, " ") }))}
        placeholder="Choose a time zone"
        kind="device_zone"
        caseId={caseId}
        extraction={extraction}
        onSave={(value, reason) => savePhoneSetting(caseId, extraction, "device_zone", value, reason)}
        onSaved={saved}
      />
      <Choice
        title="Times with no offset"
        anchor="set-offsetless"
        canEdit={canEdit}
        statement={
          s.offsetless.times === 0
            ? "Every time on this phone has its offset in the report."
            : s.offsetless.zone
              ? `${fmt(s.offsetless.applied)} of ${fmt(s.offsetless.times)} times the report wrote with no offset are read in ${s.offsetless.name ?? s.offsetless.zone}, by decision. Each says so where it is shown.`
              : `${fmt(s.offsetless.times)} ${s.offsetless.times === 1 ? "time was" : "times were"} written with no offset. Loupe has not assumed one.`
        }
        decision={s.offsetless.decision}
        undo={() => savePhoneSetting(caseId, extraction, "offsetless_zone", s.offsetless.undo_to, `Undo of: ${s.offsetless.decision?.reason ?? ""}`)}
        options={ZONES().map((z) => ({ value: z, label: z.replace(/_/g, " ") }))}
        placeholder="Choose a time zone"
        kind="offsetless_zone"
        caseId={caseId}
        extraction={extraction}
        disabledWords={s.offsetless.times === 0 ? "Nothing to apply on this phone." : null}
        onSave={(value, reason) => savePhoneSetting(caseId, extraction, "offsetless_zone", value, reason)}
        onSaved={saved}
      />
      <ClockOffset caseId={caseId} extraction={extraction} setup={s} canEdit={canEdit} onSaved={saved} />
      <OutsideProcessing caseId={caseId} extraction={extraction} />
    </div>
  )
}

function zoneStatement(s: Setup): string {
  if (s.zone.basis === "decided") return `Set to ${s.zone.name ?? s.zone.zone} by decision.${s.zone.report_zone ? ` The report recorded ${s.zone.report_zone}.` : " The report recorded none."}`
  if (s.zone.zone) return `Recorded by the phone: ${s.zone.name ?? s.zone.zone}.`
  return `The report recorded no time zone for this phone.${s.zone.examiner_zone ? ` The examiner's report setting was ${s.zone.examiner_zone}, which is not evidence of the phone.` : ""}`
}

interface ChoiceProps {
  title: string
  anchor: string
  canEdit: boolean
  statement: ReactNode
  decision: DecisionNote | null
  undo: () => Promise<unknown>
  options: { value: string; label: string }[]
  placeholder: string
  kind: SetupKind
  caseId: string
  extraction: string
  disabledWords?: string | null
  onSave: (value: string, reason: string) => Promise<unknown>
  onSaved: () => void
}

function Choice({ title, anchor, canEdit, statement, decision, undo, options, placeholder, kind, caseId, extraction, disabledWords, onSave, onSaved }: ChoiceProps) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState("")
  const [reason, setReason] = useState("")
  useEffect(() => {
    // arriving from a link in the Needs a decision list (…/phones/<id>#set-zone) opens the control
    const hash = () => { if (window.location.hash === `#${anchor}`) setOpen(true) }
    hash()
    window.addEventListener("hashchange", hash)
    return () => window.removeEventListener("hashchange", hash)
  }, [anchor])
  const preview = useQuery({
    queryKey: ["phone-setup-describe", caseId, extraction, kind, value],
    queryFn: () => describeSetup(caseId, extraction, { kind, value }),
    enabled: open && !!value,
  })
  const save = useMutation({
    mutationFn: () => onSave(value, reason.trim()),
    onSuccess: () => {
      setOpen(false)
      setValue("")
      setReason("")
      onSaved()
    },
  })
  const back = useMutation({ mutationFn: undo, onSuccess: onSaved })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (value && reason.trim() && preview.data) save.mutate()
  }
  return (
    <div id={anchor} className="flex flex-col gap-1">
      <p>
        <span className="font-medium">{title}:</span> {statement}{" "}
        {decision && <span className="text-muted-foreground">{decidedWords(decision)} </span>}
        {decision && canEdit && (
          <button type="button" className="underline underline-offset-2" disabled={back.isPending} onClick={() => back.mutate()}>
            Undo
          </button>
        )}{" "}
        {canEdit && !disabledWords && (
          <button type="button" className="underline underline-offset-2" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? "Close" : "Change"}
          </button>
        )}
      </p>
      {back.isError && <p role="alert">{setupError(back.error, "The undo could not be saved. Nothing changed.")}</p>}
      {open && (
        <form aria-label={title} className="flex flex-col gap-1.5 rounded border bg-background p-2" onSubmit={submit}>
          <select aria-label={title} className="rounded border bg-background px-2 py-1" value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">{placeholder}</option>
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          {value && preview.isLoading && <p role="status">Counting what this would change</p>}
          {preview.data && <p role="status">{preview.data.words}</p>}
          {preview.isError && <p role="alert">{setupError(preview.error, "What this would change could not be counted.")}</p>}
          <label className="flex flex-col gap-0.5">
            <span>Reason, in your own words</span>
            <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <span className="flex items-center gap-2">
            <Button type="submit" size="sm" variant="outline" disabled={!value || !reason.trim() || !preview.data || save.isPending}>
              Save and read again
            </Button>
            {save.isPending && <span role="status">Saving</span>}
          </span>
          {save.isError && <p role="alert">{setupError(save.error, "This could not be saved. Nothing changed.")}</p>}
        </form>
      )}
    </div>
  )
}

/** A device clock that ran fast or slow for a period (02 section 10.1). Dates are whole UTC days; empty is open. */
function ClockOffset({ caseId, extraction, setup, canEdit, onSaved }: { caseId: string; extraction: string; setup: Setup; canEdit: boolean; onSaved: () => void }) {
  const [open, setOpen] = useState(false)
  const [way, setWay] = useState<"fast" | "slow">("fast")
  const [minutes, setMinutes] = useState("")
  const [seconds, setSeconds] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [reason, setReason] = useState("")
  const request = clockRequest(way, minutes, seconds, from, to)
  const preview = useQuery({
    queryKey: ["phone-setup-describe", caseId, extraction, "clock_offset", request],
    queryFn: () => describeSetup(caseId, extraction, { kind: "clock_offset", offset_seconds: request?.seconds, start: request?.start, end: request?.end }),
    enabled: open && !!request,
    retry: false,
  })
  const save = useMutation({
    mutationFn: () => saveClockOffset(caseId, extraction, request!.seconds, request!.start, request!.end, reason.trim()),
    onSuccess: () => {
      setOpen(false)
      setMinutes("")
      setSeconds("")
      setFrom("")
      setTo("")
      setReason("")
      onSaved()
    },
  })
  const undo = useMutation({
    mutationFn: (p: Setup["clock"]["periods"][number]) => saveClockOffset(caseId, extraction, 0, p.start, p.end, `Undo of: ${p.decision.reason ?? ""}`),
    onSuccess: onSaved,
  })
  const periods = setup.clock.periods
  return (
    <div id="set-clock" className="flex flex-col gap-1">
      <p>
        <span className="font-medium">Clock offset:</span>{" "}
        {periods.length === 0 ? "None recorded. Times are as the phone's clock gave them." : `${fmt(periods.length)} recorded.`}{" "}
        {canEdit && (
          <button type="button" className="underline underline-offset-2" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
            {open ? "Close" : "Add"}
          </button>
        )}
      </p>
      {periods.length > 0 && (
        <ul aria-label="Clock offsets" className="flex flex-col gap-0.5">
          {periods.map((p) => (
            <li key={`${p.start}|${p.end}`}>
              {offsetAmountWords(p.offset_seconds)} {clockPeriodWords(p.start, p.end)}: {fmt(p.times)} {p.times === 1 ? "time" : "times"} moved.{" "}
              <span className="text-muted-foreground">{decidedWords(p.decision)} </span>
              {canEdit && (
                <button type="button" className="underline underline-offset-2" disabled={undo.isPending} onClick={() => undo.mutate(p)}>
                  Undo
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {undo.isError && <p role="alert">{setupError(undo.error, "The undo could not be saved. Nothing changed.")}</p>}
      {open && (
        <form
          aria-label="Clock offset"
          className="flex flex-col gap-1.5 rounded border bg-background p-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (request && reason.trim() && preview.data) save.mutate()
          }}
        >
          <span className="flex flex-wrap items-center gap-1.5">
            The phone's clock ran
            <select aria-label="Fast or slow" className="rounded border bg-background px-1 py-0.5" value={way} onChange={(e) => setWay(e.target.value as "fast" | "slow")}>
              <option value="fast">fast</option>
              <option value="slow">slow</option>
            </select>
            by
            <input aria-label="Minutes" type="number" min={0} className="w-16 rounded border bg-background px-1 py-0.5" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
            minutes
            <input aria-label="Seconds" type="number" min={0} max={59} className="w-14 rounded border bg-background px-1 py-0.5" value={seconds} onChange={(e) => setSeconds(e.target.value)} />
            seconds
          </span>
          <span className="flex flex-wrap items-center gap-1.5">
            From (UTC day, empty for the start)
            <input aria-label="From" type="date" className="rounded border bg-background px-1 py-0.5" value={from} onChange={(e) => setFrom(e.target.value)} />
            to (UTC day, empty for the end)
            <input aria-label="To" type="date" className="rounded border bg-background px-1 py-0.5" value={to} onChange={(e) => setTo(e.target.value)} />
          </span>
          {preview.data && <p role="status">{preview.data.words}</p>}
          {preview.isError && <p role="alert">{setupError(preview.error, "What this would change could not be counted.")}</p>}
          <label className="flex flex-col gap-0.5">
            <span>Reason, in your own words</span>
            <textarea className="rounded border bg-background px-2 py-1" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <span className="flex items-center gap-2">
            <Button type="submit" size="sm" variant="outline" disabled={!request || !reason.trim() || !preview.data || save.isPending}>
              Save and read again
            </Button>
            {save.isPending && <span role="status">Saving</span>}
          </span>
          {save.isError && <p role="alert">{setupError(save.error, "This could not be saved. Nothing changed.")}</p>}
        </form>
      )}
    </div>
  )
}

/** The link to the external-processing decision (03 section 7.3); the decision itself lives in Case settings. */
function OutsideProcessing({ caseId, extraction }: { caseId: string; extraction: string }) {
  const q = useQuery({ queryKey: ["phone-external", caseId, extraction], queryFn: () => getExternalProcessing(caseId, extraction), enabled: !!caseId && !!extraction })
  return (
    <p id="external-processing">
      <span className="font-medium">Outside services:</span>{" "}
      {q.isError ? "This decision could not be read." : !q.data ? "Reading this decision" : q.data.external_processing ? `Allowed${q.data.decided_by ? ` by ${q.data.decided_by}` : ""}.` : "Not allowed for this phone."}{" "}
      <Link className="underline underline-offset-2" to={`/cases/${encodeURIComponent(caseId)}/settings#phones`}>
        Open in Case settings
      </Link>
    </p>
  )
}
