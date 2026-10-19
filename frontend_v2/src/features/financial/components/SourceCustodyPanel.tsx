import { useFinancialAccess } from "../hooks/use-financial-access"
import { randomRequestId } from "@/lib/browser-crypto"
import { evidenceAPI } from "@/features/evidence/api"
import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"
import { useFinancialDraft } from "../stores/financial-drafts"

const emptyCustodyDraft = {
  kind: "receipt",
  corrects: "",
  occurred_at: "",
  received_by: "",
  from_person_or_organisation: "",
  acquisition_method: "unknown",
  native_file_status: "unknown",
  certification_file_id: "",
  certification_filename: "",
  reason: "",
  sourceSha256: undefined as string | null | undefined,
  pending: null as { signature: string; id: string } | null,
}
const custodyLabels: Record<string, string> = {
  receipt: "Receipt",
  transfer: "Transfer",
  note: "Additional information",
  correction: "Correction",
  unknown: "Unknown",
  production: "Document production",
  subpoena: "Subpoena",
  client: "Client supplied",
  open_source: "Public source",
  other: "Other",
  provided: "Provided",
  requested: "Requested",
  unavailable: "Unavailable",
}

const event = z.object({
  id: z.string().uuid(),
  case_id: z.string().uuid(),
  evidence_file_id: z.string().uuid(),
  evidence_sha256: z.string().nullable(),
  recorded_at: z.string(),
  actor: z.object({
    name: z.string(),
    email: z.string(),
    user_id: z.string().nullable(),
  }),
  report: z.object({
    event_kind: z.enum(["receipt", "transfer", "note", "correction"]),
    occurred_at: z.string().nullable(),
    received_by: z.string().nullable(),
    from_person_or_organisation: z.string().nullable(),
    acquisition_method: z.string(),
    native_file_status: z.string(),
    certification_file_id: z.string().uuid().nullable(),
    certification_sha256: z.string().nullable(),
    corrects_event_id: z.string().uuid().nullable(),
    reason: z.string(),
  }),
})
const history = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  evidence_sha256: z.string().nullable(),
  events: z.array(event),
  limitation: z.string(),
})

export function SourceCustodyPanel({
  caseId,
  fileId,
}: {
  caseId: string
  fileId: string
}) {
  const [opened, setOpened] = useState(false)
  return (
    <section className="space-y-3 rounded border p-3">
      <Button
        variant="outline"
        aria-expanded={opened}
        onClick={() => setOpened(!opened)}
      >
        Source custody records
      </Button>
      {opened && (
        <CustodyEditor
          key={`${caseId}:${fileId}`}
          caseId={caseId}
          fileId={fileId}
        />
      )}
    </section>
  )
}

