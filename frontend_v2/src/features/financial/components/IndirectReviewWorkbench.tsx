import { useState, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { caseworkAPI } from "@/features/workspace/casework-api"
import { useCreateCaseworkEntry } from "@/features/workspace/hooks/use-casework"
import { correctionMoney } from "../lib/correction-contract"
import {
  indirectMinor,
  indirectCatalog,
  indirectRequest,
  verifyIndirectReview,
  type IndirectRequest,
  type VerifiedIndirectReview,
} from "../lib/indirect-review"

type Field = {
  amount_input: string
  basis: string
  source_file_id: string
  source_location: string
  status: "reviewed" | "unresolved"
}
const empty = (): Field => ({
  amount_input: "",
  basis: "",
  source_file_id: "",
  source_location: "",
  status: "unresolved",
})
export function IndirectReviewWorkbench({ caseId }: { caseId: string }) {
  const [method, setMethod] = useState<IndirectRequest["method"]>("net_worth"),
    [currency, setCurrency] = useState(""),
    [subject, setSubject] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [entries, setEntries] = useState<Record<string, Field>>({}),
    [checks, setChecks] = useState<Record<string, Field>>({}),
    [search, setSearch] = useState(""),
    [sources, setSources] = useState<{ id: string; label: string }[]>([]),
    [source, setSource] = useState<{ id: string; label: string } | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [report, setReport] = useState<VerifiedIndirectReview | null>(null)
  const revision = useRef(0)
  const [drafts, setDrafts] = useState<
    Record<
      string,
      { entries: Record<string, Field>; checks: Record<string, Field> }
    >
  >({})
  const save = useCreateCaseworkEntry(caseId)
  const catalog = useQuery({
    queryKey: ["financial-ledger", caseId, "indirect-methods"],
    retry: false,
    queryFn: async () => {
      const data = indirectCatalog.parse(
        await fetchAPI(
          `/api/financial/indirect-review-methods?case_id=${encodeURIComponent(caseId)}`
        )
      )
      if (data.case_id !== caseId)
        throw Error("Review methods belong to another case.")
      return data
    },
  })
  const selected = catalog.data?.methods.find((m) => m.id === method)
  const changed = () => {
    revision.current += 1
    setReport(null)
    setError("")
    save.reset()
  }
  const update = (key: string, patch: Partial<Field>, review = false) => {
    changed()
    const setter = review ? setChecks : setEntries
    setter((state) => ({
      ...state,
      [key]: { ...(state[key] ?? empty()), ...patch },
    }))
  }
  const loadSources = async () => {
    try {
      setError("")
      const result = await caseworkAPI.attachmentOptions(
        caseId,
        "evidence",
        search,
        20
      )
      setSources((old) => [
        ...new Map(
          [
            ...old,
            ...result.items.map((i) => ({ id: i.target_id, label: i.label })),
          ].map((i) => [i.id, i])
        ).values(),
      ])
      if (!result.items.length)
        setError(
          "No matching files. Add the evidence to this case or refine the search."
        )
    } catch (e) {
      setError(e instanceof Error ? e.message : "Source search failed.")
    }
  }
  const calculate = async () => {
    setBusy(true)
    changed()
    const ticket = revision.current
    try {
      if (!catalog.data || !selected) throw Error("Load the method first.")
      const entryValues = Object.fromEntries(
        selected.terms.map((term) => {
          const field = entries[term.id] ?? empty()
          const amount = field.amount_input.trim()
            ? indirectMinor(field.amount_input, currency, term.signed)
            : null
          if (field.amount_input.trim() && amount === null)
            throw Error(`Enter a valid amount for ${term.label}.`)
          return [
            term.id,
            {
              amount_minor: amount,
              basis: field.basis,
              source_file_id: field.source_file_id || null,
              source_location: field.source_location,
            },
          ]
        })
      )
      const requirements = Object.fromEntries(
        catalog.data.requirements.map((check) => {
          const field = checks[check.id] ?? empty()
          return [
            check.id,
            {
              status: field.status,
              basis: field.basis,
              source_file_id: field.source_file_id || null,
              source_location: field.source_location,
            },
          ]
        })
      )
      const request = indirectRequest.parse({
        method,
        currency,
        subject,
        start_date: start,
        end_date: end,
        entries: entryValues,
        requirements,
      })
      const answer = await fetchAPI(
        `/api/financial/indirect-review?case_id=${encodeURIComponent(caseId)}`,
        { method: "POST", body: request }
      )
      const verified = await verifyIndirectReview(answer, catalog.data, request)
      if (revision.current === ticket) setReport(verified)
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Workpaper could not be calculated."
      )
    } finally {
      setBusy(false)
    }
  }
  const download = () => {
    if (!report) return
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report.envelope, null, 2)], {
        type: "application/json",
      })
    )
    const a = document.createElement("a")
    a.href = url
    a.download = `loupe-${method}-workpaper.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  const restore = async (file: File | undefined) => {
    if (!file || !catalog.data) return
    changed()
    const ticket = revision.current
    try {
      if (file.size > 1024 * 1024) throw Error("Workpaper file exceeds1MiB.")
      const envelope = JSON.parse(await file.text())
      const request = indirectRequest.parse(
        JSON.parse(envelope.scenario_json).inputs
      )
      const captured = await verifyIndirectReview(
        envelope,
        catalog.data,
        request
      )
      if (revision.current !== ticket) return
      setMethod(request.method)
      setCurrency(request.currency)
      setSubject(request.subject)
      setStart(request.start_date)
      setEnd(request.end_date)
      setEntries(
        Object.fromEntries(
          Object.entries(request.entries).map(([key, value]) => [
            key,
            {
              ...empty(),
              ...value,
              source_file_id: value.source_file_id ?? "",
              amount_input:
                value.amount_minor === null
                  ? ""
                  : correctionMoney(
                      value.amount_minor,
                      request.currency
                    ).replace(` ${request.currency}`, ""),
            },
          ])
        )
      )
      setChecks(
        Object.fromEntries(
          Object.entries(request.requirements).map(([key, value]) => [
            key,
            {
              ...empty(),
              ...value,
              source_file_id: value.source_file_id ?? "",
            },
          ])
        )
      )
      setSources(
        captured.value.sources.map((s) => ({ id: s.id, label: s.filename }))
      )
      setReport(captured)
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Workpaper could not be restored."
      )
    }
  }
  const saveNote = () => {
    if (!report) return
    const value = report.value
    save.mutate({
      entry_type: "note",
      title: `${value.method_label} workpaper — ${value.inputs.subject}`.slice(
        0,
        255
      ),
      body: [
        `Conditional ${value.method_label} review: ${value.inputs.subject}.`,
        `${value.inputs.start_date} to ${value.inputs.end_date}; ${value.inputs.currency}.`,
        value.difference_minor === null
          ? `Incomplete: ${value.missing.map((m) => m.label).join("; ")}`
          : `Conditional difference: ${correctionMoney(value.difference_minor, value.inputs.currency)}.`,
        ...value.lines.map(
          (line) =>
            `${line.label}: ${line.amount_minor === null ? "Unknown" : correctionMoney(line.amount_minor, value.inputs.currency)}. Basis: ${line.basis}. Source location: ${line.source_location}.`
        ),
        value.limitation,
        `Capture: ${report.envelope.scenario_sha256}.`,
      ].join("\n\n"),
      tags: ["financial", "indirect-review", value.inputs.method],
      links: value.sources.map((s, i) => ({
        target_type: "evidence",
        target_id: s.id,
        target_label: s.filename,
        relationship: "context",
        source_anchor: { workpaper_sha256: report.envelope.scenario_sha256 },
        metadata:
          i === 0
            ? {
                schema: "loupe.financial.indirect_workpaper/1",
                envelope: report.envelope,
              }
            : { workpaper_sha256: report.envelope.scenario_sha256 },
      })),
    })
  }
  const sourceFields = (key: string, field: Field, review: boolean) => (
    <>
      <label className="block">
        Supporting case file
        <select
          aria-label={`${review ? "Review" : "Amount"} source ${key}`}
          className="block w-full border bg-background p-2"
          value={field.source_file_id}
          onChange={(e) =>
            update(key, { source_file_id: e.target.value }, review)
          }
        >
          <option value="">Choose a source</option>
          {sources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      {field.source_file_id && (
        <Button
          type="button"
          variant="outline"
          aria-label={`Inspect ${review ? "review" : "amount"} source ${key}`}
          onClick={() =>
            setSource(
              sources.find((s) => s.id === field.source_file_id) ?? null
            )
          }
        >
          Inspect source
        </Button>
      )}
      <label className="block">
        Page, section or source location
        <input
          aria-label={`${review ? "Review" : "Amount"} location ${key}`}
          maxLength={1024}
          className="block w-full border bg-background p-2"
          value={field.source_location}
          onChange={(e) =>
            update(key, { source_location: e.target.value }, review)
          }
        />
      </label>
      <label className="block">
        Basis and work performed
        <textarea
          aria-label={`${review ? "Review" : "Amount"} basis ${key}`}
          maxLength={4096}
          className="block w-full border bg-background p-2"
          value={field.basis}
          onChange={(e) => update(key, { basis: e.target.value }, review)}
        />
      </label>
    </>
  )
  return (
    <section className="space-y-4 p-4" aria-label="Indirect financial review">
      <h2 className="font-semibold">Indirect financial review</h2>
      <p>
        Build a source-referenced workpaper when direct records leave gaps.
        Enter assessed amounts and explain the work behind them. Unknown values
        stay unknown; a completed form is not an independently verified finding.
      </p>
      {catalog.isPending && <p>Loading review methods…</p>}
      {catalog.error && <p role="alert">{catalog.error.message}</p>}
      {catalog.data && selected && (
        <>
          <fieldset
            disabled={busy || save.isPending}
            className="space-y-3 rounded border p-3"
          >
            <legend>1. Define this review</legend>
            <label className="block">
              Method
              <select
                aria-label="Indirect method"
                className="ml-2 border bg-background p-2"
                value={method}
                onChange={(e) => {
                  changed()
                  setDrafts({ ...drafts, [method]: { entries, checks } })
                  const next = e.target.value as IndirectRequest["method"]
                  setMethod(next)
                  setEntries(drafts[next]?.entries ?? {})
                  setChecks(drafts[next]?.checks ?? {})
                }}
              >
                {catalog.data.methods.map((m) => (
                  <option value={m.id} key={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            <p>
              <a
                className="underline"
                href={catalog.data.reference}
                target="_blank"
                rel="noreferrer"
              >
                Method reference: IRS manual {selected.reference_section}
              </a>
              . Record the applicable accounting and legal basis below; no
              deductions or exemptions are supplied automatically.
            </p>
            <div className="grid gap-3 md:grid-cols-3">
              <label>
                Subject
                <input
                  aria-label="Indirect subject"
                  maxLength={512}
                  className="block w-full border bg-background p-2"
                  value={subject}
                  onChange={(e) => {
                    changed()
                    setSubject(e.target.value)
                  }}
                />
              </label>
              <label>
                Currency
                <input
                  aria-label="Indirect currency"
                  placeholder="GBP"
                  maxLength={3}
                  className="block w-full border bg-background p-2"
                  value={currency}
                  onChange={(e) => {
                    changed()
                    setCurrency(e.target.value.toUpperCase())
                  }}
                />
              </label>
              <label>
                From
                <input
                  aria-label="Indirect from"
                  type="date"
                  className="block border bg-background p-2"
                  value={start}
                  onChange={(e) => {
                    changed()
                    setStart(e.target.value)
                  }}
                />
              </label>
              <label>
                Through
                <input
                  aria-label="Indirect through"
                  type="date"
                  className="block border bg-background p-2"
                  value={end}
                  onChange={(e) => {
                    changed()
                    setEnd(e.target.value)
                  }}
                />
              </label>
            </div>
          </fieldset>
          <div className="space-y-2 rounded border p-3">
            <label>
              Find supporting case files
              <input
                aria-label="Find indirect sources"
                className="ml-2 border bg-background p-2"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <Button variant="outline" onClick={() => void loadSources()}>
              Search indirect sources
            </Button>
            <p>
              {sources.length} files available in the source selectors. Search
              returns up to20 matches; refine it for other files.
            </p>
          </div>
          <fieldset
            disabled={busy || save.isPending}
            className="space-y-3 rounded border p-3"
          >
            <legend>2. Enter source amounts</legend>
            <p>
              Use currency units. Enter an explicit zero with its basis where
              appropriate. Source locations are your recorded references;
              amounts are not automatically extracted or classified.
            </p>
            {selected.terms.map((term) => {
              const field = entries[term.id] ?? empty()
              return (
                <details key={term.id} className="rounded border p-3">
                  <summary>
                    {term.sign === 1 ? "Add" : "Subtract"}: {term.label} ·{" "}
                    {field.amount_input || "Unknown"}
                  </summary>
                  <div className="space-y-2 pt-2">
                    <label>
                      Amount ({currency || "choose currency"})
                      <input
                        aria-label={`Indirect amount ${term.id}`}
                        inputMode="decimal"
                        className="block w-full border bg-background p-2"
                        value={field.amount_input}
                        onChange={(e) =>
                          update(term.id, { amount_input: e.target.value })
                        }
                      />
                    </label>
                    {sourceFields(term.id, field, false)}
                  </div>
                </details>
              )
            })}
          </fieldset>
          <fieldset
            disabled={busy || save.isPending}
            className="space-y-3 rounded border p-3"
          >
            <legend>3. Record the required review</legend>
            {catalog.data.requirements.map((check) => {
              const field = checks[check.id] ?? empty()
              return (
                <details key={check.id} className="rounded border p-3">
                  <summary>
                    {check.label} · {field.status}
                  </summary>
                  <div className="space-y-2 pt-2">
                    <label>
                      <input
                        aria-label={`Indirect reviewed ${check.id}`}
                        type="checkbox"
                        checked={field.status === "reviewed"}
                        onChange={(e) =>
                          update(
                            check.id,
                            {
                              status: e.target.checked
                                ? "reviewed"
                                : "unresolved",
                            },
                            true
                          )
                        }
                      />{" "}
                      I have recorded this review and its supporting evidence
                    </label>
                    {sourceFields(check.id, field, true)}
                  </div>
                </details>
              )
            })}
          </fieldset>
          <Button
            disabled={
              busy ||
              save.isPending ||
              !subject.trim() ||
              !currency ||
              !start ||
              !end
            }
            onClick={() => void calculate()}
          >
            {busy ? "Calculating…" : "Calculate indirect workpaper"}
          </Button>
          <label className="block">
            Restore a downloaded workpaper
            <input
              type="file"
              className="mt-2 block max-w-full"
              accept="application/json,.json"
              aria-label="Restore indirect workpaper"
              disabled={busy || save.isPending}
              onChange={(e) => void restore(e.target.files?.[0])}
            />
          </label>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      {report && (
        <section
          className="space-y-3 rounded border p-3"
          aria-label="Indirect workpaper result"
        >
          <h3 className="font-semibold">
            {report.value.method_label} workpaper
          </h3>
          <p>
            {report.value.difference_minor === null
              ? "Result withheld: required amounts or review steps are incomplete."
              : `Conditional difference: ${correctionMoney(report.value.difference_minor, report.value.inputs.currency)}`}
          </p>
          <ul>
            {report.value.missing.map((m) => (
              <li key={`${m.kind}-${m.id}`}>{m.label}</li>
            ))}
          </ul>
          <p>{report.value.limitation}</p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={download}>
              Download indirect workpaper
            </Button>
            <Button
              disabled={
                !report.value.sources.length ||
                save.isPending ||
                save.isError ||
                !!save.data
              }
              onClick={saveNote}
            >
              Save workpaper in Workspace
            </Button>
          </div>
          {save.data && (
            <p role="status">
              Workpaper saved with source references.{" "}
              <a className="underline" href={`/cases/${caseId}/workspace`}>
                Open Workspace
              </a>
            </p>
          )}
          {save.error && (
            <p role="alert">
              {save.error.message} Check Workspace before retrying.
            </p>
          )}
        </section>
      )}
      {source && (
        <DocumentViewer
          caseId={caseId}
          evidenceId={source.id}
          open
          onOpenChange={(open) => !open && setSource(null)}
          documentUrl={evidenceAPI.getFileUrl(source.id)}
          documentName={source.label}
        />
      )}
    </section>
  )
}
