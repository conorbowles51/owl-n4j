import { useState } from "react"
import { Button } from "@/components/ui/button"
import {
  statementScope,
  signedControlMinor,
  type StatementScope,
  type ScopeReading,
  type ControlCell,
} from "../lib/statement-scope-contract"
import {
  StatementEditorDraftPanel,
  type EditorDraft,
} from "./StatementEditorDraftPanel"
import { StatementControlPicker } from "./StatementControlPicker"
const labels = {
  start: "statement start",
  end: "statement end",
  opening: "opening balance",
  closing: "closing balance",
} as const
type Role = keyof typeof labels
export function StatementScopeEditor({
  caseId,
  fileId,
  readings,
  onSave,
  onClose,
}: {
  caseId: string
  fileId: string
  readings: ScopeReading[]
  onSave: (scope: StatementScope) => void
  onClose: () => void
}) {
  const [group, setGroup] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [opening, setOpening] = useState(""),
    [closing, setClosing] = useState(""),
    [convention, setConvention] = useState(""),
    [reason, setReason] = useState("")
  const [cells, setCells] = useState<Partial<Record<Role, ControlCell>>>({}),
    [picking, setPicking] = useState<Role | null>(null)
  const groups = [
    ...new Map(
      readings.map((row) => [`${row.account_id}:${row.currency}`, row])
    ).entries(),
  ]
  const account = groups.find(([key]) => key === group)?.[1]
  const matching = readings.filter(
    (row) => `${row.account_id}:${row.currency}` === group
  )
  const draft = statementScope.safeParse({
    account_id: account?.account_id,
    currency: account?.currency,
    candidate_ids: selected.every((id) =>
      matching.some((row) => row.candidate_id === id)
    )
      ? selected
      : [],
    start: { value: start, source: cells.start },
    end: { value: end, source: cells.end },
    opening: opening
      ? {
          amount_minor: signedControlMinor(opening, account?.currency ?? ""),
          source: cells.opening,
        }
      : null,
    closing: closing
      ? {
          amount_minor: signedControlMinor(closing, account?.currency ?? ""),
          source: cells.closing,
        }
      : null,
    balance_convention: convention,
    reason,
  })
  return (
    <section
      className="space-y-3 rounded border p-3"
      aria-label="Review statement controls"
    >
      <StatementEditorDraftPanel
        caseId={caseId}
        fileId={fileId}
        value={{
          group,
          selected,
          start,
          end,
          opening,
          closing,
          convention: convention as EditorDraft["convention"],
          reason,
          cells,
        }}
        onLoad={(saved) => {
          setGroup(saved.group)
          setSelected(saved.selected)
          setStart(saved.start)
          setEnd(saved.end)
          setOpening(saved.opening)
          setClosing(saved.closing)
          setConvention(saved.convention)
          setReason(saved.reason)
          setCells(saved.cells)
          setPicking(null)
        }}
      />
      {selected.some(
        (id) => !matching.some((row) => row.candidate_id === id)
      ) && (
        <p role="alert">
          Some saved rows are no longer available for this statement. Choose the
          account and rows again before adding controls.
        </p>
      )}
      <h4 className="font-semibold">Review statement dates and balances</h4>
      <p>
        Assign selected reviewed rows to one printed statement period. This
        records your reading and its sources; it does not establish complete
        extraction or raise P3 eligibility.
      </p>
      <label className="block">
        Statement account
        <select
          aria-label="Statement account"
          value={group}
          onChange={(e) => {
            setGroup(e.target.value)
            setSelected([])
            setOpening("")
            setClosing("")
          }}
          className="block w-full rounded border bg-background p-2"
        >
          <option value="">Choose account and currency</option>
          {groups.map(([key, row]) => (
            <option value={key} key={key}>
              {row.account_label} · {row.currency}
            </option>
          ))}
        </select>
      </label>
      <fieldset className="max-h-52 space-y-1 overflow-auto rounded border p-2">
        <legend>Reviewed rows in this statement</legend>
        {matching.map((row, index) => (
          <label key={row.candidate_id} className="flex gap-2">
            <input
              type="checkbox"
              aria-label={`Assign reviewed row ${index + 1} to statement`}
              checked={selected.includes(row.candidate_id)}
              onChange={(e) =>
                setSelected((v) =>
                  e.target.checked
                    ? [...v, row.candidate_id]
                    : v.filter((id) => id !== row.candidate_id)
                )
              }
            />
            <span>
              {row.booking_date ?? row.transaction_date ?? "Unknown date"} ·{" "}
              {row.description ?? "No description"}
            </span>
          </label>
        ))}
        {!matching.length && (
          <p>Choose an account to see its unassigned reviewed rows.</p>
        )}
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <label>
          Printed statement start
          <input
            aria-label="Printed statement start"
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="block w-full rounded border bg-background p-2"
          />
        </label>
        <label>
          Printed statement end
          <input
            aria-label="Printed statement end"
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="block w-full rounded border bg-background p-2"
          />
        </label>
        <label>
          Printed opening balance
          <input
            aria-label="Printed opening balance"
            value={opening}
            onChange={(e) => setOpening(e.target.value)}
            inputMode="decimal"
            className="block w-full rounded border bg-background p-2"
          />
        </label>
        <label>
          Printed closing balance
          <input
            aria-label="Printed closing balance"
            value={closing}
            onChange={(e) => setClosing(e.target.value)}
            inputMode="decimal"
            className="block w-full rounded border bg-background p-2"
          />
        </label>
      </div>
      <p className="text-sm">
        Leave an unprinted balance blank. Blank means unknown, not zero. Enter
        decimal amounts without currency symbols or thousands separators,
        keeping a minus sign where printed.
      </p>
      <label className="block">
        What do the printed balances represent?
        <select
          aria-label="Printed balance convention"
          value={convention}
          onChange={(e) => setConvention(e.target.value)}
          className="block w-full rounded border bg-background p-2"
        >
          <option value="">Choose from the statement</option>
          <option value="asset_balance">Money held in the account</option>
          <option value="liability_owed">Money owed to the issuer</option>
        </select>
      </label>
      {convention === "liability_owed" && (
        <p className="text-sm">
          Amounts owed become negative ledger balances. The original printed
          amounts and this choice are retained.
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {(Object.keys(labels) as Role[])
          .filter(
            (role) =>
              role === "start" ||
              role === "end" ||
              (role === "opening" ? opening : closing)
          )
          .map((role) => (
            <div key={role} className="space-y-1">
              <Button variant="outline" onClick={() => setPicking(role)}>
                Choose source for {labels[role]}
              </Button>
              {cells[role] && (
                <p className="text-sm break-words">
                  Page {cells[role]!.page_number}: {cells[role]!.expected_text}
                </p>
              )}
            </div>
          ))}
      </div>
      {picking && (
        <StatementControlPicker
          key={picking}
          caseId={caseId}
          fileId={fileId}
          label={labels[picking]}
          onClose={() => setPicking(null)}
          onSelected={(cell) => {
            setCells((v) => ({ ...v, [picking]: cell }))
            setPicking(null)
          }}
        />
      )}
      <label className="block">
        Reason for statement control readings
        <textarea
          aria-label="Reason for statement control readings"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={4096}
          className="block w-full rounded border bg-background p-2"
        />
      </label>
      <div className="flex gap-2">
        <Button
          disabled={!draft.success}
          onClick={() => {
            if (draft.success) onSave(draft.data)
          }}
        >
          Add statement to preview
        </Button>
        <Button variant="outline" onClick={onClose}>
          Cancel statement controls
        </Button>
      </div>
      {!draft.success && (
        <p className="text-sm">
          Choose rows, valid dates, the balance convention, source cells for
          both dates and any entered balances, and a review reason.
        </p>
      )}
    </section>
  )
}
