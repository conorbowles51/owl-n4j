/** "Required" or "Optional" beside a field's label: what import needs from it. */
export function FieldNeed({ required }: { required: boolean }) {
  return (
    <span
      className={`ml-1 text-[10px] font-semibold uppercase tracking-wide ${required ? "text-amber-800 dark:text-amber-300" : "text-muted-foreground"}`}
    >
      {required ? "Required" : "Optional"}
    </span>
  )
}
