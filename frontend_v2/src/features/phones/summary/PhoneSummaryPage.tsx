import { useQuery } from "@tanstack/react-query"
import { ReviewCoverage } from "./ReviewCoverage"
import { Link, useParams } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { CopyButton } from "@/components/ui/copy-button"
import { profileText } from "../lib/profile-text"
import { failureText } from "../api"
import { phoneProfileQuery } from "../phone-queries"
import { labelText } from "../lib/labels"
import { useCase } from "@/features/cases/hooks/use-cases"
import { useCasePermissions } from "@/features/cases/hooks/use-case-permissions"
import { ContinueReading } from "../ContinueReading"
import { NONE } from "../media/media-queries"
import { recordListHref } from "../records/record-list-url"
import { liveCollectClient, undoCollect } from "../collect.api"
import { useCollectTargets } from "../hooks/use-collect"
import { AddToMenu } from "../ui/AddToMenu"
import { EMPTY_SCOPE } from "../ui/scope"
import { ScopeCrossings } from "../ui/ScopeCrossings"
import { TypedDossierAdd } from "../ui/TypedDossierAdd"
import { fmt } from "../ui/count-sentence"
import { NamePhone } from "./NamePhone"
import { SetOwner } from "./SetOwner"
import { HeldDifference } from "./HeldDifference"
import { PhoneSetup } from "./PhoneSetup"
import { ExportHistory, ExportProfile, SinceYouLastLooked } from "./SummaryExtras"
import { flagKindWords, flagSubjectWords, type FlagSubject } from "@/features/admin/phone-registry"
import type { Profile } from "../schemas"
import { FirstPhoneCard } from "./FirstPhoneCard"

/**
 * Phone summary (03 section 7; 07 J-2, J-11, J-15): the verdict, what needs a decision, the triage block (coverage
 * by month, top people, apps, deleted and missing), where to start and continue reading, then whose phone it is,
 * the device and report, what the production says it holds, whether it arrived whole, files, deleted and
 * recovered, what Loupe reads, and when there is data. Every number comes from the server's count and links to
 * the list it counts.
 */

const MONTH = new Intl.DateTimeFormat("en-US", { month: "short", year: "numeric", timeZone: "UTC" })
const monthWords = (m: string) => MONTH.format(new Date(`${m}-15T00:00:00Z`))


function Section({ name, children, className }: { name: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={name} className={className ?? "rounded border bg-card p-3 text-sm"}>
      <h2 className="mb-2 text-sm font-semibold">{name}</h2>
      {children}
    </section>
  )
}

