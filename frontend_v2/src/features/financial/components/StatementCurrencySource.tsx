import { useState, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { TransactionSourceHighlight } from "./TransactionSourceHighlight"

/** Keep the original available before a currency-dependent review can load. */
export function StatementCurrencySource({
  fileId,
  filename,
  pages,
  children,
}: {
  fileId: string
  filename: string
  pages: number[]
  children: ReactNode
}) {
  const available = pages.length ? pages : [1]
  const [selected, setSelected] = useState(available[0])
  const page = available.includes(selected) ? selected : available[0]
  const index = available.indexOf(page)
  return (
    <section aria-label="Check statement currency" className="space-y-4">
      <div className="rounded border p-4 space-y-2">
        <h3 className="font-semibold">Check the currency in the original</h3>
        <p className="text-sm break-words">{filename}</p>
        <p className="text-sm">
          Loupe could not identify the currency confidently. Check the account
          section in the PDF below, then choose its currency to continue
          reviewing.
        </p>
        {children}
      </div>
      <div
        role="group"
        aria-label="Currency source pages"
        className="flex flex-wrap items-center gap-2"
      >
        <Button
          variant="outline"
          disabled={index === 0}
          onClick={() => setSelected(available[index - 1])}
        >
          Previous page
        </Button>
        <label>
          PDF page{" "}
          <select
            aria-label="Currency source page"
            value={page}
            onChange={(event) => setSelected(Number(event.target.value))}
            className="rounded border bg-background p-2"
          >
            {available.map((number) => (
              <option key={number} value={number}>
                {number}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="outline"
          disabled={index === available.length - 1}
          onClick={() => setSelected(available[index + 1])}
        >
          Next page
        </Button>
      </div>
      <TransactionSourceHighlight
        sourceDocumentId={fileId}
        locatorPayload={{ kind: "page_only", page }}
        wholePage
      />
    </section>
  )
}