function CustodyEditor({ caseId, fileId }: { caseId: string; fileId: string }) {
  const { canEdit } = useFinancialAccess()
  const client = useQueryClient()
  const key = ["financial-source-custody", caseId, fileId]
  const url = candidateUrl(`sources/${fileId}/custody`, caseId)
  const [loadCertificates, setLoadCertificates] = useState(false)
  const certificates = useQuery({
    queryKey: ["custody-certification-files", caseId],
    enabled: loadCertificates,
    retry: false,
    queryFn: () => evidenceAPI.list(caseId),
  })
  const [draft, setDraft] = useFinancialDraft(
    caseId,
    `source-custody:${fileId}`,
    emptyCustodyDraft
  )
  const { kind, corrects } = draft
  const [message, setMessage] = useState("")
  const locked = useRef(false)
  const query = useQuery({
    queryKey: key,
    retry: false,
    queryFn: async () => {
      const data = history.parse(await fetchAPI(url))
      if (
        data.case_id !== caseId ||
        data.evidence_file_id !== fileId ||
        data.events.some(
          (e) => e.case_id !== caseId || e.evidence_file_id !== fileId
        )
      )
        throw new Error("Custody records do not match this source.")
      return data
    },
  })
  const sourceChanged =
    !!query.data &&
    draft.sourceSha256 !== undefined &&
    draft.sourceSha256 !== query.data.evidence_sha256
  const missingCorrection =
    kind === "correction" &&
    !query.data?.events.some((record) => record.id === corrects)
  const change = (values: Partial<typeof emptyCustodyDraft>) => {
    setDraft((current) => ({
      ...current,
      ...values,
      sourceSha256:
        current.sourceSha256 === undefined
          ? query.data?.evidence_sha256
          : current.sourceSha256,
      pending: null,
    }))
    setMessage("")
  }
  const save = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const saved = event.parse(await fetchAPI(url, { method: "POST", body }))
      if (
        saved.case_id !== caseId ||
        saved.evidence_file_id !== fileId ||
        saved.id !== body.event_id ||
        saved.evidence_sha256 !== body.expected_source_sha256 ||
        Object.entries(body).some(([name, value]) => {
          if (name === "event_id" || name === "expected_source_sha256")
            return false
          const actual = saved.report[name as keyof typeof saved.report]
          if (name === "occurred_at" && value && actual)
            return Date.parse(String(actual)) !== Date.parse(String(value))
          return actual !== value
        })
      )
        throw new Error(
          "The saved custody response does not match this submission. Reload the history before retrying."
        )
      return saved
    },
    onSuccess: async (_saved, body) => {
      setDraft((current) =>
        current.pending?.id === body.event_id ? emptyCustodyDraft : current
      )
      setMessage("Custody report recorded. Earlier reports remain preserved.")
      await client.invalidateQueries({ queryKey: key })
    },
    onSettled: () => {
      locked.current = false
    },
  })
  return (
    <div className="space-y-3 text-sm">
      <p>
        {canEdit
          ? "Record how this source was obtained and any known transfers. Leave unknown times blank."
          : "Read the recorded history of how this source was obtained and transferred."}
      </p>
      {query.isPending && <p role="status">Loading custody history…</p>}
      {query.isError && <p role="alert">{query.error.message}</p>}
      <Button
        variant="outline"
        disabled={query.isFetching || save.isPending}
        onClick={() => void query.refetch()}
      >
        Reload custody history
      </Button>
      {query.data && (
        <>
          <details>
            <summary>How to read this history</summary>
            <p>
              Each entry records what the named person reported. The reported
              event time may differ from the time they added it to Loupe.
              Missing history remains unknown. File references identify the
              registered documents; they do not verify earlier handling or
              authenticity.
            </p>
          </details>
          {!query.data.events.length && (
            <p>No custody reports recorded. Earlier custody is unknown.</p>
          )}
          <ol className="space-y-3">
            {query.data.events.map((e) => (
              <li key={e.id} className="break-words rounded border p-2">
                <p>
                  <strong>{custodyLabels[e.report.event_kind]}</strong> ·
                  reported time: {e.report.occurred_at || "Unknown"}
                </p>
                <p>
                  Recorded {e.recorded_at} by {e.actor.name} ({e.actor.email})
                </p>
                <p>
                  From: {e.report.from_person_or_organisation || "Unknown"}.
                  Received by: {e.report.received_by || "Unknown"}.
                </p>
                <p>
                  Obtained through:{" "}
                  {custodyLabels[e.report.acquisition_method] ||
                    e.report.acquisition_method}
                  . Native file:{" "}
                  {custodyLabels[e.report.native_file_status] ||
                    e.report.native_file_status}
                  .
                </p>
                <p>{e.report.reason}</p>
                {e.report.corrects_event_id && (
                  <p>
                    Corrects report {e.report.corrects_event_id}; the earlier
                    report remains visible.
                  </p>
                )}
                {e.report.certification_file_id && (
                  <p>
                    Certification file: {e.report.certification_file_id}.
                    Recorded SHA-256:{" "}
                    {e.report.certification_sha256 || "Unknown"}.
                  </p>
                )}
                <p className="text-xs">Report ID: {e.id}</p>
                {canEdit && (
                  <Button
                    variant="outline"
                    disabled={save.isPending}
                    onClick={() => {
                      change({
                        kind: "correction",
                        corrects: e.id,
                        occurred_at: e.report.occurred_at || "",
                        received_by: e.report.received_by || "",
                        from_person_or_organisation:
                          e.report.from_person_or_organisation || "",
                        acquisition_method: e.report.acquisition_method,
                        native_file_status: e.report.native_file_status,
                        certification_file_id:
                          e.report.certification_file_id || "",
                        certification_filename: "",
                        reason: "",
                      })
                    }}
                  >
                    Correct this custody report
                  </Button>
                )}
              </li>
            ))}
          </ol>
          {canEdit && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault()
                if (locked.current || sourceChanged || missingCorrection) return
                setMessage("")
                const value = (name: keyof typeof draft) =>
                  String(draft[name] || "").trim() || null
                const time = value("occurred_at")
                if (
                  time &&
                  (!/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(time) ||
                    Number.isNaN(Date.parse(time)))
                ) {
                  setMessage(
                    "Use a complete date and time with an explicit timezone, for example 2026-09-10T14:30:00+01:00."
                  )
                  return
                }
                const body = {
                  expected_source_sha256:
                    draft.sourceSha256 === undefined
                      ? query.data.evidence_sha256
                      : draft.sourceSha256,
                  event_kind: kind,
                  occurred_at: time,
                  received_by: value("received_by"),
                  from_person_or_organisation: value(
                    "from_person_or_organisation"
                  ),
                  acquisition_method: value("acquisition_method"),
                  native_file_status: value("native_file_status"),
                  certification_file_id: value("certification_file_id"),
                  corrects_event_id: kind === "correction" ? corrects : null,
                  reason: value("reason"),
                }
                const signature = JSON.stringify(body)
                const request =
                  draft.pending?.signature === signature
                    ? draft.pending
                    : { signature, id: randomRequestId() }
                locked.current = true
                setDraft((current) => ({ ...current, pending: request }))
                save.mutate({ ...body, event_id: request.id })
              }}
            >
              <p>
                Your unfinished report stays in this browser tab when you close
                the source or refresh. Wait for the recorded confirmation before
                treating it as part of the case history.
              </p>
              {draft.pending && !save.isPending && (
                <p role="status">
                  A previous submission may have reached the server. Reload
                  custody history to check it. Submitting the unchanged report
                  again uses the same request and does not add a second copy.
                </p>
              )}
              {sourceChanged && (
                <div role="alert" className="space-y-2">
                  <p>
                    The source file changed while this report was unfinished.
                    Check the current original before using these details.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      setDraft((current) => ({
                        ...current,
                        sourceSha256: query.data.evidence_sha256,
                        pending: null,
                      }))
                    }
                  >
                    Use details for the current source
                  </Button>
                </div>
              )}
              {missingCorrection && (
                <p role="alert">
                  The report selected for correction is not in the current
                  history. Reload the history and select the report again.
                </p>
              )}
              <fieldset disabled={save.isPending} className="grid gap-3">
                <legend className="font-semibold">
                  Add a custody report (case editors)
                </legend>
                <label>
                  Report type
                  <select
                    aria-label="Report type"
                    className="block w-full rounded border p-2"
                    value={kind}
                    onChange={(e) => change({ kind: e.target.value })}
                  >
                    <option value="receipt">Receipt</option>
                    <option value="transfer">Transfer</option>
                    <option value="note">Additional information</option>
                    <option value="correction" disabled={!corrects}>
                      Correction to selected report
                    </option>
                  </select>
                </label>
                {kind === "correction" && (
                  <p className="break-all">
                    Correcting report {corrects}. Describe the corrected facts
                    and why the earlier report was wrong.
                  </p>
                )}
                <label>
                  Reported event time with timezone (optional)
                  <input
                    name="occurred_at"
                    aria-label="Reported event time with timezone (optional)"
                    value={draft.occurred_at}
                    onChange={(e) => change({ occurred_at: e.target.value })}
                    maxLength={64}
                    placeholder="2026-09-10T14:30:00+01:00"
                    className="block w-full rounded border p-2"
                  />
                </label>
                <label>
                  Received from (optional)
                  <input
                    name="from_person_or_organisation"
                    aria-label="Received from (optional)"
                    value={draft.from_person_or_organisation}
                    onChange={(e) =>
                      change({ from_person_or_organisation: e.target.value })
                    }
                    maxLength={512}
                    className="block w-full rounded border p-2"
                  />
                </label>
                <label>
                  Received by
                  <input
                    name="received_by"
                    aria-label="Received by"
                    value={draft.received_by}
                    onChange={(e) => change({ received_by: e.target.value })}
                    required={kind === "receipt" || kind === "transfer"}
                    maxLength={512}
                    className="block w-full rounded border p-2"
                  />
                </label>
                <label>
                  How obtained
                  <select
                    aria-label="How obtained"
                    name="acquisition_method"
                    value={draft.acquisition_method}
                    onChange={(e) =>
                      change({ acquisition_method: e.target.value })
                    }
                    className="block w-full rounded border p-2"
                  >
                    <option value="unknown">Unknown</option>
                    <option value="production">Document production</option>
                    <option value="subpoena">Subpoena</option>
                    <option value="client">Client supplied</option>
                    <option value="open_source">Public source</option>
                    <option value="other">Other, explain below</option>
                  </select>
                </label>
                <label>
                  Native file availability
                  <select
                    aria-label="Native file availability"
                    name="native_file_status"
                    value={draft.native_file_status}
                    onChange={(e) =>
                      change({ native_file_status: e.target.value })
                    }
                    className="block w-full rounded border p-2"
                  >
                    <option value="unknown">Unknown</option>
                    <option value="provided">Provided</option>
                    <option value="requested">Requested</option>
                    <option value="unavailable">Unavailable</option>
                  </select>
                </label>
                <div>
                  <p>Supporting certification (optional)</p>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setLoadCertificates(true)}
                  >
                    Choose a certification file from this case
                  </Button>
                  {certificates.isFetching && (
                    <p role="status">Loading case files…</p>
                  )}
                  {certificates.isError && (
                    <p role="alert">
                      Case files could not be loaded.{" "}
                      {certificates.error.message}
                    </p>
                  )}
                  <select
                    aria-label="Supporting certification file"
                    name="certification_file_id"
                    className="block w-full rounded border p-2"
                    value={draft.certification_file_id}
                    onChange={(e) =>
                      change({
                        certification_file_id: e.target.value,
                        certification_filename:
                          certificates.data?.find(
                            (file) => file.id === e.target.value
                          )?.original_filename || "",
                      })
                    }
                  >
                    <option value="">No certification attached</option>
                    {draft.certification_file_id &&
                      !certificates.data?.some(
                        (file) => file.id === draft.certification_file_id
                      ) && (
                        <option value={draft.certification_file_id}>
                          {draft.certification_filename ||
                            draft.certification_file_id}{" "}
                          (previous selection; load files to check)
                        </option>
                      )}
                    {certificates.data
                      ?.filter((file) => file.id !== fileId)
                      .map((file) => (
                        <option key={file.id} value={file.id}>
                          {file.original_filename}
                        </option>
                      ))}
                  </select>
                </div>
                <label>
                  Details and reason
                  <textarea
                    name="reason"
                    aria-label="Details and reason"
                    value={draft.reason}
                    onChange={(e) => change({ reason: e.target.value })}
                    required
                    maxLength={4096}
                    className="block w-full rounded border p-2"
                  />
                </label>
                <Button
                  type="submit"
                  disabled={sourceChanged || missingCorrection}
                >
                  {save.isPending
                    ? "Recording custody report…"
                    : "Record custody report"}
                </Button>
              </fieldset>
            </form>
          )}
        </>
      )}
      {save.isError && <p role="alert">{save.error.message}</p>}
      {message && <p role="status">{message}</p>}
    </div>
  )
}