export function PhoneSummaryPage() {
  const { id: caseId = "", extraction = "" } = useParams()
  const q = useQuery({ ...phoneProfileQuery(caseId, extraction), enabled: !!caseId && !!extraction })
  const caseQuery = useCase(caseId)
  const { canEdit } = useCasePermissions(caseQuery.data)
  const collect = useCollectTargets(caseId)
  if (q.isLoading) return <p className="p-6 text-sm">Loading the phone summary</p>
  if (q.isError || !q.data)
    return (
      <div role="alert" className="p-6 text-sm">
        <p>{failureText(q.error, "The phone summary could not be loaded.")}</p>
        <Button size="sm" variant="outline" className="mt-2" onClick={() => void q.refetch()}>
          Try again
        </Button>
      </div>
    )
  const p = q.data
  const conv = p.links.conversations
  const maxMonth = Math.max(1, ...p.months.map((m) => m.messages + m.calls + m.other))
  const soFar = p.verdict.word === "Still reading" ? " (so far)" : ""
  const missing = p.files.verification.missing ?? 0
  const notAllowed = canEdit ? undefined : "A case member who can edit can add."
  const targets = collect.data ?? []
  // a phone reaches a dossier as a device dossier, an identity through a link decision (07 6.1); both go to the rest
  const notDossiers = targets.filter((t) => t.kind !== "dossier")
  const ownerKey = p.owner.label?.identity_key
  return (
    <div className="flex flex-col gap-3 p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold">Phone summary: {p.phone.label}</h1>
        <span className="ml-auto flex gap-2">
          <CopyButton rows={1} noun="profile" label="Copy profile as text" build={() => ({ text: profileText(p) })} />
          <ExportProfile caseId={caseId} extraction={extraction} label={p.phone.label} />
          <Button asChild size="sm" variant="outline">
            <Link to={conv}>Conversations</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/media`}>Media</Link>
          </Button>
        </span>
      </header>
      <FirstPhoneCard caseId={caseId} />
      <p className="text-sm font-medium">
        {p.verdict.sentence}
        {soFar}
      </p>
      <div aria-label="Add this phone" className="flex flex-wrap items-start gap-2">
        <AddToMenu caseId={caseId} links={[{ target_type: "phone_extraction", target_id: extraction, label: p.phone.label, source_anchor: { extraction_id: extraction } }]}
          noun="phones" targets={notDossiers} client={liveCollectClient} origin="Added from the Phone summary" keys={false} disabledReason={notAllowed}
          onUndo={(t, r) => void undoCollect(caseId, t, r)} />
        <TypedDossierAdd caseId={caseId} type="device" suggestedName={p.phone.label} origin="Added from the Phone summary" disabledReason={notAllowed}
          link={{ target_type: "phone_extraction", target_id: extraction, label: p.phone.label, source_anchor: { extraction_id: extraction } }} />
        {ownerKey && (
          <Button asChild size="sm" variant="outline">
            <Link to={`/cases/${encodeURIComponent(caseId)}/dossiers?tab=phone-identities&identity=${encodeURIComponent(ownerKey)}`}>Link the owner to a person</Link>
          </Button>
        )}
        <ScopeCrossings caseId={caseId} here="summary" scope={{ ...EMPTY_SCOPE, phones: [{ id: extraction, label: p.phone.label, index: 0 }] }} />
      </div>

      <Section name="Needs a decision" className="rounded border border-status-review bg-status-review-soft p-3 text-sm">
        {p.needs.length === 0 ? (
          <p>Nothing needs a decision on this phone.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {p.needs.map((n) => (
              <li key={n.kind}>
                {n.kind === "owner" ? (
                  <>
                    No owner number was found. Person-level views stay off until an owner is set.{" "}
                    <button
                      type="button"
                      className="underline underline-offset-2"
                      onClick={() => {
                        document.getElementById("set-owner")?.scrollIntoView({ block: "center" })
                        document.getElementById("set-owner-number")?.focus()
                      }}
                    >
                      Set the owner.
                    </button>
                  </>
                ) : n.kind === "reconciliation" ? (
                  <HeldDifference caseId={caseId} extraction={extraction} words={n.words} held={p.completeness.held} />
                ) : (
                  <>
                    {n.words}{" "}
                    {n.link && (
                      <Link className="underline underline-offset-2" to={n.link}>
                        {n.kind === "zone" || n.kind === "offsetless" ? "Decide" : "Open"}
                      </Link>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
        <PhoneSetup caseId={caseId} extraction={extraction} />
      </Section>

      <div className="grid gap-3 md:grid-cols-2">
        <Section name="Coverage by month">
          {p.months.length === 0 ? (
            <p>No dated messages or calls on this phone.</p>
          ) : (
            <ul className="flex flex-col gap-0.5" aria-label="Messages and calls by month">
              {p.months.map((m) => {
                const n = m.messages + m.calls + m.other
                return (
                  <li key={m.month} className="flex items-center gap-2 text-xs">
                    <span className="w-20 shrink-0">{monthWords(m.month)}</span>
                    <span aria-hidden className="h-2 rounded-sm bg-status-info" style={{ width: `${Math.max(n ? 2 : 0, (n / maxMonth) * 100)}%` }} />
                    {n && m.link ? (
                      <Link className="underline underline-offset-2" to={m.link}>
                        {fmt(m.messages)} messages, {fmt(m.calls)} calls
                      </Link>
                    ) : (
                      <span>{n ? `${fmt(m.messages)} messages, ${fmt(m.calls)} calls` : "none"}</span>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </Section>
        <section aria-label="Top people" className="rounded border bg-card p-3 text-sm">
          <h2 className="mb-2 text-sm font-semibold">Top people by contact</h2>
          {p.top_people.length === 0 ? (
            <p>No other people take part in this phone's messages or calls.</p>
          ) : (
            <ol className="flex flex-col gap-0.5">
              {p.top_people.map((t) => (
                <li key={t.text} className="flex flex-wrap items-center gap-2">
                  {t.link ? (
                    <Link className="underline underline-offset-2" to={t.link}>
                      {t.text}: {fmt(t.events)} messages and calls
                    </Link>
                  ) : (
                    `${t.text}: ${fmt(t.events)} messages and calls`
                  )}
                  {t.label.identity_key && (
                    <AddToMenu caseId={caseId} links={[{ target_type: "phone_identity", target_id: t.label.identity_key, label: t.text, source_anchor: { extraction_id: extraction } }]}
                      noun="people" targets={notDossiers} client={liveCollectClient} origin="Added from the Phone summary" keys={false} disabledReason={notAllowed}
                      onUndo={(u, r) => void undoCollect(caseId, u, r)} />
                  )}
                </li>
              ))}
            </ol>
          )}
        </section>
        <Section name="Apps">
          <ul className="flex flex-col gap-0.5">
            {p.apps.map((a) => (
              <li key={a.app}>
                <Link className="underline underline-offset-2" to={`${conv}?apps=${encodeURIComponent(a.app)}`}>
                  {a.app}: {fmt(a.events)}
                </Link>
              </li>
            ))}
            {p.apps.length === 0 && <li>No app recorded on any message or call.</li>}
          </ul>
        </Section>
        <Section name="Busiest weeks">
          {p.busiest_weeks.length === 0 ? (
            <p>No dated messages or calls on this phone.</p>
          ) : (
            <ol className="flex flex-col gap-0.5">
              {p.busiest_weeks.map((w) => (
                <li key={w.week}>
                  <Link className="underline underline-offset-2" to={w.link}>
                    {w.words}: {fmt(w.events)} messages and calls
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </Section>
        <Section name="Deleted, recovered and missing">
          <ul className="flex flex-col gap-0.5">
            <li>
              <Link className="underline underline-offset-2" to={p.deleted.link}>
                {fmt(p.deleted.comm_events)} deleted or in trash
              </Link>{" "}
              (messages and calls)
            </li>
            {p.deleted.by_type.map((d) => (
              <li key={d.model_type}>
                <Link className="underline underline-offset-2" to={recordListHref(caseId, extraction, d.model_type, { placement: "top", deleted: "only" })}>
                  {d.model_type}: {fmt(d.deleted + d.trash)} deleted or in trash
                </Link>
              </li>
            ))}
            <li>
              <Link className="underline underline-offset-2" to={`${p.files.link}?verification=missing`}>
                {fmt(missing)} {missing === 1 ? "file" : "files"} missing
              </Link>
            </li>
          </ul>
        </Section>
      </div>

      <Section name="Where to start">
        <p className="mb-1 text-xs text-muted-foreground">Suggestions worked out from the counts on this page.</p>
        <ul className="flex flex-col gap-0.5">
          {p.where_to_start.map((w) => (
            <li key={w.words}>{w.link ? <Link className="underline underline-offset-2" to={w.link}>{w.words}</Link> : w.words}</li>
          ))}
          {p.where_to_start.length === 0 && <li>No suggestion: nothing on this phone stands out by count.</li>}
        </ul>
      </Section>
      <Section name="Continue reading">
        <ContinueReading caseId={caseId} extraction={extraction} empty={(
          <p>
            Nothing opened yet on this browser, and no assigned review with a saved position.{" "}
            <Link className="underline underline-offset-2" to={conv}>
              Open Conversations
            </Link>
          </p>
        )} />
      </Section>

      <div className="grid gap-3 md:grid-cols-2">
        <Section name="Since you last looked">
          {/* keyed by phone: moving to another phone reads that phone's own last visit */}
          <SinceYouLastLooked key={`${caseId}:${extraction}`} caseId={caseId} extraction={extraction} />
        </Section>
        <Section name="Export history">
          <ExportHistory caseId={caseId} extraction={extraction} />
        </Section>
      </div>
      <Section name="Review coverage">
        <ReviewCoverage caseId={caseId} extraction={extraction} />
      </Section>
      <Section name="Whose phone">
        <p>{p.owner.label && !p.owner.missing ? labelText(p.owner.label) : "No owner number was found."}</p>
        <p className="text-xs text-muted-foreground">{p.owner.missing ? "Person-level views stay off until an owner is set." : p.owner.words}</p>
        <SetOwner caseId={caseId} extraction={extraction} owner={p.owner} />
        <NamePhone caseId={caseId} extraction={extraction} label={p.phone.label} />
        {p.zone.device_zone ? (
          <p className="text-xs">{p.zone.basis === "decided" ? "Time zone set by decision" : "Time zone recorded by the phone"}: {p.zone.device_zone}</p>
        ) : (
          <p className="text-xs">This phone did not record its time zone. Times show in the case zone ({p.zone.case_zone}).</p>
        )}
      </Section>
      <Section name="Device and report">
        <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 text-xs">
          <dt>Device</dt>
          <dd>{[p.phone.device.manufacturer, p.phone.device.model, p.phone.device.os].filter(Boolean).join(", ") || "not recorded"}</dd>
          <dt>Report file</dt>
          <dd className="break-all">{p.report.filename ?? "not recorded"}</dd>
          <dt>Form and version</dt>
          <dd>{[p.report.form, p.report.report_version].filter(Boolean).join(", ") || "not recorded"}</dd>
          <dt>Producer</dt>
          <dd>{p.report.producer ?? "not recorded"}</dd>
          <dt>Extraction type</dt>
          <dd>{p.report.extraction_type ?? "not recorded"}</dd>
          <dt>SHA-256 received</dt>
          <dd className="break-all">{p.report.container_sha256 ?? "not recorded"}</dd>
        </dl>
      </Section>
      <Section name="What the production says it contains">
        <ul className="flex flex-col gap-1">
          {p.selection.map((s) => (
            <li key={s.flag}>
              {s.name}: <span className="font-mono text-xs">{s.verbatim}</span>
              {s.meaning ? `. ${s.meaning}` : ""}
            </li>
          ))}
        </ul>
      </Section>
      <Section name="Did it arrive whole">
        <p>
          {p.completeness.reconciliation === "exact"
            ? "Every part of the report matches its own counts."
            : p.completeness.reconciliation === "failed"
              ? "Part of the report does not match its own counts."
              : "The report's counts have not been checked yet."}
        </p>
        {p.completeness.held
          .filter((h) => h.accepted)
          .map((h) => (
            <p key={`acc-${h.document_index}`} className="text-xs">
              {fmt(h.difference_count)} {h.difference_count === 1 ? "difference" : "differences"} in {h.document ?? `document ${h.document_index + 1}`} accepted
              {h.accepted?.by ? ` by ${h.accepted.by}` : ""}
              {h.accepted?.at ? ` on ${h.accepted.at.slice(0, 10)}` : ""}: {h.accepted?.reason ?? ""}
            </p>
          ))}
        {p.completeness.documents.flatMap((d) =>
          d.stated_vs_read.map((x) => (
            <p key={`${d.document_index}-${x.what}`} className="text-xs">
              {x.words ?? `${x.what}: the report states ${typeof x.stated === "number" ? fmt(x.stated) : "nothing"}, ${typeof x.read === "number" ? fmt(x.read) : "none"} read`}
            </p>
          )),
        )}
      </Section>
      <Section name="Files">
        <p>
          <Link className="underline" to={`/cases/${encodeURIComponent(caseId)}/phones/${encodeURIComponent(extraction)}/records/media`}>
            {fmt(p.files.total)} files
          </Link>
          {soFar}
        </p>
        <ul className="text-xs">
          {Object.entries(p.files.verification).map(([k, v]) => (
            <li key={k}>
              <Link className="underline underline-offset-2" to={`${p.files.link}?verification=${encodeURIComponent(k === "not checked" ? NONE : k)}`}>
                {k.replace(/_/g, " ")}: {fmt(v)}
              </Link>
            </li>
          ))}
        </ul>
      </Section>
      <Section name="What Loupe reads">
        <table className="text-xs">
          <thead>
            <tr>
              <th className="pr-3 text-left">Record type</th>
              <th className="pr-3 text-right">Records</th>
              <th className="pr-3 text-right">Inside other records</th>
              <th className="text-left">State</th>
            </tr>
          </thead>
          <tbody>
            {p.coverage.map((c) => (
              <tr key={c.model_type}>
                <td className="pr-3">{c.model_type}</td>
                <td className="pr-3 text-right">
                  {c.records > 0 ? (
                    <Link className="underline underline-offset-2" aria-label={`${fmt(c.records)} ${c.model_type} records`} to={recordListHref(caseId, extraction, c.model_type, { placement: "top" })}>
                      {fmt(c.records)}
                    </Link>
                  ) : (
                    "0"
                  )}
                </td>
                <td className="pr-3 text-right">
                  {c.nested > 0 ? (
                    <Link className="underline underline-offset-2" aria-label={`${fmt(c.nested)} ${c.model_type} records inside other records`} to={recordListHref(caseId, extraction, c.model_type, { placement: "nested" })}>
                      {fmt(c.nested)}
                    </Link>
                  ) : (
                    "0"
                  )}
                  {c.copies > 0 && (
                    <>
                      {" "}
                      <Link className="underline underline-offset-2" to={recordListHref(caseId, extraction, c.model_type, { copies: "only" })}>
                        ({fmt(c.copies)} {c.copies === 1 ? "copy" : "copies"} from another source)
                      </Link>
                    </>
                  )}
                </td>
                <td>{c.level_words}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <MappingBacklog backlog={p.mapping_backlog} />
      </Section>
      <Section name="When there is data">
        <ul className="text-xs">
          {p.data_periods.map((d) => (
            <li key={d.signal}>
              {d.link ? <Link className="underline underline-offset-2" to={d.link}>{d.signal}: {fmt(d.records)}</Link> : `${d.signal}: ${fmt(d.records)}`}
              {d.listed !== undefined && d.listed !== d.records ? ` (${fmt(d.listed)} rows once copies of one message are folded together)` : ""}
              {d.first_words ? `, ${d.first_words} to ${d.last_words}` : ""}
              {d.records > d.dated ? `; ${fmt(d.records - d.dated)} with no time` : ""}
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}

export default PhoneSummaryPage

/** The mapping backlog for this phone (02 section 3.4): what an administrator marked as waiting for a mapping. Every
 * item is listed with the total; until a mapping is loaded these are kept and searchable but read generically. */
export function MappingBacklog({ backlog }: { backlog: Profile["mapping_backlog"] }) {
  if (!backlog) return null
  if (backlog.total === 0)
    return <p className="mt-2 text-xs text-muted-foreground">Nothing on this phone is waiting for a mapping.</p>
  return (
    <div className="mt-2 text-xs" data-testid="mapping-backlog">
      <p>
        Waiting for a mapping ({backlog.total.toLocaleString()}): kept and searchable, read generically until a
        mapping is added.
      </p>
      <ul className="list-disc pl-4">
        {backlog.items.map((b) => (
          <li key={b.flag_id}>
            {flagKindWords(b.flag_kind)}: {flagSubjectWords({ flag_kind: b.flag_kind, subject: b.subject as FlagSubject, detail: {} })}
          </li>
        ))}
      </ul>
    </div>
  )
}
