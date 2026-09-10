import { useState } from "react"
import { Button } from "@/components/ui/button"
import type { TransferInputs } from "../lib/ledger-transfers"

export function TransferReferenceEvidence({
  data,
  onSource,
}: {
  data: TransferInputs
  onSource: (id: string) => void
}) {
  const [page, setPage] = useState(0)
  const items = data.reference_evidence
  return (
    <section
      aria-label="Payment identifier evidence"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">Payment identifier evidence</h3>
      <p>
        {items.length} shared-reference comparisons. Equal identifiers can
        connect sources; they do not by themselves establish one payment or
        remove a posting.
      </p>
      <p>
        {data.unscoped_reference_ids.length} readings have references without a
        supported scope and were not matched by identifier.
      </p>
      {items.slice(page * 10, page * 10 + 10).map((item, index) => (
        <article
          key={`${item.left_id}:${item.right_id}`}
          className="space-y-2 border-t pt-2"
        >
          <p className="break-all">
            {item.reference.kind}: {item.reference.value}
          </p>
          <p>
            Scope:{" "}
            {item.reference.scope_key ??
              "UUID equality; source field meaning must be checked"}
          </p>
          <p>
            {item.relation === "same_side"
              ? "Additional sighting on the same account"
              : item.relation === "conflict"
                ? "Conflicting account or direction evidence"
                : "Opposite sides on different accounts"}
            . {item.reason}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => onSource(item.left_id)}
            >
              First identifier source {page * 10 + index + 1}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onSource(item.right_id)}
            >
              Second identifier source {page * 10 + index + 1}
            </Button>
          </div>
        </article>
      ))}
      {items.length > 10 && (
        <div className="flex gap-2">
          <Button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Previous identifiers
          </Button>
          <Button
            disabled={(page + 1) * 10 >= items.length}
            onClick={() => setPage((p) => p + 1)}
          >
            Next identifiers
          </Button>
        </div>
      )}
    </section>
  )
}
