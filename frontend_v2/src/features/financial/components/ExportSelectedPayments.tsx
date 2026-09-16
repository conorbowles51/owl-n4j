import { useMutation } from "@tanstack/react-query"
import { formatLedgerAmount } from "../lib/ledger-format"
import { Button } from "@/components/ui/button"
import { readSelectedPayments } from "../lib/selected-payment-source"

export function ExportSelectedPayments({
  caseId,
  ids,
}: {
  caseId: string
  ids: string[]
}) {
  const download = useMutation({
    retry: false,
    mutationFn: async () => {
      const records = []
      for (let offset = 0; offset < ids.length; offset += 500)
        records.push(
          ...(await readSelectedPayments(
            caseId,
            ids.slice(offset, offset + 500)
          ))
        )
      const csv = (value: unknown) => {
        let text = value === null || value === undefined ? "" : String(value)
        if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text))
          text = `'${text}`
        return `"${text.replaceAll('"', '""')}"`
      }
      const columns = [
        "payment_id",
        "account",
        "date",
        "date_basis",
        "description",
        "recorded_name",
        "currency",
        "direction",
        "amount",
        "printed_balance",
        "amount_minor",
        "printed_balance_minor",
        "status",
        "replaced_by",
        "source_file",
        "reference",
      ]
      const lines = records.map((source) => {
        const row = source.transaction
        return [
          row.key,
          row.account_label,
          row.ordering_date,
          row.ordering_date_context || row.ordering_date_source,
          row.description,
          row.counterparty_raw,
          row.currency,
          row.direction,
          formatLedgerAmount(row.amount_minor, row.currency).scaled
            ? formatLedgerAmount(
                row.amount_minor,
                row.currency
              ).text.replaceAll(",", "")
            : "Unknown currency scale; see amount_minor",
          row.running_balance_minor === null
            ? ""
            : formatLedgerAmount(row.running_balance_minor, row.currency).scaled
              ? formatLedgerAmount(
                  row.running_balance_minor,
                  row.currency
                ).text.replaceAll(",", "")
              : "Unknown currency scale; see printed_balance_minor",
          row.amount_minor,
          row.running_balance_minor,
          source.ledger_status,
          source.superseded_by_id,
          source.filename,
          source.ref_id,
        ]
          .map(csv)
          .join(",")
      })
      const url = URL.createObjectURL(
        new Blob([[columns.map(csv).join(","), ...lines].join("\r\n")], {
          type: "text/csv;charset=utf-8",
        })
      )
      const anchor = document.createElement("a")
      anchor.href = url
      anchor.download = `financial-selected-payments-${caseId}.csv`
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
  })
  return (
    <div>
      <Button
        variant="outline"
        disabled={!ids.length || download.isPending}
        onClick={() => download.mutate()}
      >
        {download.isPending
          ? "Preparing selected payments…"
          : "Export selected"}
      </Button>
      {download.isError && (
        <p role="alert" className="text-sm">
          {download.error.message}
        </p>
      )}
    </div>
  )
}
