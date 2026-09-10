import { useState, useMemo } from "react"
import type { z } from "zod"
import type { counterpartyParties } from "../lib/counterparty-parties"
import { paymentIdentitySuggestions } from "../lib/payment-identity-suggestions"
import { Button } from "@/components/ui/button"

export function PaymentIdentitySuggestions({
  readings,
  onSelect,
  onSource,
  disabled,
}: {
  readings: z.infer<typeof counterpartyParties>["readings"]
  onSelect: (ids: string[], partyId: string) => void
  onSource: (id: string) => void
  disabled: boolean
}) {
  const [opened, setOpened] = useState(false),
    [page, setPage] = useState(0)
  const suggestions = useMemo(
    () => (opened ? paymentIdentitySuggestions(readings) : []),
    [opened, readings]
  )
  const safePage = Math.min(
    page,
    Math.max(0, Math.ceil(suggestions.length / 10) - 1)
  )
  return (
    <section
      className="space-y-2 rounded border p-3"
      aria-label="Possible payment identity links"
    >
      <Button
        variant="outline"
        disabled={disabled}
        onClick={() => setOpened((v) => !v)}
      >
        {opened
          ? "Hide possible identity links"
          : "Find possible identity links"}
      </Button>
      {opened && (
        <>
          <p>
            Compare unlinked source names with names on already reviewed
            payments, ignoring only case and extra spaces. These are
            suggestions, not identity decisions. Explicitly cleared links stay
            cleared.
          </p>
          <p>
            {suggestions.length} name groups with possible links. Review
            originals and enter your reason before saving.
          </p>
          {suggestions
            .slice(safePage * 10, (safePage + 1) * 10)
            .map((group) => (
              <div key={group.key} className="space-y-2 rounded border p-2">
                <p>
                  Source names:{" "}
                  {group.labels.map((s) => JSON.stringify(s)).join(" · ")}
                </p>
                <p>
                  {group.readings.length} unlinked readings ·{" "}
                  {group.alternatives.length} possible reviewed{" "}
                  {group.alternatives.length === 1 ? "party" : "parties"}
                </p>
                {group.alternatives.length > 1 && (
                  <p>
                    Conflicting reviewed identities share this name. Choose only
                    after inspecting their sources.
                  </p>
                )}
                {group.alternatives.map((alternative) => (
                  <div key={alternative.party.id}>
                    <p>
                      {alternative.party.name} · {alternative.anchors.length}{" "}
                      reviewed supporting readings
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        disabled={disabled}
                        onClick={() =>
                          onSource(alternative.anchors[0].transaction_id)
                        }
                      >
                        Inspect supporting source{" "}
                        {alternative.anchors[0].ref_id}
                      </Button>
                      <Button
                        variant="outline"
                        disabled={disabled}
                        onClick={() =>
                          onSelect(
                            group.readings
                              .slice(0, 100)
                              .map((r) => r.transaction_id),
                            alternative.party.id
                          )
                        }
                      >
                        Review {Math.min(group.readings.length, 100)} possible
                        links to {alternative.party.name}
                      </Button>
                    </div>
                  </div>
                ))}
                <Button
                  variant="outline"
                  disabled={disabled}
                  onClick={() => onSource(group.readings[0].transaction_id)}
                >
                  Inspect unlinked source {group.readings[0].ref_id}
                </Button>
                {group.readings.length > 100 && (
                  <p>
                    Only the first100readings will be selected. Remaining
                    readings stay unselected for a later review.
                  </p>
                )}
              </div>
            ))}
          {suggestions.length > 10 && (
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                disabled={safePage === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous identity suggestions
              </Button>
              <span>
                {safePage * 10 + 1}–
                {Math.min((safePage + 1) * 10, suggestions.length)} of{" "}
                {suggestions.length}
              </span>
              <Button
                variant="outline"
                disabled={(safePage + 1) * 10 >= suggestions.length}
                onClick={() => setPage((p) => p + 1)}
              >
                Next identity suggestions
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  )
}
