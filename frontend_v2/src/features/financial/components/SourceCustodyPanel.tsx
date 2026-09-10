import { evidenceAPI } from "@/features/evidence/api"
import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { candidateUrl } from "../lib/candidate-contract"

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
  const [kind, setKind] = useState("receipt")
  const [corrects, setCorrects] = useState("")
  const [message, setMessage] = useState("")
  const pending = useRef<{ signature: string; id: string } | null>(null)
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
  const save = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const saved = event.parse(await fetchAPI(url, { method: "POST", body }))
      if (
        saved.case_id !== caseId ||
        saved.evidence_file_id !== fileId ||
        saved.id !== body.event_id
      )
        throw new Error(
          "The saved custody response does not match this submission. Reload the history before retrying."
        )
      return saved
    },
    onSuccess: async () => {
      setMessage("Custody report recorded. Earlier reports remain preserved.")
      await client.invalidateQueries({ queryKey: key })
    },
  })
  return (
    <div className="space-y-3 text-sm">
      <p>
        Record how this source was obtained and any known transfers. Leave
        unknown times blank. Recording a report does not verify its accuracy or
        admit transactions.
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
          <p>{query.data.limitation}</p>
          {!query.data.events.length && (
            <p>No custody reports recorded. Earlier custody is unknown.</p>
          )}
          <ol className="space-y-3">
            {query.data.events.map((e) => (
              <li key={e.id} className="break-words rounded border p-2">
                <p>
                  <strong>{e.report.event_kind}</strong> — reported time:{" "}
                  {e.report.occurred_at || "Unknown"}
                </p>
                <p>
                  Recorded {e.recorded_at} by {e.actor.name} ({e.actor.email})
                </p>
                <p>
                  From: {e.report.from_person_or_organisation || "Unknown"}.
                  Received by: {e.report.received_by || "Unknown"}.
                </p>
                <p>
                  Obtained through: {e.report.acquisition_method}. Native file:{" "}
                  {e.report.native_file_status}.
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
                <Button
                  variant="outline"
                  disabled={save.isPending}
                  onClick={() => {
                    setKind("correction")
                    setCorrects(e.id)
                    setMessage("")
                  }}
                >
                  Correct this custody report
                </Button>
              </li>
            ))}
          </ol>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              setMessage("")
              const data = new FormData(e.currentTarget)
              const value = (name: string) =>
                String(data.get(name) || "").trim() || null
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
                expected_source_sha256: query.data.evidence_sha256,
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
              if (pending.current?.signature !== signature)
                pending.current = { signature, id: crypto.randomUUID() }
              save.mutate({ ...body, event_id: pending.current.id })
            }}
          >
            <fieldset disabled={save.isPending} className="grid gap-3">
              <legend className="font-semibold">
                Add a custody report (case editors)
              </legend>
              <label>
                Report type
                <select
                  className="block w-full rounded border p-2"
                  value={kind}
                  onChange={(e) => {
                    setKind(e.target.value)
                    setMessage("")
                  }}
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
                  Correcting report {corrects}. Describe the corrected facts and
                  why the earlier report was wrong.
                </p>
              )}
              <label>
                Reported event time with timezone (optional)
                <input
                  name="occurred_at"
                  maxLength={64}
                  placeholder="2026-09-10T14:30:00+01:00"
                  className="block w-full rounded border p-2"
                />
              </label>
              <label>
                Received from (optional)
                <input
                  name="from_person_or_organisation"
                  maxLength={512}
                  className="block w-full rounded border p-2"
                />
              </label>
              <label>
                Received by
                <input
                  name="received_by"
                  required={kind === "receipt" || kind === "transfer"}
                  maxLength={512}
                  className="block w-full rounded border p-2"
                />
              </label>
              <label>
                How obtained
                <select
                  name="acquisition_method"
                  defaultValue="unknown"
                  className="block w-full rounded border p-2"
                >
                  <option value="unknown">Unknown</option>
                  <option value="production">Document production</option>
                  <option value="subpoena">Subpoena</option>
                  <option value="client">Client supplied</option>
                  <option value="open_source">Public source</option>
                  <option value="other">Other — explain below</option>
                </select>
              </label>
              <label>
                Native file availability
                <select
                  name="native_file_status"
                  defaultValue="unknown"
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
                    Case files could not be loaded. {certificates.error.message}
                  </p>
                )}
                <select
                  aria-label="Supporting certification file"
                  name="certification_file_id"
                  className="block w-full rounded border p-2"
                  defaultValue=""
                >
                  <option value="">No certification attached</option>
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
                  required
                  maxLength={4096}
                  className="block w-full rounded border p-2"
                />
              </label>
              <Button type="submit">
                {save.isPending
                  ? "Recording custody report…"
                  : "Record custody report"}
              </Button>
            </fieldset>
          </form>
        </>
      )}
      {save.isError && <p role="alert">{save.error.message}</p>}
      {message && <p role="status">{message}</p>}
    </div>
  )
}
