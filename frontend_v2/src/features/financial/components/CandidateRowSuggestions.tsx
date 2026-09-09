import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl, assertCandidateScope } from "../lib/candidate-contract"

type Source = {
  case_id: string
  evidence_file_id: string
  page_number: number
  table_index: number
  source_revision: string
  rows: {
    row_index: number
    cells: { column_index: number; expected_text: string }[]
  }[]
}
const cell = z
  .object({
    column_index: z.number().int().nonnegative(),
    expected_text: z.string(),
  })
  .nullable()
const answer = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  page_number: z.number().int(),
  table_index: z.number().int(),
  source_revision: z.string(),
  date_column: z.number().int(),
  amount_column: z.number().int(),
  currency: z.string(),
  currency_source: z.literal("caller_supplied"),
  checked_rows: z.number().int().nonnegative(),
  suggested_rows: z.number().int().nonnegative(),
  applied: z.literal(false),
  requires_source_review: z.literal(true),
  limitation: z.string(),
  rows: z
    .array(
      z.object({
        row_index: z.number().int().nonnegative(),
        suggested: z.boolean(),
        reason: z.string(),
        date_source: cell,
        amount_source: cell,
        date_assessment: z
          .object({ status: z.string(), explanation: z.string() })
          .nullable(),
        amount_assessment: z.object({ explanation: z.string() }).nullable(),
        amount_error: z.string().nullable(),
      })
    )
    .max(1000),
})
export function CandidateRowSuggestions({
  source,
  columns,
  onSelect,
}: {
  source: Source
  columns: Record<number, string>
  onSelect: (rows: number[]) => void
}) {
  return (
    <Suggestions
      key={JSON.stringify([source.source_revision, columns])}
      source={source}
      columns={columns}
      onSelect={onSelect}
    />
  )
}
function Suggestions({
  source,
  columns,
  onSelect,
}: {
  source: Source
  columns: Record<number, string>
  onSelect: (rows: number[]) => void
}) {
  const [dateColumn, setDateColumn] = useState(""),
    [amountColumn, setAmountColumn] = useState(""),
    [currency, setCurrency] = useState(""),
    [page, setPage] = useState(0)
  const suggestion = useMutation({
    retry: false,
    mutationFn: async () => {
      const data = answer.parse(
        await fetchAPI<unknown>(
          `${candidateUrl(`candidate-sources/${source.evidence_file_id}/pages/${source.page_number}/row-suggestions`, source.case_id)}&table_index=${source.table_index}`,
          {
            method: "POST",
            body: {
              expected_revision: source.source_revision,
              date_column: Number(dateColumn),
              amount_column: Number(amountColumn),
              currency,
            },
          }
        )
      )
      assertCandidateScope(data, source.case_id)
      if (
        data.evidence_file_id !== source.evidence_file_id ||
        data.source_revision !== source.source_revision ||
        data.page_number !== source.page_number ||
        data.table_index !== source.table_index ||
        data.date_column !== Number(dateColumn) ||
        data.amount_column !== Number(amountColumn) ||
        data.currency !== currency
      )
        throw new Error(
          "Suggestions returned for a different source or input. Reload the table."
        )
      if (
        data.checked_rows !== source.rows.length ||
        data.rows.length !== source.rows.length ||
        new Set(data.rows.map((r) => r.row_index)).size !==
          source.rows.length ||
        data.suggested_rows !== data.rows.filter((r) => r.suggested).length
      )
        throw new Error("Suggestion coverage does not match the stored rows.")
      for (const row of data.rows) {
        const original = source.rows.find((r) => r.row_index === row.row_index)
        if (!original) throw new Error("An unknown source row was returned.")
        for (const [column, value] of [
          [data.date_column, row.date_source],
          [data.amount_column, row.amount_source],
        ] as const) {
          const expected = original.cells.find((c) => c.column_index === column)
          if (
            expected
              ? !value ||
                value.column_index !== column ||
                value.expected_text !== expected.expected_text
              : value !== null
          )
            throw new Error("Suggested source text changed. Reload the table.")
        }
      }
      return data
    },
  })
  const change = () => {
    suggestion.reset()
    setPage(0)
  }
  const dates = Object.entries(columns).filter(([, role]) =>
    ["booking_date", "value_date", "transaction_date"].includes(role)
  )
  const amounts = Object.entries(columns).filter(([, role]) =>
    ["amount", "credit", "debit"].includes(role)
  )
  return (
    <section
      aria-label="Suggest rows for review"
      className="space-y-2 rounded border p-3"
    >
      <h3>Suggest rows for review</h3>
      <p>
        First identify date and amount column meanings above. Suggestions use
        those columns and your currency context; they do not establish which
        rows are transactions. All rows remain available for manual selection.
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <label>
          Date column for suggestions
          <select
            className="mt-1 block w-full rounded border bg-background p-2"
            value={dateColumn}
            disabled={suggestion.isPending}
            onChange={(e) => {
              change()
              setDateColumn(e.target.value)
            }}
          >
            <option value="">Choose date column</option>
            {dates.map(([index]) => (
              <option key={index} value={index}>
                Column {Number(index) + 1}
              </option>
            ))}
          </select>
        </label>
        <label>
          Amount column for suggestions
          <select
            className="mt-1 block w-full rounded border bg-background p-2"
            value={amountColumn}
            disabled={suggestion.isPending}
            onChange={(e) => {
              change()
              setAmountColumn(e.target.value)
            }}
          >
            <option value="">Choose amount column</option>
            {amounts.map(([index]) => (
              <option key={index} value={index}>
                Column {Number(index) + 1}
              </option>
            ))}
          </select>
        </label>
        <label>
          Currency context for suggestions
          <input
            className="mt-1 block w-full rounded border bg-background p-2"
            value={currency}
            maxLength={3}
            disabled={suggestion.isPending}
            onChange={(e) => {
              change()
              setCurrency(e.target.value.toUpperCase())
            }}
            placeholder="e.g. GBP"
          />
        </label>
      </div>
      <Button
        disabled={
          suggestion.isPending ||
          dateColumn === "" ||
          amountColumn === "" ||
          !/^[A-Z]{3}$/.test(currency)
        }
        onClick={() => suggestion.mutate()}
      >
        Inspect row suggestions
      </Button>
      {suggestion.isPending && <p role="status">Checking stored rows…</p>}
      {suggestion.isError && (
        <p role="alert">Suggestions unavailable. {suggestion.error.message}</p>
      )}
      {suggestion.data && (
        <>
          <p>{suggestion.data.limitation}</p>
          <p>
            {suggestion.data.suggested_rows} suggested from{" "}
            {suggestion.data.checked_rows} checked rows.
          </p>
          {suggestion.data.rows.slice(page * 25, page * 25 + 25).map((row) => (
            <article key={row.row_index} className="rounded border p-2">
              <p>
                Source row {row.row_index + 1}:{" "}
                {row.suggested
                  ? "Suggested for inspection"
                  : "No date-and-amount suggestion"}
              </p>
              <p>
                Date text: {row.date_source?.expected_text ?? "Not recorded"} ·
                Amount text:{" "}
                {row.amount_source?.expected_text ?? "Not recorded"}
              </p>
              <p>{row.reason}</p>
              <p>{row.date_assessment?.explanation}</p>
              <p>{row.amount_assessment?.explanation ?? row.amount_error}</p>
            </article>
          ))}
          <Button disabled={page === 0} onClick={() => setPage(page - 1)}>
            Previous suggestion rows
          </Button>
          <Button
            disabled={(page + 1) * 25 >= suggestion.data.rows.length}
            onClick={() => setPage(page + 1)}
          >
            Next suggestion rows
          </Button>
          <Button
            disabled={!suggestion.data.suggested_rows}
            onClick={() =>
              onSelect(
                suggestion.data.rows
                  .filter((r) => r.suggested)
                  .map((r) => r.row_index)
              )
            }
          >
            Add suggested rows to review selection
          </Button>
          <p>
            This only changes the selection. Check the source before saving
            pending readings.
          </p>
        </>
      )}
    </section>
  )
}
