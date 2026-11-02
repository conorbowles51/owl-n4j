import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import type { FixtureCase } from "../fixtures"
import { fmt } from "../ui/ResultCount"
import { PhoneChip } from "../ui/PhoneChip"
import { apps, monthBands, phoneMessages, topPeople } from "./proto-data"
import { ShareBar, appTone } from "@/lib/data-colour"
import { cn } from "@/lib/cn"

/** Section groups (lx-style mock2 #18): a top rule and a small label, so related sections read as one group. */
const GROUPS = {
  act: { label: "Act", rule: "border-t-status-warning", text: "text-status-warning border-status-warning" },
  next: { label: "Next step", rule: "border-t-status-info", text: "text-status-info border-status-info" },
  activity: { label: "Activity", rule: "border-t-source-1", text: "text-source-1 border-source-1" },
  people: { label: "People", rule: "border-t-source-3", text: "text-source-3 border-source-3" },
  gaps: { label: "Gaps", rule: "border-t-source-2", text: "text-source-2 border-source-2" },
} as const
type Group = keyof typeof GROUPS
const groupRule = (g: Group) => cn("border-t-[3px]", GROUPS[g].rule)
function GroupLabel({ group }: { group: Group }) {
  return (
    <span aria-hidden data-group={group} className={cn("mr-2 inline-flex rounded-full border px-2 text-[11px] font-bold tracking-[0.02em]", GROUPS[group].text)}>
      {GROUPS[group].label}
    </span>
  )
}

