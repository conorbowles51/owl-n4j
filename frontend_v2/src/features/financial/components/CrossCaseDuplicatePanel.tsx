import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { casesAPI } from "@/features/cases/api"
import { candidateUrl } from "../lib/candidate-contract"
const document = z.object({
  case_id: z.string(),
  document_id: z.string(),
  filename: z.string(),
  status: z.string(),
})
const comparison = z.object({
  case_id: z.string(),
  comparison_case_id: z.string(),
  applied: z.literal(false),
  documents: z.record(z.string(), z.number().int().nonnegative()),
  compared: z.record(z.string(), z.number().int().nonnegative()),
  stored_rows_checked: z.number().int().nonnegative(),
  limitation: z.string(),
  skipped: z.array(document.extend({ reason: z.string() })),
  matches: z
    .array(
      z.object({
        left: document,
        right: document,
        matching_ingestion_hash: z.boolean(),
        matching_stored_reading: z.boolean(),
      })
    )
    .max(1000),
})
export function CrossCaseDuplicatePanel({ caseId }: { caseId: string }) {
  const [opened, setOpened] = useState(false),
    [other, setOther] = useState("")
  const cases = useQuery({
    queryKey: ["financial-comparison-cases", caseId],
    enabled: opened,
    retry: false,
    queryFn: () => casesAPI.list("all_cases", true),
  })
  return (
    <section
      aria-label="Cross-case document comparison"
      className="space-y-3 rounded border p-4"
    >
      <h3 className="font-semibold">Compare with another case</h3>
      <p>
        Find matching financial source documents in a second case you can view.
      </p>
      {!opened ? (
        <Button variant="outline" onClick={() => setOpened(true)}>
          Choose comparison case
        </Button>
      ) : (
        <>
          {cases.isPending && <p role="status">Loading available cases…</p>}
          {cases.isError && (
            <p role="alert">Available cases could not be loaded.</p>
          )}
          {cases.data && !cases.isError && (
            <label>
              Comparison case{" "}
              <select
                aria-label="Comparison case"
                value={other}
                className="border bg-background p-2"
                onChange={(e) => setOther(e.target.value)}
              >
                <option value="">Choose a different case</option>
                {cases.data
                  .filter((c) => c.id !== caseId)
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
              </select>
            </label>
          )}
          {other && <Comparison key={other} caseId={caseId} other={other} />}
        </>
      )}
    </section>
  )
}
function Comparison({ caseId, other }: { caseId: string; other: string }) {
  const [opened, setOpened] = useState(false),
    [page, setPage] = useState(0)
  const result = useQuery({
    queryKey: ["financial-ledger", caseId, "cross-case-duplicates", other],
    enabled: opened,
    retry: false,
    queryFn: async () => {
      const data = comparison.parse(
        await fetchAPI(
          `${candidateUrl("cross-case-duplicates", caseId)}&${new URLSearchParams({ comparison_case_id: other })}`,
          { timeout: 120000 }
        )
      )
      if (
        data.case_id !== caseId ||
        data.comparison_case_id !== other ||
        data.matches.some(
          (m) =>
            m.left.case_id !== caseId ||
            m.right.case_id !== other ||
            (!m.matching_ingestion_hash && !m.matching_stored_reading)
        ) ||
        data.skipped.some((d) => ![caseId, other].includes(d.case_id))
      )
        throw Error("Comparison returned for a different scope.")
      return data
    },
  })
  const index = Math.min(
    page,
    Math.max(0, Math.ceil((result.data?.matches.length ?? 0) / 20) - 1)
  )
  return (
    <div className="space-y-3">
      <Button
        disabled={result.isFetching}
        onClick={() => {
          if (opened) void result.refetch()
          else setOpened(true)
        }}
      >
        {opened ? "Refresh cross-case comparison" : "Compare selected cases"}
      </Button>
      {opened && result.isPending && <p role="status">Comparing both cases…</p>}
      {result.isError && (
        <p role="alert">Comparison unavailable. {result.error.message}</p>
      )}
      {result.data && !result.isFetching && !result.isError && (
        <>
          <p>
            {result.data.compared[caseId]} of {result.data.documents[caseId]}{" "}
            documents in this case; {result.data.compared[other]} of{" "}
            {result.data.documents[other]} in the comparison case.{" "}
            {result.data.stored_rows_checked} stored readings checked.
          </p>
          <p>{result.data.limitation}</p>
          <p>{result.data.matches.length} possible matches.</p>
          <ul className="space-y-3">
            {result.data.matches
              .slice(index * 20, index * 20 + 20)
              .map((m, i) => (
                <li
                  className="rounded border p-3"
                  key={`${m.left.document_id}:${m.right.document_id}`}
                >
                  <p className="break-words">
                    {index * 20 + i + 1}. {m.left.filename} ↔ {m.right.filename}
                  </p>
                  <p>
                    {m.matching_ingestion_hash
                      ? "Matching ingestion file hash. "
                      : ""}
                    {m.matching_stored_reading
                      ? "Matching stored reading and recorded coverage."
                      : "Stored readings are not established as equal."}
                  </p>
                  <p>
                    Statuses: {m.left.status} / {m.right.status}.
                  </p>
                  <a className="underline" href={`/cases/${other}/financial`}>
                    Open comparison case financial review
                  </a>
                </li>
              ))}
          </ul>
          {result.data.matches.length > 20 && (
            <div className="flex gap-2">
              <Button disabled={!index} onClick={() => setPage(index - 1)}>
                Previous comparison matches
              </Button>
              <Button
                disabled={(index + 1) * 20 >= result.data!.matches.length}
                onClick={() => setPage(index + 1)}
              >
                Next comparison matches
              </Button>
            </div>
          )}
          {!!result.data.skipped.length && (
            <details>
              <summary>
                Documents not compared ({result.data.skipped.length})
              </summary>
              {result.data.skipped.map((d) => (
                <p key={d.document_id}>
                  {d.filename}: {d.reason}
                </p>
              ))}
            </details>
          )}
        </>
      )}
    </div>
  )
}
