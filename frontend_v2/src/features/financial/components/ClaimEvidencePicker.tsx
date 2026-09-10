import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { DocumentViewer } from "@/components/ui/document-viewer"
import { evidenceAPI } from "@/features/evidence/api"
import { caseworkAPI } from "@/features/workspace/casework-api"
export function ClaimEvidencePicker({
  caseId,
  value,
  onChange,
}: {
  caseId: string
  value: { id: string; label: string } | null
  onChange: (value: { id: string; label: string }) => void
}) {
  const [search, setSearch] = useState(""),
    [view, setView] = useState(false)
  const load = useMutation({
    retry: false,
    mutationFn: () =>
      caseworkAPI.attachmentOptions(caseId, "evidence", search, 20),
  })
  return (
    <section className="space-y-2 rounded border p-3">
      <h3 className="font-semibold">Source of the payment claim</h3>
      <label>
        Find claim evidence
        <input
          aria-label="Find claim evidence"
          className="ml-2 border bg-background p-2"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <Button
        type="button"
        variant="outline"
        disabled={load.isPending}
        onClick={() => load.mutate()}
      >
        Search claim sources
      </Button>
      {load.isError && <p role="alert">{load.error.message}</p>}
      {load.data && (
        <div className="space-y-1">
          {load.data.items.map((item) => (
            <Button
              key={item.target_id}
              type="button"
              variant="outline"
              onClick={() =>
                onChange({ id: item.target_id, label: item.label })
              }
            >
              Use claim source {item.label}
            </Button>
          ))}
          {!load.data.items.length && (
            <p>
              No source files match. Refine the search or add the evidence to
              the case.
            </p>
          )}
          {load.data.items.length === 20 && (
            <p>Showing the first20 matches; refine the search if needed.</p>
          )}
        </div>
      )}
      {value && (
        <div>
          <p>Selected claim source: {value.label}</p>
          <Button type="button" variant="outline" onClick={() => setView(true)}>
            Inspect claim source
          </Button>
          <DocumentViewer
            caseId={caseId}
            evidenceId={value.id}
            open={view}
            onOpenChange={setView}
            documentUrl={evidenceAPI.getFileUrl(value.id)}
            documentName={value.label}
          />
        </div>
      )}
    </section>
  )
}
