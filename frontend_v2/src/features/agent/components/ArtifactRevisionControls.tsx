import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { agentAPI } from "../api"
import type { AgentArtifact } from "../types"
import { artifactRows, artifactText, artifactIdentity, artifactRevision } from "../artifact-data"
import { ArtifactVersionComparison } from "./ArtifactVersionComparison"

function SectionEditor({ section, number, onChange }: { section: Record<string, unknown>; number: string; onChange: (section: Record<string, unknown>) => void }) {
  const childKey = artifactRows(section.sections).length ? "sections" : "children"
  const children = artifactRows(section[childKey])
  return <details className="my-2 rounded border border-border bg-background p-2">
    <summary className="cursor-pointer text-sm">{artifactText(section.heading) || `Section ${number}`}</summary>
    <label className="mt-2 block text-xs">Heading<input aria-label={`Section ${number} heading`} value={artifactText(section.heading)} onChange={(e) => onChange({ ...section, heading: e.target.value })} className="mt-1 w-full rounded border border-border bg-background p-2 text-sm" /></label>
    <label className="mt-2 block text-xs">Content<textarea aria-label={`Section ${number} content`} value={artifactText(section.content)} onChange={(e) => onChange({ ...section, content: e.target.value })} className="mt-1 min-h-40 w-full rounded border border-border bg-background p-2 text-sm" /></label>
    <p className="text-xs text-muted-foreground">Existing exhibits and source references are retained.</p>
    {children.map((child, index) => <SectionEditor key={artifactText(child.id) || index} section={child} number={`${number}.${index + 1}`} onChange={(next) => onChange({ ...section, [childKey]: children.map((item, i) => i === index ? next : item) })} />)}
  </details>
}

