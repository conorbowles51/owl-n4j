import { useState } from "react"
import { correctionMinor, correctionMoney } from "../lib/correction-contract"
import type { LedgerTransaction } from "../api"

export type TransferParts = Record<string, { principal: string; fee: string }>

export function TransferPartsEditor({
  rows,
  value,
  onChange,
  search,
}: {
  rows: LedgerTransaction[]
  value: TransferParts
  onChange: (value: TransferParts) => void
  search: string
}) {
  const [limit, setLimit] = useState(100)
  const visible = rows.filter(
    (p) =>
      p.key in value ||
      `${p.description} ${p.account_label} ${p.ref_id} ${p.ordering_date}`
        .toLowerCase()
        .includes(search.toLowerCase())
  )
  return (
    <fieldset className="rounded border p-3 space-y-3">
      <legend>Transfer principal and fees</legend>
      <p>
        Select all sending and receiving entries. Assign the part of each entry
        belonging to this transfer. For a separate fee, set principal to zero.
        Unassigned money remains available for another reviewed link.
      </p>
      <div className="max-h-80 overflow-auto space-y-3">
        {visible
          .filter((p, index) => index < limit || p.key in value)
          .map((p) => {
            const part = value[p.key]
            const principal = part
              ? correctionMinor(part.principal, p.currency)
              : null
            const fee = part ? correctionMinor(part.fee, p.currency) : null
            const rest =
              principal !== null &&
              fee !== null &&
              principal !== "" &&
              fee !== ""
                ? BigInt(p.amount_minor) - BigInt(principal) - BigInt(fee)
                : null
            return (
              <div key={p.key} className="rounded border p-2 space-y-2">
                <label className="flex gap-2 items-start">
                  <input
                    type="checkbox"
                    aria-label={`Include ${p.ref_id} in transfer`}
                    checked={!!part}
                    onChange={(e) => {
                      const next = { ...value }
                      if (e.target.checked)
                        next[p.key] = {
                          principal: correctionMoney(
                            String(p.amount_minor),
                            p.currency
                          ).split(" ")[0],
                          fee: "0",
                        }
                      else delete next[p.key]
                      onChange(next)
                    }}
                  />
                  <span>
                    {p.ordering_date} ·{" "}
                    {p.direction === "debit" ? "Money out" : "Money in"} ·{" "}
                    {correctionMoney(String(p.amount_minor), p.currency)} ·{" "}
                    {p.account_label} · {p.description || p.ref_id}
                  </span>
                </label>
                {part && (
                  <>
                    <div className="flex flex-wrap gap-3">
                      <label>
                        Principal ({p.currency})
                        <input
                          aria-label={`Principal for ${p.ref_id}`}
                          className="block w-40 rounded border bg-background p-2"
                          inputMode="decimal"
                          value={part.principal}
                          onChange={(e) =>
                            onChange({
                              ...value,
                              [p.key]: { ...part, principal: e.target.value },
                            })
                          }
                        />
                      </label>
                      {p.direction === "debit" && (
                        <label>
                          Fee included in this debit ({p.currency})
                          <input
                            aria-label={`Fee for ${p.ref_id}`}
                            className="block w-40 rounded border bg-background p-2"
                            inputMode="decimal"
                            value={part.fee}
                            onChange={(e) =>
                              onChange({
                                ...value,
                                [p.key]: { ...part, fee: e.target.value },
                              })
                            }
                          />
                        </label>
                      )}
                    </div>
                    <p
                      className={
                        rest !== null && rest < 0n
                          ? "text-destructive"
                          : "text-muted-foreground"
                      }
                    >
                      Unassigned in this link:{" "}
                      {rest === null
                        ? "Enter valid amounts"
                        : correctionMoney(String(rest), p.currency)}
                      . The preview also checks other saved links.
                    </p>
                  </>
                )}
              </div>
            )
          })}
      </div>
      {visible.length > limit && (
        <button
          type="button"
          className="underline"
          onClick={() => setLimit((n) => n + 100)}
        >
          Show 100 more matching entries ({visible.length} total)
        </button>
      )}
      <p>
        Use the reason below to identify the evidence for fees and split
        amounts. Separate currencies are retained; an exchange hypothesis must
        be selected explicitly.
      </p>
    </fieldset>
  )
}
