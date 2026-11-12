import { useMemo } from "react"
import { Button } from "@/components/ui/button"
import { artifactRevision } from "../artifact-data"
import { compareArtifacts } from "../artifact-compare"
import type { AgentArtifact } from "../types"
import { AgentMarkdown } from "./AgentCitations"

function BeforeAfter({ before, after }: { before: string; after: string }) {
  return <div className="mt-2 grid min-w-0 gap-3 @min-[40rem]:grid-cols-2">
    {[{ label: "Before", text: before }, { label: "After", text: after }].map(({ label, text }) => <div key={label} className="min-w-0 rounded border border-border bg-background p-3"><h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</h4><div className="max-h-72 overflow-auto text-sm [overflow-wrap:anywhere]">{text ? <AgentMarkdown content={text} /> : <p className="text-muted-foreground">Not present in this version.</p>}</div></div>)}
  </div>
}

export function ArtifactVersionComparison({ previous, current, onSelect }: { previous: AgentArtifact; current: AgentArtifact; onSelect: (artifact: AgentArtifact) => void }) {
  const changes = useMemo(() => compareArtifacts(previous, current), [previous, current])
  return <div className="@container space-y-4 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Version {artifactRevision(previous)} → Version {artifactRevision(current)}</h3><Button size="sm" variant="outline" onClick={() => onSelect(previous)}>Open version {artifactRevision(previous)}</Button></div>
    <p className="text-xs text-muted-foreground">Comparing saved versions. Unsaved edits are separate.</p>
    {changes.titleChanged && <div><h4 className="font-medium">Title changed</h4><BeforeAfter before={previous.title} after={current.title} /></div>}
    {changes.details.map((detail) => <details key={detail.label}><summary className="cursor-pointer font-medium">{detail.label} changed</summary><BeforeAfter before={detail.before} after={detail.after} /></details>)}
    {changes.sectionChanges.length > 0 && <section aria-label="Report section changes"><h4 className="mb-2 font-medium">{changes.sectionChanges.filter((s) => s.kind === "Added").length} added · {changes.sectionChanges.filter((s) => s.kind === "Removed").length} removed · {changes.sectionChanges.filter((s) => s.kind === "Changed").length} changed sections</h4><div className="space-y-2">{changes.sectionChanges.map((change) => <details key={change.key} className="rounded border border-border bg-muted/20 p-2"><summary className="cursor-pointer text-sm"><span className="mr-2 font-semibold">{change.kind}</span>{change.after?.heading || change.before?.heading}</summary>
      {change.before && change.after && change.before.position !== change.after.position && <p className="mt-2 text-xs text-muted-foreground">Position {change.before.position} → {change.after.position}</p>}
      {change.before?.heading !== change.after?.heading && change.before && change.after && <p className="mt-2 text-xs">Heading: {change.before.heading} → {change.after.heading}</p>}
      <BeforeAfter before={change.before?.content || ""} after={change.after?.content || ""} />
      {change.exhibitsChanged && <p className="mt-2 text-xs text-muted-foreground">Embedded exhibits changed: {change.before?.embeds.length || 0} → {change.after?.embeds.length || 0}. Pinned exhibit snapshots remain with their saved versions.</p>}
    </details>)}</div></section>}
    {changes.datasetChanges.map((change) => <section key={change.key} aria-label={`${change.label} changes`} className="rounded border border-border bg-background p-3"><h4 className="font-medium">{change.label}{!change.before ? " added" : !change.after ? " removed" : " changed"}</h4><p className="mt-1 text-xs">Rows: {(change.before?.rows.length || 0).toLocaleString()} → {(change.after?.rows.length || 0).toLocaleString()} · Columns: {change.before?.columns.length || 0} → {change.after?.columns.length || 0}</p>
      {change.columnsChanged && <div className="mt-2 space-y-1 text-xs"><p><strong>Before columns:</strong> {change.before?.columns.map((c) => c.label).join(", ") || "None"}</p><p><strong>After columns:</strong> {change.after?.columns.map((c) => c.label).join(", ") || "None"}</p></div>}
      {change.rowsChanged && change.before && change.after && <p className="mt-2 text-xs text-muted-foreground">Cell values or row order changed. Open either saved version to inspect its complete data.</p>}
    </section>)}
    {changes.otherChanges.length > 0 && <ul className="list-disc space-y-1 pl-4 text-xs">{changes.otherChanges.map((change) => <li key={change}>{change}</li>)}</ul>}
    {!changes.contentChanged && <p>No content changes between these saved versions.</p>}
    {changes.contentChanged && !changes.titleChanged && !changes.sectionChanges.length && !changes.datasetChanges.length && !changes.details.length && !changes.otherChanges.length && <p>Saved content changed. Open each version to review the complete artifact.</p>}
  </div>
}