/** Prototype: Phone summary (07 J-2): verdict line, Needs a decision box, triage block, Where to start. */
export function PhoneSummaryProto({
  fx,
  phone,
  base,
  owners,
  setOwner,
}: {
  fx: FixtureCase
  phone: string
  base: string
  owners: Record<string, string | null>
  setOwner: (phone: string, person: string | null) => void
}) {
  const p = fx.phones.find((x) => x.label === phone)!
  const idx = fx.phones.findIndex((x) => x.label === phone)
  const msgs = phoneMessages(fx, phone)
  const timed = msgs.filter((m) => m.time).map((m) => m.time!).sort()
  const appList = apps(fx, phone)
  const owner = owners[phone] ?? p.owner
  const deleted = msgs.filter((m) => m.deleted === "Deleted" || m.deleted === "Trash").length
  const noTime = msgs.length - timed.length
  const decisions = (owner ? 0 : 1) + (p.zone ? 0 : 1) + 1
  const first = timed[0] ? new Date(timed[0]).toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" }) : "no dated records"
  const last = timed.length ? new Date(timed[timed.length - 1]).toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric" }) : ""
  const people = topPeople(fx, phone)
  const bands = monthBands(fx, phone)
  const maxBand = Math.max(1, ...bands.map((b) => b.count))
  const maxMessages = Math.max(1, ...people.map((x) => x.messages))
  const maxCalls = Math.max(1, ...people.map((x) => x.calls))
  const appTotal = appList.reduce((sum, [, n]) => sum + n, 0)
  const conv = (q: string) => `${base}/conversations?phone=${phone}${q}`
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <PhoneChip label={phone} index={idx} extractionDate={p.extraction_date} />
        <span className="text-sm text-muted-foreground">Extracted {new Date(`${p.extraction_date}T12:00:00Z`).toLocaleDateString("en-US", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })}</span>
      </div>
      <p className="text-base font-medium" data-testid="verdict">
        Read in full: {fmt(p.records)} records, {first} to {last}, {appList.length} apps. {decisions} {decisions === 1 ? "thing needs" : "things need"} a decision.
      </p>

      <section aria-labelledby="nad" className={cn("rounded border border-status-review bg-status-review-soft p-3 text-foreground", groupRule("act"))}>
        <h2 id="nad" className="mb-2 text-sm font-semibold"><GroupLabel group="act" />Needs a decision</h2>
        <ul className="flex flex-col gap-2 text-sm">
          {!owner ? (
            <li className="flex flex-wrap items-center gap-2">
              No owner number was found. Person-level views stay off until an owner is set.
              <label className="inline-flex items-center gap-1">
                Set the owner
                <select className="rounded border bg-card px-1 py-0.5" defaultValue="" onChange={(e) => setOwner(phone, e.target.value || null)}>
                  <option value="">Choose a person</option>
                  {fx.people.map((x) => (
                    <option key={x.key} value={x.key}>
                      {x.name}
                    </option>
                  ))}
                </select>
              </label>
            </li>
          ) : (
            <li>
              Owner: {fx.people.find((x) => x.key === owner)?.name ?? "set"}{" "}
              <button type="button" className="underline underline-offset-2" onClick={() => setOwner(phone, null)}>
                Change
              </button>
            </li>
          )}
          {!p.zone && <li>This phone did not record its time zone. Times show in the case zone (Eastern time). <a className="underline underline-offset-2" href="#settings">Change</a></li>}
          <li>
            {fmt(msgs.length)} messages use readings not yet confirmed. <Link className="underline underline-offset-2" to={`${base}/needs-a-decision`}>Check them</Link>
          </li>
        </ul>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="cov" className={cn("rounded border bg-card p-3", groupRule("activity"))}>
          <h2 id="cov" className="mb-2 text-sm font-semibold"><GroupLabel group="activity" />Coverage by month</h2>
          <table className="w-full text-sm">
            <caption className="sr-only">Messages per month, with days that have no data</caption>
            <thead>
              <tr className="text-left text-muted-foreground"><th scope="col" className="font-medium">Month</th><th scope="col" className="font-medium">Messages</th><th scope="col" className="sr-only">Bar</th></tr>
            </thead>
            <tbody>
              {bands.map((b) => (
                <tr key={b.month}>
                  <td className="py-0.5 pr-2">{b.month}</td>
                  <td className="py-0.5 pr-2">
                    <Link className="underline underline-offset-2" to={conv(`&month=${encodeURIComponent(b.month)}`)}>{fmt(b.count)}</Link>
                    {b.noDataDays > 0 && <span className="ml-2 text-status-warning">No data on {b.noDataDays} days</span>}
                  </td>
                  <td className="w-1/2 py-0.5" aria-hidden>
                    <div
                      data-gap={b.noDataDays > 0 ? "" : undefined}
                      className={cn("h-2 rounded", b.noDataDays > 0 ? "bg-status-warning" : "bg-status-info")}
                      style={{
                        width: `${(b.count / maxBand) * 100}%`,
                        backgroundImage:
                          b.noDataDays > 0
                            ? "repeating-linear-gradient(135deg, transparent 0 4px, hsl(var(--card) / 0.45) 4px 7px)"
                            : undefined,
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section aria-labelledby="top" className={cn("rounded border bg-card p-3", groupRule("people"))}>
          <h2 id="top" className="mb-2 text-sm font-semibold"><GroupLabel group="people" />Top {people.length} people by contact</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground"><th scope="col" className="font-medium">Name (number)</th><th scope="col" className="font-medium">Messages</th><th scope="col" className="font-medium">Calls</th></tr>
            </thead>
            <tbody>
              {people.map((x) => (
                <tr key={x.key}>
                  <td className="py-0.5 pr-2">
                    <Link className="underline underline-offset-2" to={conv(`&person=${x.key}`)}>{x.person.name} ({x.person.numbers[0]})</Link>
                  </td>
                  <td className="whitespace-nowrap tabular-nums">{fmt(x.messages)}<ShareBar value={x.messages} max={maxMessages} barClassName="bg-source-1" width="w-14" /></td>
                  <td className="whitespace-nowrap tabular-nums">{fmt(x.calls)}<ShareBar value={x.calls} max={maxCalls} barClassName="bg-source-3" width="w-9" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section aria-labelledby="apps" className={cn("rounded border bg-card p-3 text-sm", groupRule("activity"))}>
          <h2 id="apps" className="mb-2 text-sm font-semibold"><GroupLabel group="activity" />Apps</h2>
          {appTotal > 0 && (
            <div className="mb-2 flex h-2.5 max-w-[520px] overflow-hidden rounded-full" aria-hidden data-testid="apps-share">
              {appList.map(([app, n]) => (
                <span key={app} className={appTone(app).bg} style={{ width: `${(n / appTotal) * 100}%` }} />
              ))}
            </div>
          )}
          <ul>{appList.map(([app, n]) => <li key={app}><span aria-hidden className={cn("mr-2 inline-block size-2.5 rounded-[2px] align-[-1px]", appTone(app).bg)} /><Link className="underline underline-offset-2" to={conv(`&app=${encodeURIComponent(app)}`)}>{app}: {fmt(n)} messages</Link></li>)}</ul>
        </section>

        <section aria-labelledby="del" className={cn("rounded border bg-card p-3 text-sm", groupRule("gaps"))}>
          <h2 id="del" className="mb-2 text-sm font-semibold"><GroupLabel group="gaps" />Deleted, undated and missing</h2>
          <ul>
            <li><Link className="underline underline-offset-2" to={conv("&state=deleted")}>{fmt(deleted)} deleted or in trash</Link></li>
            <li>{fmt(noTime)} messages have no time and are listed at the end of their thread.</li>
            <li>{fmt(p.files)} files in the report.</li>
          </ul>
        </section>
      </div>

      <section aria-labelledby="start" className={cn("rounded border bg-card p-3 text-sm", groupRule("next"))}>
        <h2 id="start" className="mb-1 text-sm font-semibold"><GroupLabel group="next" />Where to start</h2>
        <p className="mb-2 text-muted-foreground">Suggestions worked out from the counts above. They are suggestions, not findings.</p>
        <ul className="flex flex-col gap-1">
          {people[0] && <li><Link className="underline underline-offset-2" to={conv(`&person=${people[0].key}`)}>Read the busiest conversation: {people[0].person.name}, {fmt(people[0].messages)} messages</Link></li>}
          {deleted > 0 && <li><Link className="underline underline-offset-2" to={conv("&state=deleted")}>Look at the {fmt(deleted)} deleted messages</Link></li>}
          {p.no_data_days && <li>Check why there is no data for {p.no_data_days[1] - p.no_data_days[0]} days. No data does not mean no activity.</li>}
        </ul>
      </section>
      <div><Button asChild size="sm"><Link to={conv("")}>Open Conversations</Link></Button></div>
    </div>
  )
}
