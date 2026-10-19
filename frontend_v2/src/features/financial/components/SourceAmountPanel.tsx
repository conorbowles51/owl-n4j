import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { fetchAPI } from "@/lib/api-client"
import { Button } from "@/components/ui/button"
import { sourceSelection } from "../lib/source-selection"
import { correctionMoney } from "../lib/correction-contract"

const textWindow = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  content: z.string(),
  content_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  start_char: z.number().int().nonnegative(),
  end_char: z.number().int().nonnegative(),
  character_count: z.number().int().nonnegative(),
  has_more: z.boolean(),
  offset_unit: z.literal("unicode_code_points"),
})
const assessment = z.object({
  case_id: z.string(),
  evidence_file_id: z.string(),
  content_sha256: z.string(),
  start_char: z.number(),
  end_char: z.number(),
  applied: z.literal(false),
  offset_unit: z.literal("unicode_code_points"),
  currency_source: z.literal("caller_supplied"),
  limitation: z.string(),
  assessment: z.object({
    raw: z.string(),
    currency: z.string(),
    origin: z.enum(["digital_text_layer", "recognised_glyphs", "unknown"]),
    suspicion: z.string(),
    explanation: z.string(),
    minor_units: z
      .string()
      .regex(/^-?\d+$/)
      .optional(),
    proposals: z
      .array(
        z.object({
          minor_units: z.string().regex(/^-?\d+$/),
          basis: z.string(),
        })
      )
      .optional(),
  }),
})

export function SourceAmountPanel({
  caseId,
  evidenceId,
  onClose,
}: {
  caseId: string
  evidenceId: string
  onClose: () => void
}) {
  const [offset, setOffset] = useState(0)
  const [currency, setCurrency] = useState("")
  const [selected, setSelected] =
    useState<ReturnType<typeof sourceSelection>>(null)
  const path = `/api/financial/source-files/${encodeURIComponent(evidenceId)}`
  const source = useQuery({
    queryKey: ["financial-source-text", caseId, evidenceId, offset],
    retry: false,
    queryFn: async () => {
      const data = textWindow.parse(
        await fetchAPI(
          `${path}/text?${new URLSearchParams({ case_id: caseId, start_char: String(offset) })}`
        )
      )
      if (
        data.case_id !== caseId ||
        data.evidence_file_id !== evidenceId ||
        data.start_char !== offset ||
        data.end_char - data.start_char !== Array.from(data.content).length ||
        data.end_char > data.character_count ||
        data.has_more !== data.end_char < data.character_count
      )
        throw new Error(
          "Source text response is inconsistent. Reload the document."
        )
      return data
    },
  })
  const review = useMutation({
    retry: false,
    mutationFn: async (input: {
      start_char: number
      end_char: number
      expected_text: string
      content_sha256: string
      currency: string
    }) => {
      const data = assessment.parse(
        await fetchAPI(
          `${path}/amount-assessment?${new URLSearchParams({ case_id: caseId })}`,
          { method: "POST", body: input }
        )
      )
      if (
        data.case_id !== caseId ||
        data.evidence_file_id !== evidenceId ||
        data.content_sha256 !== input.content_sha256 ||
        data.start_char !== input.start_char ||
        data.end_char !== input.end_char ||
        data.assessment.raw !== input.expected_text ||
        data.assessment.currency !== input.currency ||
        (data.assessment.suspicion !== "none" &&
          data.assessment.minor_units !== undefined)
      )
        throw new Error("Assessment did not match the selected source text.")
      return data
    },
  })
  const move = (next: number) => {
    setOffset(next)
    setSelected(null)
    review.reset()
  }
  return (
    <section
      aria-label="Assess source amount"
      className="space-y-3 rounded border p-3"
    >
      <h3 className="font-semibold">Assess an amount in the source text</h3>
      <p className="text-sm">
        Select the complete amount below, then enter its currency. This checks
        possible readings; it does not change the ledger.
      </p>
      {source.isPending && <p>Loading source text…</p>}
      {source.isError && <p role="alert">{source.error.message}</p>}
      {source.data && (
        <>
          <textarea
            aria-label="Source text"
            readOnly
            value={source.data.content}
            className="h-52 w-full rounded border bg-background p-2 font-mono text-sm"
            disabled={review.isPending}
            onSelect={(event) => {
              setSelected(
                sourceSelection(
                  source.data.content,
                  event.currentTarget.selectionStart,
                  event.currentTarget.selectionEnd
                )
              )
              review.reset()
            }}
          />
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={offset === 0 || review.isPending}
              onClick={() => move(Math.max(0, offset - 12000))}
            >
              Previous section
            </Button>
            <Button
              variant="outline"
              disabled={!source.data.has_more || review.isPending}
              onClick={() => move(source.data.end_char)}
            >
              Next section
            </Button>
          </div>
          <p className="text-sm">
            {selected
              ? `Selected: ${selected.text}`
              : "Select up to 128 characters containing the amount."}
          </p>
          <label className="block text-sm">
            Currency (ISO code)
            <input
              className="ml-2 rounded border bg-background p-2"
              value={currency}
              maxLength={3}
              disabled={review.isPending}
              onChange={(e) => {
                setCurrency(e.target.value.toUpperCase())
                review.reset()
              }}
            />
          </label>
          <Button
            disabled={
              !selected || !/^[A-Z]{3}$/.test(currency) || review.isPending
            }
            onClick={() => {
              if (!selected || !source.data || review.isPending) return
              review.mutate({
                start_char: offset + selected.start,
                end_char: offset + selected.end,
                expected_text: selected.text,
                content_sha256: source.data.content_sha256,
                currency,
              })
            }}
          >
            Assess selected amount
          </Button>
        </>
      )}
      {review.isError && <p role="alert">{review.error.message}</p>}
      {review.data && (
        <div role="status" className="space-y-2 text-sm">
          <p>
            Text origin:{" "}
            {
              {
                digital_text_layer: "Digital text",
                recognised_glyphs: "Recognized from an image",
                unknown: "Unknown",
              }[review.data.assessment.origin]
            }
          </p>
          <p>{review.data.assessment.explanation}</p>
          {review.data.assessment.minor_units !== undefined && (
            <p>
              Reading:{" "}
              {correctionMoney(review.data.assessment.minor_units, currency)}
            </p>
          )}
          {review.data.assessment.proposals?.map((proposal, i) => (
            <p key={i}>
              Possible reading:{" "}
              {correctionMoney(proposal.minor_units, currency)}.{" "}
              {proposal.basis}
            </p>
          ))}
          <p>{review.data.limitation}</p>
        </div>
      )}
      <Button variant="outline" onClick={onClose}>
        Close amount assessment
      </Button>
    </section>
  )
}
