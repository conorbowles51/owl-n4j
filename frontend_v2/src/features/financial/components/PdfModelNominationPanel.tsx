import { useEffect, useRef, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI, ApiError } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
import { sourceTable } from "../lib/pdf-source-table"
import {
  pdfModelNomination,
  modelNominationPlans,
  type PdfModelNomination,
} from "../lib/pdf-model-nomination"
import { verifyQueuedMapping } from "../lib/scanned-reading-queue"
const historySchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  offset: z.number().int().nonnegative(),
  has_more: z.boolean(),
  items: z.array(
    z.object({
      id: z.string().uuid(),
      status: z.enum(["pending", "completed", "failed"]),
      page_number: z.number().int(),
      created_at: z.string(),
    })
  ),
  applied: z.literal(false),
})
export function PdfModelNominationPanel({
  source,
  onSaved,
  onSource,
}: {
  source: z.infer<typeof sourceTable>
  onSaved: (id: string) => void
  onSource: (cell: {
    row: number
    column: number
    text: string
    locator: unknown
  }) => void
}) {
  const [unrecorded, setUnrecorded] = useState(false)
  const [opened, setOpened] = useState(false),
    [run, setRun] = useState<PdfModelNomination | null>(null),
    [attemptId, setAttemptId] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [selected, setSelected] = useState<number[]>([]),
    [rowPage, setRowPage] = useState(0),
    [historyPage, setHistoryPage] = useState(0),
    [saved, setSaved] = useState<
      { id: string; group: number; count: number }[]
    >([]),
    [saveAttempted, setSaveAttempted] = useState(false)
  const active = useRef(true),
    lock = useRef(false),
    client = useQueryClient()
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  const path = `candidate-sources/${encodeURIComponent(source.evidence_file_id)}/model-nominations`
  const history = useQuery({
    queryKey: [
      "financial-model-nominations",
      source.case_id,
      source.evidence_file_id,
      source.page_number,
      source.table_index,
      historyPage,
    ],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const data = historySchema.parse(
        await fetchAPI(
          candidateUrl(path, source.case_id) +
            `&page_number=${source.page_number}&table_index=${source.table_index}&limit=20&offset=${historyPage * 20}`
        )
      )
      if (
        data.case_id !== source.case_id ||
        data.evidence_file_id !== source.evidence_file_id ||
        data.offset !== historyPage * 20 ||
        data.items.some((i) => i.page_number !== source.page_number)
      )
        throw Error("Saved attempts do not match this source page.")
      return data
    },
  })
  const accept = (raw: unknown, id: string) => {
    const data = pdfModelNomination.parse(raw)
    if (
      data.id !== id ||
      data.case_id !== source.case_id ||
      data.evidence_file_id !== source.evidence_file_id ||
      data.request.page_number !== source.page_number ||
      data.request.table_index !== source.table_index
    )
      throw Error("Model attempt does not match this source page.")
    setUnrecorded(false)
    setRun(data)
    setSelected([])
    setRowPage(0)
    setSaveAttempted(false)
    setSaved([])
  }
  const check = async (id: string) => {
    if (lock.current) return
    lock.current = true
    setBusy(true)
    setMessage("")
    try {
      const data = await fetchAPI(
        candidateUrl(`model-nominations/${id}`, source.case_id)
      )
      if (active.current) {
        setAttemptId(id)
        accept(data, id)
      }
    } catch (error) {
      if (active.current && error instanceof ApiError && error.status === 404)
        setUnrecorded(true)
      if (active.current)
        setMessage(
          error instanceof Error
            ? error.message
            : "Saved attempt could not be read."
        )
    } finally {
      lock.current = false
      if (active.current) setBusy(false)
    }
  }
  const request = async (reuseId?: string) => {
    if (lock.current || (attemptId && reuseId !== attemptId)) return
    lock.current = true
    setBusy(true)
    setMessage("")
    const id = reuseId ?? crypto.randomUUID()
    setUnrecorded(false)
    setAttemptId(id)
    try {
      const data = await fetchAPI(candidateUrl(path, source.case_id), {
        method: "POST",
        body: {
          request_id: id,
          page_number: source.page_number,
          table_index: source.table_index,
          source_revision: source.source_revision,
        },
        timeout: 110000,
      })
      if (active.current) accept(data, id)
    } catch (error) {
      if (active.current) {
        setMessage(
          `${error instanceof Error ? error.message : "The request did not finish."} Check the saved attempt before making another request.`
        )
        if (
          error instanceof ApiError &&
          [403, 404, 409, 422].includes(error.status)
        )
          setAttemptId(null)
      }
    } finally {
      lock.current = false
      if (active.current) setBusy(false)
      void history.refetch()
    }
  }
  const abandon = async () => {
    if (lock.current || !run || run.status !== "pending") return
    lock.current = true
    setBusy(true)
    setMessage("")
    try {
      const data = await fetchAPI(
        candidateUrl(`model-nominations/${run.id}/abandon`, source.case_id),
        { method: "POST" }
      )
      if (active.current) accept(data, run.id)
    } catch (error) {
      if (active.current)
        setMessage(
          error instanceof Error
            ? error.message
            : "The attempt could not be closed. Check its saved status."
        )
    } finally {
      lock.current = false
      if (active.current) setBusy(false)
      void history.refetch()
    }
  }
  const current = run?.request.source_revision === source.source_revision
  const save = async () => {
    if (lock.current || !run || !current || saveAttempted || !selected.length)
      return
    lock.current = true
    setBusy(true)
    setSaveAttempted(true)
    let group = 0
    try {
      const fresh = await fetchAPI(
        candidateUrl(
          `candidate-sources/${source.evidence_file_id}/pages/${source.page_number}`,
          source.case_id
        ) + `&table_index=${source.table_index}`
      )
      const plans = modelNominationPlans(run, selected, fresh)
      for (const [index, proposal] of plans.entries()) {
        if (!active.current) return
        group = index + 1
        setMessage(`Saving model review group ${group} of ${plans.length}…`)
        const raw = await fetchAPI(
          candidateUrl("candidate-mappings", source.case_id),
          { method: "POST", body: proposal }
        )
        const mapping = verifyQueuedMapping(raw, proposal)
        if (!active.current) return
        setSaved((old) => [
          ...old,
          { id: mapping.id, group, count: mapping.candidates.length },
        ])
      }
      setMessage(
        "Selected model proposals are saved for review. No transactions were admitted."
      )
    } catch (error) {
      if (active.current)
        setMessage(
          `${error instanceof Error ? error.message : "Saving stopped."} ${group ? `Check the save outcome for group ${group} in PDF readings before retrying. Earlier saved groups remain; later groups were not attempted.` : "Nothing was saved by this attempt."}`
        )
    } finally {
      lock.current = false
      if (active.current) setBusy(false)
      void client.invalidateQueries({
        queryKey: ["financial-candidates", source.case_id, "list"],
      })
    }
  }
  return (
    <section
      aria-label="Model-assisted PDF nominations"
      className="space-y-3 rounded border p-3"
    >
      <Button variant="outline" onClick={() => setOpened((v) => !v)}>
        {opened
          ? "Hide model-assisted proposals"
          : "Model-assisted row proposals"}
      </Button>
      {opened && (
        <>
          <p>
            Use the local scan and printed-layout aids first. This optional
            fallback sends this stored table’s text to the configured extraction
            model. It proposes existing cells for human review; it cannot
            correct source values or admit transactions. One request covers one
            table, up to 200 rows and 24KB of source text.
          </p>
          <Button
            disabled={busy || attemptId !== null}
            onClick={() => void request()}
          >
            Request AI proposals for this page
          </Button>
          {busy && <p role="status">Working on the selected request…</p>}
          {attemptId && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void check(attemptId)}
            >
              Check saved model attempt
            </Button>
          )}
          {unrecorded && attemptId && (
            <div>
              <p>
                No saved attempt was found. Retry with this same request ID to
                avoid duplicating any request still reaching the server.
              </p>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void request(attemptId)}
              >
                Retry the same model request ID
              </Button>
            </div>
          )}
          {message && <p role="status">{message}</p>}
          {run && (
            <div className="space-y-3">
              <p>
                Attempt status: {run.status}. Requested model:{" "}
                {run.request.provider} / {run.request.model_id}. Prompt:{" "}
                {run.request.schema_version}.
              </p>
              {run.result && (
                <p>
                  Provider-reported model:{" "}
                  {run.result.transport?.status === "captured"
                    ? (run.result.transport.response_metadata.reported_model ??
                      "Not reported")
                    : "Not recorded"}
                  .
                  {run.result.transport?.status === "captured"
                    ? " Provider request settings are retained with this review's export history."
                    : " A complete provider request record is unavailable for this attempt."}
                </p>
              )}
              {run.request.execution_mode === "simulated_test" && (
                <p>
                  SIMULATED acceptance data: no external model ran for this
                  attempt.
                </p>
              )}
              <p>{run.limitation}</p>
              {!current && (
                <p role="alert">
                  This attempt belongs to an older source preparation. Its
                  proposals cannot be applied to this page.
                </p>
              )}
              {run.status === "pending" && (
                <p>
                  The attempt has not recorded an outcome. It may still be
                  running or have been interrupted. Checking its saved status
                  does not call the provider again.
                </p>
              )}
              {run.status === "pending" && (
                <div>
                  <p>
                    Closing this attempt prevents its result from being used. A
                    request already sent to the provider may still finish and
                    incur usage.
                  </p>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void abandon()}
                  >
                    Close interrupted model attempt
                  </Button>
                </div>
              )}
              {run.status === "failed" && (
                <p role="alert">
                  The attempt failed ({run.error_code}). Check the provider
                  connection or source before starting another request. No model
                  proposals were accepted.
                </p>
              )}
              {run.status !== "pending" && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setAttemptId(null)
                    setRun(null)
                    setSelected([])
                    setSaved([])
                    setSaveAttempted(false)
                    setMessage("")
                  }}
                >
                  Start a separate model request
                </Button>
              )}
              {run.result && (
                <>
                  <p>
                    {run.result.rows.length} nominated rows.{" "}
                    {run.result.usage.total_tokens !== undefined
                      ? `${run.result.usage.total_tokens} provider-reported tokens.`
                      : "Provider usage is unavailable."}
                  </p>
                  {!run.result.rows.length && (
                    <p>
                      No rows were nominated. This does not establish that the
                      page contains no transactions.
                    </p>
                  )}
                  <fieldset
                    disabled={busy || saveAttempted || !current}
                    className="space-y-2"
                  >
                    <Button
                      variant="outline"
                      onClick={() =>
                        setSelected(run.result!.rows.map((r) => r.row_index))
                      }
                    >
                      Select all model proposals
                    </Button>
                    <Button variant="outline" onClick={() => setSelected([])}>
                      Clear model selection
                    </Button>
                    {run.result.rows
                      .slice(rowPage * 10, rowPage * 10 + 10)
                      .map((row) => (
                        <div
                          key={row.row_index}
                          className="space-y-1 border-t pt-2"
                        >
                          <label>
                            <input
                              type="checkbox"
                              checked={selected.includes(row.row_index)}
                              onChange={(e) =>
                                setSelected((old) =>
                                  e.target.checked
                                    ? [...old, row.row_index]
                                    : old.filter((i) => i !== row.row_index)
                                )
                              }
                            />{" "}
                            Select model row {row.row_index + 1}
                          </label>
                          <p>Model reason: {row.reason}</p>
                          <div className="flex flex-wrap gap-2">
                            {row.cells.map((cell) => (
                              <Button
                                key={cell.column_index}
                                variant="outline"
                                onClick={() =>
                                  onSource({
                                    row: row.row_index,
                                    column: cell.column_index,
                                    text: cell.expected_text,
                                    locator: cell.locator,
                                  })
                                }
                              >
                                {cell.proposed_meaning.replaceAll("_", " ")}:{" "}
                                {cell.expected_text}
                              </Button>
                            ))}
                          </div>
                        </div>
                      ))}
                    <Button
                      disabled={!selected.length}
                      onClick={() => void save()}
                    >
                      Save selected model proposals for review
                    </Button>
                  </fieldset>
                  {run.result.rows.length > 10 && (
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        disabled={!rowPage || busy}
                        onClick={() => setRowPage((p) => p - 1)}
                      >
                        Previous model rows
                      </Button>
                      <span>
                        Page {rowPage + 1} of{" "}
                        {Math.ceil(run.result.rows.length / 10)}
                      </span>
                      <Button
                        variant="outline"
                        disabled={
                          (rowPage + 1) * 10 >= run.result.rows.length || busy
                        }
                        onClick={() => setRowPage((p) => p + 1)}
                      >
                        Next model rows
                      </Button>
                    </div>
                  )}
                </>
              )}
              {!!saved.length && (
                <ul>
                  {saved.map((g) => (
                    <li key={g.id}>
                      Group {g.group}: {g.count} readings.{" "}
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => onSaved(g.id)}
                      >
                        Open model review group {g.group}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <details>
            <summary>Saved attempts for this source table</summary>
            {history.isPending ? (
              <p>Loading attempts…</p>
            ) : history.isError ? (
              <p role="alert">{history.error.message}</p>
            ) : (
              <>
                <ul>
                  {history.data?.items.map((item) => (
                    <li key={item.id}>
                      {item.created_at} · {item.status}{" "}
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => void check(item.id)}
                      >
                        Open saved attempt {item.id.slice(0, 8)}
                      </Button>
                    </li>
                  ))}
                </ul>
                <Button
                  variant="outline"
                  disabled={!historyPage || busy}
                  onClick={() => setHistoryPage((p) => p - 1)}
                >
                  Previous attempts
                </Button>
                <Button
                  variant="outline"
                  disabled={!history.data?.has_more || busy}
                  onClick={() => setHistoryPage((p) => p + 1)}
                >
                  Next attempts
                </Button>
              </>
            )}
          </details>
        </>
      )}
    </section>
  )
}
