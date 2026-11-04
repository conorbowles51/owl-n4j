import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { FileDown, Receipt } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { caseCostsAPI } from "../costs-api"

const money = (value: string | number) =>
  Number(value).toLocaleString(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2 })
const day = (value: string | null) => (value ? value.slice(0, 10) : "")

/**
 * The case's AI costs for billing (FEAT-007): one line per document, batch, conversation or kind of work, the case
 * named on the report, a PDF to send. Shown to the case's manager (the owner) and admins; the server refuses others.
 */
export function CaseCostsSection({ caseId, caseTitle }: { caseId: string; caseTitle: string }) {
  const [start, setStart] = useState("")
  const [end, setEnd] = useState("")
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [making, setMaking] = useState(false)
  const report = useQuery({
    queryKey: ["case-costs", caseId, start, end],
    queryFn: () => caseCostsAPI.report(caseId, start || undefined, end || undefined),
  })
  const data = report.data
  return (
    <Card className="mt-6 gap-4 p-5" aria-labelledby="case-costs-title">
      <CardHeader className="grid-cols-[auto_1fr] grid-rows-[auto_auto] gap-x-3">
        <div className="row-span-2 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
          <Receipt className="size-4" />
        </div>
        <CardTitle id="case-costs-title" className="self-end text-base">
          AI costs for this case
        </CardTitle>
        <CardDescription>
          One line per document or conversation, for billing {caseTitle}. Each line adds up the individual AI calls made
          for it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="case-costs-start">From</Label>
            <Input id="case-costs-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="case-costs-end">To</Label>
            <Input id="case-costs-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>
          <Button
            variant="outline"
            disabled={making || !data}
            onClick={async () => {
              setPdfError(null)
              setMaking(true)
              try {
                await caseCostsAPI.downloadPdf(caseId, start || undefined, end || undefined)
              } catch (error) {
                setPdfError((error as Error).message)
              } finally {
                setMaking(false)
              }
            }}
          >
            <FileDown className="size-3.5" />
            {making ? "Making the PDF..." : "Download PDF"}
          </Button>
        </div>
        {pdfError && (
          <p role="alert" className="text-sm text-destructive">
            {pdfError}
          </p>
        )}
        {report.isLoading && <p className="text-sm text-muted-foreground">Adding up this case's AI costs...</p>}
        {report.isError && (
          <p role="alert" className="text-sm text-destructive">
            {(report.error as Error).message || "The costs could not be read."}
          </p>
        )}
        {data && (
          <>
            <p className="text-sm" data-testid="case-costs-total">
              <strong>{money(data.total_cost_exact)}</strong> over {data.line_count.toLocaleString()}{" "}
              {data.line_count === 1 ? "line" : "lines"} ({data.call_count.toLocaleString()} AI calls)
            </p>
            {data.lines.length === 0 ? (
              <p className="text-sm text-muted-foreground">No AI costs are recorded for this case in these dates.</p>
            ) : (
              <div className="max-h-[420px] overflow-auto rounded border">
                <table className="w-full text-xs" aria-label="AI costs by document">
                  <thead className="sticky top-0 bg-muted text-left">
                    <tr>
                      <th className="p-2">Work</th>
                      <th className="p-2">Document or item</th>
                      <th className="p-2 text-right">Calls</th>
                      <th className="p-2">Dates</th>
                      <th className="p-2 text-right">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.lines.map((line, index) => (
                      <tr key={line.evidence_file_id ?? `${line.kind}:${line.label}:${index}`} className="border-t align-top">
                        <td className="p-2 whitespace-nowrap">{line.kind}</td>
                        <td className="p-2 break-words" title={line.models.join(", ")}>
                          {line.label}
                        </td>
                        <td className="p-2 text-right tabular-nums">{line.calls.toLocaleString()}</td>
                        <td className="p-2 whitespace-nowrap">
                          {day(line.first_at)}
                          {day(line.last_at) !== day(line.first_at) ? ` to ${day(line.last_at)}` : ""}
                        </td>
                        <td className="p-2 text-right tabular-nums">{money(line.cost_exact)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
