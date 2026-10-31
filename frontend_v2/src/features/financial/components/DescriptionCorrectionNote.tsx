/**
 * A payment whose first printed line a model read again from the page image and corrected. The correction is the
 * model's reading until a person confirms it, and the description as it was saved stays visible beside it.
 */
export type DescriptionCorrection = {
  before?: string | null
  after?: string | null
  previous_description?: string | null
  page?: number | null
  model: string
  model_id?: string | null
  for_name?: string | null
  confirmed: boolean
}

export function DescriptionCorrectionNote({ correction }: { correction?: DescriptionCorrection }) {
  if (!correction) return null
  const who = correction.for_name ? `${correction.model} (for ${correction.for_name})` : correction.model
  return (
    <div
      role="note"
      aria-label="Description corrected by a model"
      className="space-y-1 rounded border border-[#e7c66b] bg-[#fdf6dd] p-2 text-[12px] text-[#5c3d00] dark:bg-amber-950 dark:text-amber-100"
    >
      <p>
        <strong>First line corrected by {who} · {correction.confirmed ? "confirmed" : "not confirmed"}.</strong>{" "}
        Read again from the page image{correction.page ? `, page ${correction.page}` : ""}: “{correction.before}” → “
        {correction.after}”.
      </p>
      {correction.previous_description && (
        <p>
          As saved before: <span className="font-mono">{correction.previous_description}</span>
        </p>
      )}
    </div>
  )
}