/** A revision is an immutable new artifact; a stale save retains the investigator's unsaved text. */
export function ArtifactRevisionControls({ artifact, artifacts, disabled, onSaved, onSelect, onRevise, agentBusy = false }: {
  artifact: AgentArtifact; artifacts: AgentArtifact[]; disabled: boolean;
  onSaved: (artifact: AgentArtifact) => void; onSelect: (artifact: AgentArtifact) => void;
  onRevise: (message: string) => void
  agentBusy?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(artifact.title)
  const [sections, setSections] = useState(() => artifactRows(artifact.data.sections))
  const [note, setNote] = useState("")
  const [instruction, setInstruction] = useState("")
  const [error, setError] = useState("")
  const [saving, setSaving] = useState(false)
  const [remoteVersions, setRemoteVersions] = useState<AgentArtifact[]>([])
  const [comparisonOpen, setComparisonOpen] = useState(false)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [previousVersion, setPreviousVersion] = useState<AgentArtifact | null>(null)
  const [reviewReasons, setReviewReasons] = useState<Record<string, string>>({})
  const comparisonRef = useRef<HTMLElement>(null)
  const originalSections = artifactRows(artifact.data.sections)
  const hasChanges = title !== artifact.title || sections.some((section, index) => section !== originalSections[index])
  const validation = artifact.metadata.validation as { issues?: unknown[] } | undefined
  const completion = artifact.metadata.completion_review as { issues?: unknown[] } | undefined
  const issues = [...new Set([...(Array.isArray(validation?.issues) ? validation.issues : []),
    ...(Array.isArray(completion?.issues) ? completion.issues : [])].map(artifactText))]
  const dependencies = artifact.metadata.dependency_review as { status?: string; items?: unknown[] } | undefined
  const dependencyItems = artifactRows(dependencies?.items).filter((item) => item.status === "newer_revision_available" || (!item.status && Number(item.latest_revision) > Number(item.pinned_revision)))
  const versions = [...new Map([...artifacts, ...remoteVersions, artifact]
    .filter((a) => artifactIdentity(a) === artifactIdentity(artifact)).map((a) => [a.id, a])).values()]
    .sort((a, b) => artifactRevision(b) - artifactRevision(a))

  useEffect(() => {
    if (comparisonOpen && !comparisonLoading) { comparisonRef.current?.focus({ preventScroll: true }); comparisonRef.current?.scrollIntoView({ block: "nearest" }) }
  }, [comparisonOpen, comparisonLoading])

  const comparePrevious = async () => {
    setEditing(false); setComparisonOpen(true); setComparisonLoading(true); setError("")
    try {
      const saved = await agentAPI.artifactVersions(artifact.id)
      setRemoteVersions(saved)
      setPreviousVersion(saved.find((version) => version.id === artifact.metadata.previous_revision_id)
        ?? saved.filter((version) => artifactRevision(version) < artifactRevision(artifact)).sort((a, b) => artifactRevision(b) - artifactRevision(a))[0] ?? null)
    } catch (e) { setComparisonOpen(false); setError(e instanceof Error ? e.message : "Could not load the previous version. Your edits are retained.") }
    finally { setComparisonLoading(false) }
  }

  const openDependency = async (id: string) => {
    try { onSelect(await agentAPI.getArtifact(id)) }
    catch (e) { setError(e instanceof Error ? e.message : "Could not open that source version.") }
  }

  const retainDependency = async (item: Record<string, unknown>) => {
    const location = artifactText(item.location)
    const reason = reviewReasons[location]?.trim()
    if (!reason || !item.latest_artifact_id) return
    setSaving(true); setError("")
    try {
      const data: Record<string, unknown> = structuredClone({ ...artifact.data, ...(artifact.type === "report" ? { sections } : {}) })
      if (item.dependency_kind === "copied_input") {
        const sourceId = artifactText(item.artifact_id)
        if (!/^[0-9a-f-]{36}$/i.test(sourceId)) throw new Error("The saved source identity is invalid. Reload this deliverable.")
        const existing = data.source_dependency_reviews
        data.source_dependency_reviews = { ...(existing && typeof existing === "object" ? existing : {}),
          [sourceId]: { artifact_id: sourceId } }
      }
      const path = location.split(".")
      if (path.shift() !== "data") throw new Error("This source cannot be reviewed from the saved location. Reload the report.")
      let embed: unknown = data
      for (const key of path) {
        if (!embed || typeof embed !== "object" || ["__proto__", "constructor", "prototype"].includes(key) || !Object.hasOwn(embed, key)) throw new Error("This exhibit has changed. Reload its saved version before reviewing.")
        embed = (embed as Record<string, unknown>)[key]
      }
      if (!embed || typeof embed !== "object" || (embed as Record<string, unknown>).artifact_id !== item.artifact_id) throw new Error("The pinned exhibit no longer matches this review.")
      ;(embed as Record<string, unknown>).dependency_review = { decision: "retain_pinned", latest_artifact_id: item.latest_artifact_id, reason }
      onSaved(await agentAPI.reviseArtifact(artifact.id, { expected_revision: artifactRevision(artifact), title, data, revision_note: `Retained pinned ${artifactText(item.title) || "exhibit"} after reviewing version ${artifactText(item.latest_revision)}: ${reason}` }))
    } catch (e) { setError(`${e instanceof Error ? e.message : "Could not save the source review."} Your review reason is still here.`) }
    finally { setSaving(false) }
  }

  const refreshVersions = async () => {
    try { setRemoteVersions(await agentAPI.artifactVersions(artifact.id)); setError("") }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load versions. Your changes are retained.") }
  }
  const save = async () => {
    setSaving(true); setError("")
    try {
      const result = await agentAPI.reviseArtifact(artifact.id, {
        expected_revision: artifactRevision(artifact), title, revision_note: note || "Investigator edit",
        data: { ...artifact.data, ...(artifact.type === "report" ? { sections } : {}) },
      })
      onSaved(result); setEditing(false)
      return result
    } catch (e) { setError(`${e instanceof Error ? e.message : "Could not save this revision."} Your edits are still here. Check saved versions before trying again.`) }
    finally { setSaving(false) }
  }
  const reviseWithAgent = async () => {
    const version = hasChanges ? await save() : artifact
    if (!version) return
    onRevise(`Revise saved artifact ${version.id} (version ${artifactRevision(version)}), titled "${version.title}". Preserve all unrelated content and investigator edits. Requested changes: ${instruction}`)
    setEditing(false)
  }
  return <div className="shrink-0 border-b border-border bg-background px-3 py-2">
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-2 text-xs text-muted-foreground">Version
        <select aria-label="Artifact version" value={artifact.id} onChange={(e) => { const found = versions.find((a) => a.id === e.target.value); if (found) onSelect(found) }} className="max-w-52 rounded border border-border bg-background p-1 text-foreground">
          {versions.map((v) => <option key={v.id} value={v.id}>Version {artifactRevision(v)}{v.id === versions[0]?.id ? " · latest" : ""}</option>)}
        </select>
      </label>
      <Button size="sm" variant="ghost" onClick={refreshVersions} disabled={saving}>Check saved versions</Button>
      <Button size="sm" variant="ghost" onClick={comparePrevious} disabled={saving || comparisonLoading}>Compare with previous</Button>
      <Button size="sm" variant="outline" disabled={disabled || saving} onClick={() => { setComparisonOpen(false); setEditing(!editing) }}>{editing ? "Close editor" : "Edit or revise"}</Button>
      <span className="ml-auto text-xs text-muted-foreground">{artifactText(artifact.metadata.status) || "Saved draft"}</span>
    </div>
    {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
    {issues.length > 0 && <div className="mt-2 rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs">
      <details open={issues.length <= 3}><summary className="cursor-pointer font-medium">Draft checks need attention ({issues.length})</summary>
        <ul className="mt-2 max-h-40 list-disc space-y-1 overflow-auto pl-4">{issues.map((issue, index) => <li key={index}>{issue.replace(/^Required coverage (.+): Exactly one explicit coverage record is required\.$/, "$1: this requested topic still needs its supporting content checked.")}</li>)}</ul>
      </details>
      <Button size="sm" variant="ghost" className="mt-1" disabled={disabled || saving || agentBusy || hasChanges}
        onClick={() => onRevise(`Resolve the draft checks on saved artifact ${artifact.id} (version ${artifactRevision(artifact)}). Preserve the original requested scope, all completed content and investigator edits. Inspect the validation and completion review issues, verify them against the sources, and correct affected claims throughout the document. Repair sources, coverage or calculations as needed, and check the rendered export before finishing.`)}>Resolve checks with agent</Button>
      {hasChanges && <p className="mt-1 text-muted-foreground">Save your edits before asking the agent to resolve these checks.</p>}
    </div>}
    {dependencyItems.length > 0 && <details open className="mt-2 max-h-64 overflow-auto rounded border border-amber-500/40 bg-amber-500/10 p-2 text-xs"><summary className="cursor-pointer font-medium">Linked artifacts have newer versions</summary><p className="my-2">This deliverable keeps its saved source versions. Opening a source records no review decision.</p><ul className="space-y-3">{dependencyItems.map((item, index) => {
      const label = artifactText(item.title || item.label || item.artifact_title) || "Linked artifact"
      const location = artifactText(item.location)
      return <li key={index}><span>{label} · pinned version {artifactText(item.pinned_revision)} → latest version {artifactText(item.latest_revision)}</span>{!!item.latest_artifact_id && <Button size="sm" variant="outline" className="ml-2" onClick={() => openDependency(artifactText(item.latest_artifact_id))}>Review newer version</Button>}
        {!!location && <details className="mt-2"><summary className="cursor-pointer">Keep the pinned version after review</summary><label className="mt-2 block">Why should this deliverable keep the original source version?<textarea aria-label={`Reason for keeping ${label}`} value={reviewReasons[location] || ""} onChange={(event) => setReviewReasons((current) => ({ ...current, [location]: event.target.value }))} className="mt-1 min-h-20 w-full rounded border border-border bg-background p-2" /></label><Button size="sm" className="mt-2" disabled={disabled || saving || !reviewReasons[location]?.trim()} onClick={() => retainDependency(item)}>Save review in new version</Button></details>}
      </li>
    })}</ul></details>}
    {comparisonOpen && <section ref={comparisonRef} tabIndex={-1} aria-label="Version comparison" className="mt-3 max-h-[55vh] space-y-3 overflow-auto rounded border border-border bg-muted/20 p-3 focus-visible:outline-2 focus-visible:outline-primary"><div className="flex justify-end"><Button size="sm" variant="ghost" onClick={() => setComparisonOpen(false)}>Close comparison</Button></div>{comparisonLoading ? <p role="status" className="text-xs">Loading saved versions…</p> : previousVersion ? <ArtifactVersionComparison previous={previousVersion} current={artifact} onSelect={onSelect} /> : <p className="text-sm">This is the first saved version. There is no earlier version to compare.</p>}</section>}
    {editing && <div className="mt-3 max-h-[55vh] space-y-3 overflow-auto rounded-md border border-border bg-muted/20 p-3">
      <form onSubmit={(e) => { e.preventDefault(); if (instruction.trim() && !saving && !agentBusy) void reviseWithAgent() }}>
        <label className="block text-xs font-medium" htmlFor="artifact-revise">Ask the agent to revise this version</label>
        <textarea id="artifact-revise" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Expand the analysis, add an exhibit, or change the format…" className="mt-1 min-h-20 w-full rounded border border-border bg-background p-2 text-sm" />
        <Button type="submit" size="sm" disabled={disabled || saving || agentBusy || !instruction.trim()}>{hasChanges ? "Save edits & revise" : "Revise with agent"}</Button>
        {agentBusy && <p className="mt-1 text-xs text-muted-foreground">The agent is working. You can save your edits here and request another revision when it finishes.</p>}
      </form>
      <div className="border-t border-border pt-3">
        <label className="block text-xs font-medium">Title<input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 w-full rounded border border-border bg-background p-2 text-sm" /></label>
        {artifact.type === "report" && sections.map((section, index) => <SectionEditor key={artifactText(section.id) || index} section={section} number={String(index + 1)} onChange={(next) => setSections((current) => current.map((s, i) => i === index ? next : s))} />)}
        <label className="my-2 block text-xs">Revision note<input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded border border-border bg-background p-2 text-sm" /></label>
        <Button size="sm" disabled={saving || disabled || !title.trim()} onClick={save}>{saving ? "Saving…" : "Save new version"}</Button>
        <span className="ml-2 text-xs text-muted-foreground">Earlier versions stay available.</span>
      </div>
    </div>}
  </div>
}
