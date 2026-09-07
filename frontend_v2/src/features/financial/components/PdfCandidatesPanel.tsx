import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import {
  assertCandidateScope,
  candidateList,
  candidateMapping,
  candidateUrl,
} from "../lib/candidate-contract"
import { CandidateFinalizationPanel } from "./CandidateFinalizationPanel"
import { CandidateReuseCheck } from "./CandidateReuseCheck"
import { CandidateSourcePicker } from "./CandidateSourcePicker"
import { CandidateReviewForm } from "./CandidateReviewForm"

export function PdfCandidatesPanel({ caseId }: { caseId: string | undefined }) {
  const [opened, setOpened] = useState(false)
  return (
    <section
      aria-label="Saved PDF readings"
      className="space-y-3 rounded-lg border bg-card p-4"
    >
      <h2 className="text-sm font-semibold">PDF readings</h2>
      <p className="text-xs text-muted-foreground">
        Review saved possible transactions alongside their original readings.
        They remain outside ledger totals until separately admitted.
      </p>
      {!caseId ? (
        <p>Choose a case to review PDF readings.</p>
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={() => setOpened((v) => !v)}
        >
          {opened ? "Hide PDF readings" : "Open PDF readings"}
        </Button>
      )}
      {opened && caseId && <CandidateMappings key={caseId} caseId={caseId} />}
    </section>
  )
}

function CandidateMappings({ caseId }: { caseId: string }) {
  const [targetCandidate, setTargetCandidate] = useState<string | null>(null)
  const [choosing, setChoosing] = useState(false)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const list = useQuery({
    queryKey: ["financial-candidates", caseId, "list", offset],
    retry: false,
    queryFn: async () => {
      const data = candidateList.parse(
        await fetchAPI<unknown>(
          `${candidateUrl("candidate-mappings", caseId)}&limit=25&offset=${offset}`
        )
      )
      assertCandidateScope(data, caseId)
      if (data.offset !== offset)
        throw new Error("The saved-reading list returned a different page.")
      return data
    },
  })
  return (
    <div className="space-y-3 text-sm">
      <Button variant="outline" onClick={() => setChoosing((v) => !v)}>
        {choosing ? "Hide source selection" : "Choose PDF rows"}
      </Button>
      {choosing && (
        <CandidateSourcePicker caseId={caseId} onSaved={setSelected} />
      )}
      <Button
        variant="outline"
        size="sm"
        disabled={list.isFetching}
        onClick={() => void list.refetch()}
      >
        Refresh PDF readings
      </Button>
      {list.isError ? (
        <p role="alert">
          Saved readings could not be loaded. {list.error.message}
        </p>
      ) : list.isPending ? (
        <p role="status">Loading saved readings…</p>
      ) : (
        <>
          {list.data.items.length === 0 && (
            <p>No PDF readings have been saved in this case yet.</p>
          )}
          <ul className="space-y-2">
            {list.data.items.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded border p-3"
              >
                <div>
                  <p className="font-medium">{item.filename}</p>
                  <p>
                    {item.candidate_count} possible transactions · saved{" "}
                    {new Date(item.created_at).toLocaleString()}
                  </p>
                </div>
                <Button size="sm" onClick={() => setSelected(item.id)}>
                  Open readings
                </Button>
              </li>
            ))}
          </ul>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={offset === 0}
              onClick={() => {
                setSelected(null)
                setOffset((n) => Math.max(0, n - 25))
              }}
            >
              Previous batches
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!list.data.has_more}
              onClick={() => {
                setSelected(null)
                setOffset((n) => n + 25)
              }}
            >
              Next batches
            </Button>
          </div>
        </>
      )}
      {selected && (
        <CandidateRows
          key={`${caseId}:${selected}:${targetCandidate}`}
          caseId={caseId}
          mappingId={selected}
          initialCandidateId={targetCandidate}
          onOpenReading={(mapping, candidate) => {
            setSelected(mapping)
            setTargetCandidate(candidate)
          }}
        />
      )}
    </div>
  )
}

function CandidateRows({
  caseId,
  mappingId,
  initialCandidateId,
  onOpenReading,
}: {
  caseId: string
  mappingId: string
  initialCandidateId: string | null
  onOpenReading: (mapping: string, candidate: string) => void
}) {
  const [selected, setSelected] = useState<string | null>(initialCandidateId)
  const [page, setPage] = useState(0)
  const mapping = useQuery({
    queryKey: ["financial-candidates", caseId, "mapping", mappingId],
    retry: false,
    queryFn: async () => {
      const data = candidateMapping.parse(
        await fetchAPI<unknown>(
          candidateUrl(
            `candidate-mappings/${encodeURIComponent(mappingId)}`,
            caseId
          )
        )
      )
      assertCandidateScope(data, caseId)
      if (
        data.id !== mappingId ||
        data.original.proposal.case_id !== caseId ||
        data.original.proposal.evidence_file_id !== data.evidence_file_id
      )
        throw new Error("The saved source mapping does not match this case.")
      return data
    },
  })
  if (mapping.isError)
    return (
      <div>
        <p role="alert">
          Readings could not be loaded. {mapping.error.message}
        </p>
        <Button onClick={() => void mapping.refetch()}>Reload readings</Button>
      </div>
    )
  if (mapping.isPending) return <p role="status">Loading original readings…</p>
  const data = mapping.data
  return (
    <div className="space-y-3">
      <CandidateReuseCheck
        caseId={caseId}
        fileId={data.evidence_file_id}
        onOpenReading={onOpenReading}
      />
      <CandidateFinalizationPanel caseId={caseId} fileId={data.evidence_file_id} />
      <h3 className="font-semibold">Saved original readings</h3>
      <ul className="space-y-2">
        {data.candidates.slice(page * 25, page * 25 + 25).map((row) => (
          <li key={row.id} className="rounded border p-3">
            <p>
              Source row {row.row_index + 1} · <strong>{row.status}</strong>
            </p>
            <p className="whitespace-pre-wrap break-words">
              {row.original.cells
                .map((cell) => cell.text ?? cell.source?.text)
                .join(" · ")}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setSelected(row.id)}
            >
              Review source row {row.row_index + 1}
            </Button>
          </li>
        ))}
      </ul>
      {data.candidates.length > 25 && (
        <div className="flex gap-2">
          <Button disabled={page === 0} onClick={() => setPage((n) => n - 1)}>
            Previous readings
          </Button>
          <Button
            disabled={(page + 1) * 25 >= data.candidates.length}
            onClick={() => setPage((n) => n + 1)}
          >
            Next readings
          </Button>
        </div>
      )}
      {selected && data.candidates.some((row) => row.id === selected) && (
        <CandidateReviewForm
          key={`${caseId}:${selected}`}
          caseId={caseId}
          candidateId={selected}
          mappingId={mappingId}
          fileId={data.evidence_file_id}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
