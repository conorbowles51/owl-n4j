import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { fetchAPI } from "@/lib/api-client"
import { candidateUrl } from "../lib/candidate-contract"
const index = z.number().int().nonnegative(),
  cell = z.object({ expected_text: z.string(), column_index: index })
const resultSchema = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  start_page: index,
  end_page: index,
  table_index: index,
  date_column: index.nullable(),
  amount_column: index.nullable(),
  auto_columns: z.boolean().default(false),
  currency: z.string(),
  applied: z.literal(false),
  limitation: z.string(),
  suggested_rows: index,
  undated_charge_rows: index.default(0),
  pages: z
    .array(
      z.object({
        page_number: index,
        checked: z.boolean(),
        reason: z.string().nullable(),
        checked_rows: index,
        chosen_columns: z
          .object({
            date_column: index,
            amount_column: index,
            additional_amount_columns: z.array(index).max(1).default([]),
            supporting_rows: index.optional(),
            header_support: index.optional(),
          })
          .optional(),
        source_section: z
          .object({
            start_row: index,
            end_row: index,
            start_source: cell,
            end_source: cell,
            omitted_rows: index,
            limitation: z.string(),
          })
          .refine((v) => v.end_row > v.start_row + 1)
          .nullable()
          .optional(),
        other_tables: index.optional(),
        source_revision: z.string().optional(),
        undated_checked_rows: index.optional(),
        undated_charges: z
          .array(
            z.object({
              row_index: index,
              label_source: cell,
              amount_sources: z.array(cell).min(1),
              date_unknown: z.literal(true),
              reason: z.string(),
            })
          )
          .default([]),
        suggestions: z.array(
          z.object({
            row_index: index,
            date_source: cell,
            amount_source: cell,
            amount_header_source: cell.optional(),
          })
        ),
      })
    )
    .max(50),
})
export function CandidatePageScan({
  caseId,
  fileId,
  onPage,
}: {
  caseId: string
  fileId: string
  onPage: (page: number) => void
}) {
  const [opened, setOpened] = useState(false),
    [automatic, setAutomatic] = useState(false),
    [start, setStart] = useState("1"),
    [end, setEnd] = useState("10"),
    [date, setDate] = useState("1"),
    [amount, setAmount] = useState("2"),
    [currency, setCurrency] = useState("")
  const scan = useMutation({
    retry: false,
    mutationFn: async () => {
      const params = {
        start_page: Number(start),
        end_page: Number(end),
        ...(automatic
          ? { auto_columns: true }
          : {
              date_column: Number(date) - 1,
              amount_column: Number(amount) - 1,
            }),
        table_index: 0,
        currency,
      }
      const data = resultSchema.parse(
        await fetchAPI(
          `${candidateUrl(`candidate-sources/${encodeURIComponent(fileId)}/page-scan`, caseId)}&${new URLSearchParams(Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)])))}`,
          { timeout: 120000 }
        )
      )
      if (
        data.case_id !== caseId ||
        data.evidence_file_id !== fileId ||
        Object.entries(params).some(
          ([k, v]) => data[k as keyof typeof data] !== v
        ) ||
        data.pages.length !== params.end_page - params.start_page + 1 ||
        data.pages.some(
          (p, i) =>
            p.page_number !== params.start_page + i ||
            (p.source_section &&
              (!automatic ||
                [...p.suggestions, ...p.undated_charges].some(
                  (r) =>
                    r.row_index <= p.source_section!.start_row ||
                    r.row_index >= p.source_section!.end_row
                )))
        ) ||
        data.undated_charge_rows !==
          data.pages.reduce((n, p) => n + p.undated_charges.length, 0) ||
        data.suggested_rows !==
          data.pages.reduce((n, p) => n + p.suggestions.length, 0)
      )
        throw Error("Page scan returned a different or incomplete scope.")
      return data
    },
  })
  return (
    <section
      aria-label="Scan PDF pages for possible transactions"
      className="space-y-3 rounded border p-3"
    >
      <Button variant="outline" onClick={() => setOpened((v) => !v)}>
        {opened
          ? "Hide page-range scan"
          : "Find possible rows across PDF pages"}
      </Button>
      {opened && (
        <>
          <p>
            Scan table 1 on up to 50 pages. Use chosen column positions or
            propose them separately on each page. Inspect each result and its
            original. Recognised undated fees and interest appear separately for
            review; no date or direction is inferred.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              scan.mutate()
            }}
            onChange={() => scan.reset()}
          >
            <fieldset
              disabled={scan.isPending}
              className="flex flex-wrap gap-3"
            >
              <label className="w-full">
                <input
                  type="checkbox"
                  aria-label="Propose columns on each page"
                  checked={automatic}
                  onChange={(e) => setAutomatic(e.target.checked)}
                />{" "}
                Propose columns on each page; leave ambiguous layouts for manual
                review
              </label>
              <label>
                Scan from page
                <input
                  aria-label="Scan from page"
                  type="number"
                  min="1"
                  required
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                  className="block w-24 border bg-background p-2"
                />
              </label>
              <label>
                Scan through page
                <input
                  aria-label="Scan through page"
                  type="number"
                  min={start}
                  max={Number(start) + 49}
                  required
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                  className="block w-24 border bg-background p-2"
                />
              </label>
              <label>
                Possible date column
                <input
                  aria-label="Possible date column"
                  disabled={automatic}
                  type="number"
                  min="1"
                  max="64"
                  required
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="block w-24 border bg-background p-2"
                />
              </label>
              <label>
                Possible amount column
                <input
                  aria-label="Possible amount column"
                  disabled={automatic}
                  type="number"
                  min="1"
                  max="64"
                  required
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="block w-24 border bg-background p-2"
                />
              </label>
              <label>
                Scan currency
                <input
                  aria-label="Scan currency"
                  pattern="[A-Z]{3}"
                  maxLength={3}
                  required
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="block w-24 border bg-background p-2"
                />
              </label>
              <Button type="submit" disabled={!automatic && date === amount}>
                {scan.isPending
                  ? "Scanning pages…"
                  : "Scan selected page range"}
              </Button>
            </fieldset>
          </form>
          {scan.isError && (
            <p role="alert">Page scan unavailable. {scan.error.message}</p>
          )}
          {scan.data && (
            <>
              <p>
                {scan.data.suggested_rows} possible rows across{" "}
                {scan.data.pages.filter((p) => p.checked).length} checked pages;{" "}
                {scan.data.pages.filter((p) => !p.checked).length} pages not
                checked.
              </p>
              <p>{scan.data.limitation}</p>
              <ul className="max-h-96 space-y-3 overflow-auto">
                {scan.data.pages.map((p) => (
                  <li key={p.page_number} className="rounded border p-2">
                    <p>
                      Page {p.page_number}:{" "}
                      {p.checked
                        ? `${p.suggestions.length} possible rows from ${p.checked_rows} rows checked`
                        : p.reason}
                    </p>
                    {p.source_section && (
                      <p>
                        Printed section: “
                        {p.source_section.start_source.expected_text}” (row{" "}
                        {p.source_section.start_row + 1}) through “
                        {p.source_section.end_source.expected_text}” (row{" "}
                        {p.source_section.end_row + 1}).{" "}
                        {p.source_section.omitted_rows} other rows remain
                        outside this scan. {p.source_section.limitation}
                      </p>
                    )}
                    {p.chosen_columns && (
                      <p>
                        Date column {p.chosen_columns.date_column + 1}, amount
                        column {p.chosen_columns.amount_column + 1}
                        {p.chosen_columns.additional_amount_columns
                          .map((c) => `, additional amount column ${c + 1}`)
                          .join("")}
                        {p.chosen_columns.supporting_rows !== undefined &&
                          ` · ${p.chosen_columns.supporting_rows} supporting rows; ${p.chosen_columns.header_support ?? 0} recognised column labels`}
                        . Review these positions before selecting readings.
                      </p>
                    )}
                    {!!p.other_tables && (
                      <p>
                        {p.other_tables} other stored tables on this page were
                        not scanned.
                      </p>
                    )}
                    {p.suggestions.slice(0, 3).map((r) => (
                      <p key={`${r.row_index}:${r.amount_source.column_index}`}>
                        Row {r.row_index + 1}: {r.date_source.expected_text} ·{" "}
                        {r.amount_source.expected_text}
                        {r.amount_header_source &&
                          ` · source header “${r.amount_header_source.expected_text}” (review direction)`}
                      </p>
                    ))}
                    {p.suggestions.length > 3 && (
                      <p>
                        {p.suggestions.length - 3} more suggestions on this
                        page.
                      </p>
                    )}
                    {p.undated_checked_rows !== undefined && (
                      <p>
                        Undated charge screen: {p.undated_charges.length}{" "}
                        possible rows from {p.undated_checked_rows} stored rows.
                      </p>
                    )}
                    {p.undated_charges.map((r) => (
                      <div
                        key={`undated-${r.row_index}`}
                        className="space-y-1 rounded border p-2"
                      >
                        <p>
                          Undated row {r.row_index + 1}:{" "}
                          {r.label_source.expected_text}
                        </p>
                        <p>
                          {r.amount_sources
                            .map(
                              (c) =>
                                `Column ${c.column_index + 1}: ${c.expected_text}`
                            )
                            .join(" · ")}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {r.reason}
                        </p>
                      </div>
                    ))}
                    <Button
                      variant="outline"
                      onClick={() => onPage(p.page_number)}
                    >
                      Inspect PDF page {p.page_number}
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  )
}
