import { useEffect, useMemo } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"
import { useQueries, useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/cn"
import { useCase } from "@/features/cases/hooks/use-cases"
import { PhoneReadinessCard } from "@/features/evidence/components/PhoneReadinessCard"
import { useJobs } from "@/features/evidence/hooks/use-jobs"
import { phonesQuery } from "../phones-query"
import { phoneProfileQuery } from "../phone-queries"
import { readingsAPI, type Reading } from "../review/readings.api"
import { IdentityLinkGroup } from "../review/IdentityLinkGroup"
import { PeopleSuggestions } from "../review/PeopleSuggestions"
import { ReadingRechecks } from "../review/ReadingRechecks"
import type { Profile } from "../schemas"
import { PhoneSetup } from "../summary/PhoneSetup"
import { SetOwner } from "../summary/SetOwner"
import { PhoneShape } from "../ui/PhoneChip"
import { ReadingCheck } from "./ReadingCheck"
import { arrivalWords, NEED_ACTION, NEED_ANCHOR, needTitle, phoneStatus, readingsMark, settleTitle, type PhoneStatus } from "./setup-words"

/**
 * Phones › Set up (screen 6). For whoever can set the case up: every phone with how it arrived and what is left to
 * settle, the chosen phone's decisions (time zone, clock, owner) each with a reason and undo, and the check of how
 * the system read it. People who can only view the case see each phone's readings state as a plain mark.
 */
const EDIT_ROLES = ["owner", "editor", "admin_access"]

const PILL: Record<PhoneStatus["tone"], string> = {
  ready: "bg-status-success-soft text-status-success",
  todo: "bg-status-warning-soft text-status-warning",
  busy: "bg-status-info-soft text-status-info",
  held: "bg-status-neutral-soft text-foreground",
}

function go(anchor: string) {
  window.location.hash = anchor
  document.getElementById(anchor)?.scrollIntoView({ block: "start", behavior: "smooth" })
}

function PhoneRow({ label, index, owner, profile, readings, chosen, onChoose }: {
  label: string; index: number; owner: string | null; profile: Profile | undefined; readings: Reading[]; chosen: boolean; onChoose: () => void
}) {
  const status = profile ? phoneStatus(profile) : null
  const progress = profile?.phone.ingest_progress
  const mark = readingsMark(readings)
  return (
    <li>
      <button type="button" onClick={onChoose} aria-current={chosen ? "true" : undefined}
        className="flex w-full items-center gap-3 border-t px-1 py-3 text-left hover:bg-muted/60 aria-[current=true]:bg-muted/40 aria-[current=true]:shadow-[inset_3px_0_0_var(--color-foreground)]">
        <PhoneShape index={index} />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold">{label} <span className="font-normal text-muted-foreground">{owner ?? "owner not set yet"}</span></span>
          <span className="mt-0.5 block text-xs text-muted-foreground">{profile ? arrivalWords(profile) : "Loading this phone."}</span>
          {profile?.verdict.word === "Still reading" && progress != null && (
            <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden><span className="block h-full bg-status-info" style={{ width: `${Math.round(progress * 100)}%` }} /></span>
          )}
          {!mark.checked && <span className="mt-0.5 block text-xs text-muted-foreground">{readings.filter((r) => r.status === "open").length.toLocaleString("en-US")} readings not checked yet.</span>}
        </span>
        {status && <span className={cn("shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold", PILL[status.tone])}>{status.word}</span>}
      </button>
    </li>
  )
}

function Decisions({ caseId, extraction, label, profile, canEdit, clockWords }: { caseId: string; extraction: string; label: string; profile: Profile; canEdit: boolean; clockWords?: string }) {
  const needs = profile.needs
  return (
    <section aria-label={`${label} decisions`} className="flex flex-[1_1_420px] flex-col gap-1 rounded-xl border bg-card p-[18px]">
      <h2 className="mb-2 text-[15px] font-semibold">{settleTitle(label, needs.length)}</h2>
      {needs.length === 0 && <p className="text-[13px] text-muted-foreground">Nothing on this phone needs a decision. The settings below can still be changed, each with a reason.</p>}
      {needs.map((n) => (
        <div key={n.kind} className="flex items-start gap-3 border-t py-3">
          <div className="flex-1">
            <p className="text-sm font-semibold">{needTitle(n.kind)}</p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{n.words}</p>
          </div>
          {NEED_ANCHOR[n.kind] && canEdit && (
            <Button variant="outline" onClick={() => go(NEED_ANCHOR[n.kind])}>{NEED_ACTION[n.kind]}</Button>
          )}
        </div>
      ))}
      {clockWords && (
        <div className="flex items-start gap-3 border-t py-3">
          <div className="flex-1">
            <p className="text-sm font-semibold">Is the clock right?</p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{clockWords}</p>
          </div>
          {canEdit && <Button variant="outline" onClick={() => go("set-clock")}>Add an offset</Button>}
        </div>
      )}
      <details className="border-t pt-2 text-[13px]" open={canEdit}>
        <summary className="cursor-pointer py-1 font-medium">Settings for {label}</summary>
        <div className="text-[13px] [&_.text-xs]:text-[12px]">
          <PhoneSetup caseId={caseId} extraction={extraction} />
          {canEdit && <SetOwner caseId={caseId} extraction={extraction} owner={profile.owner} />}
        </div>
      </details>
    </section>
  )
}

export default function SetupPage() {
  const { id: caseId = "" } = useParams()
  const [params, setParams] = useSearchParams()
  const kase = useCase(caseId)
  const canEdit = !!kase.data?.user_role && EDIT_ROLES.includes(kase.data.user_role)
  const phones = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  const list = useMemo(() => (phones.data?.phones ?? []).map((p, index) => ({ p, index })).filter(({ p }) => p.standing !== "superseded"), [phones.data])
  const profiles = useQueries({ queries: list.map(({ p }) => ({ ...phoneProfileQuery(caseId, p.extraction_id), enabled: !!caseId })) })
  const readings = useQuery({ queryKey: ["phone-readings", caseId], queryFn: () => readingsAPI.list(caseId), enabled: !!caseId })
  const jobs = useJobs(caseId, true)
  const reading = (jobs.data ?? []).filter((j) => j.job_type === "phone_capture" && j.status !== "completed")
  const items = readings.data?.items ?? []
  const byPhone = (ext: string) => items.filter((r) => r.extraction_id === ext)
  const firstToSettle = list.findIndex((_, i) => (profiles[i]?.data?.needs.length ?? 0) > 0)
  // a link from a record names one reading (?reading=<id>): open its phone on it
  const linked = items.find((r) => r.id === params.get("reading"))
  const chosenId = params.get("phone") ?? linked?.extraction_id ?? list[Math.max(0, firstToSettle)]?.p.extraction_id
  const ci = list.findIndex(({ p }) => p.extraction_id === chosenId)
  const chosen = ci >= 0 ? list[ci] : undefined
  const chosenProfile = ci >= 0 ? profiles[ci]?.data : undefined
  const setup = useQuery({
    queryKey: ["phone-setup", caseId, chosen?.p.extraction_id],
    queryFn: () => import("../api").then((m) => m.getPhoneSetup(caseId, chosen!.p.extraction_id)),
    enabled: !!chosen,
  })
  const clockWords = setup.data
    ? setup.data.clock.periods.length === 0
      ? "No offset has been recorded. Times are as the phone's clock gave them."
      : `${setup.data.clock.periods.length} clock ${setup.data.clock.periods.length === 1 ? "offset is" : "offsets are"} recorded, each by decision. See the settings below.`
    : undefined
  const identity = params.get("decision") === "link_phone_identity" ? params.get("identity") : null
  const people = params.get("panel") === "people"
  useEffect(() => { document.title = "Set up the phones · Loupe" }, [])
  const choose = (ext: string) => setParams((p) => { const n = new URLSearchParams(p); n.set("phone", ext); return n }, { replace: true })
  const base = `/cases/${encodeURIComponent(caseId)}`
  return (
    <div className="flex h-full flex-col gap-5 overflow-auto px-4 py-6 text-foreground sm:px-8">
      <div>
        <nav aria-label="Breadcrumb" className="text-xs text-muted-foreground"><Link className="underline-offset-2 hover:underline" to={`${base}/phones`}>Phones</Link> / Set up</nav>
        <h1 className="mt-1 text-2xl font-bold">Setting up the phones</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">
          {canEdit
            ? "Done once per phone by whoever owns the case. Investigators reading the phones never land here; a phone's records carry a plain mark until its readings are checked."
            : "You can view this case. Whoever owns the case or edits it settles these; until a phone's readings are checked, its records carry a plain mark."}
        </p>
      </div>
      {phones.isError && <p role="alert" className="text-[13px]">The phones of this case could not be loaded. <Button size="sm" variant="outline" onClick={() => void phones.refetch()}>Try again</Button></p>}
      {readings.isError && <p role="alert" className="text-[13px]">The readings of this case could not be loaded, so the reading checks are not shown. <Button size="sm" variant="outline" onClick={() => void readings.refetch()}>Try again</Button></p>}
      <div className="flex flex-wrap gap-4">
        <section aria-label="Phones in this case" className="flex flex-[1_1_420px] flex-col gap-1 rounded-xl border bg-card p-[18px]">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-[15px] font-semibold">Phones in this case</h2>
            {canEdit && <Button asChild><Link to={`${base}/evidence`}>Add a phone report</Link></Button>}
          </div>
          {phones.isLoading && <p role="status" className="text-[13px]">Loading the phones.</p>}
          {phones.data && list.length === 0 && <p className="text-[13px] text-muted-foreground">This case has no phone yet. Add a phone report from the evidence page; it shows here while it is read.</p>}
          <ul>
            {list.map(({ p, index }, i) => (
              <PhoneRow key={p.extraction_id} label={p.label} index={index} owner={p.owner?.name ?? null} profile={profiles[i]?.data}
                readings={byPhone(p.extraction_id)} chosen={p.extraction_id === chosen?.p.extraction_id} onChoose={() => choose(p.extraction_id)} />
            ))}
          </ul>
          {reading.length > 0 && (
            <div className="mt-2 flex flex-col gap-2 border-t pt-3">
              <h3 className="text-sm font-semibold">Reports being read</h3>
              {reading.map((j) => <PhoneReadinessCard key={j.id} job={j} />)}
            </div>
          )}
        </section>
        {chosen && chosenProfile && (
          <Decisions caseId={caseId} extraction={chosen.p.extraction_id} label={chosen.p.label} profile={chosenProfile} canEdit={canEdit} clockWords={clockWords} />
        )}
      </div>
      {chosen && canEdit && readings.data && (
        <ReadingCheck caseId={caseId} extraction={chosen.p.extraction_id} label={chosen.p.label} items={items} initial={linked?.id} zone={phones.data?.case_zone.name ?? "UTC"} />
      )}
      {chosen && !canEdit && readings.data && (
        <section aria-label={`Readings of ${chosen.p.label}`} className="rounded-xl border bg-card p-5 text-[13px]">
          <h2 className="text-[15px] font-semibold">How the system read {chosen.p.label}</h2>
          <p className="mt-1">{readingsMark(byPhone(chosen.p.extraction_id)).words}</p>
        </section>
      )}
      {canEdit && (
        <section aria-label="People and re-checks" className="flex flex-col gap-3 rounded-xl border bg-card p-5 text-[13px]">
          <nav aria-label="People" className="flex gap-3">
            {people ? <Link className="underline" to={`${base}/phones/set-up`}>Back to the reading checks</Link> : <Link className="underline" to={`${base}/phones/set-up?panel=people`}>People the phones may share</Link>}
          </nav>
          {identity && <IdentityLinkGroup caseId={caseId} identityKey={identity} />}
          {people && <PeopleSuggestions caseId={caseId} />}
          <ReadingRechecks caseId={caseId} />
        </section>
      )}
    </div>
  )
}
