import { createElement, useId, type ReactNode } from "react"
import type { AgentArtifact } from "../types"
import { AgentMarkdown } from "./AgentCitations"
import { artifactRows, artifactSections, artifactText } from "../artifact-data"
import { artifactRevision } from "../artifact-data"
import "./artifact-document.css"

export function ArtifactReportDocument({ artifact, renderEmbed }: {
  artifact: AgentArtifact; renderEmbed: (embed: Record<string, unknown>, index: number) => ReactNode
}) {
  const id = useId()
  const sections = artifactSections(artifact.data.sections)
  const metadata = (artifact.data.document_metadata || artifact.data.metadata || {}) as Record<string, unknown>
  const layout = (artifact.data.document_layout || {}) as Record<string, unknown>
  const sources = Array.isArray(artifact.data.sources) ? artifact.data.sources : []
  const questions = Array.isArray(artifact.data.open_questions) ? artifact.data.open_questions.map(artifactText) : []
  const items = Array.isArray(artifact.data.included_items) ? artifact.data.included_items.map(artifactText) : []
  return <div className="loupe-document-layout min-h-0 flex-1 overflow-y-auto">
    <nav aria-label="Report contents" className="loupe-document-contents">
      <details open><summary>Contents · {sections.length} sections</summary>
        <ol>{sections.map((section, i) => <li key={artifactText(section.id) || i} style={{ marginInlineStart: (Number(section.level) - 2) * 12 }}><a href={`#${id}-section-${i}`} onClick={(e) => { e.preventDefault(); const target = document.getElementById(`${id}-section-${i}`); target?.scrollIntoView({ behavior: "smooth", block: "start" }); target?.focus({ preventScroll: true }) }}><span>{i + 1}</span>{artifactText(section.heading) || `Section ${i + 1}`}</a></li>)}</ol>
      </details>
    </nav>
    <article aria-label={artifact.title} className={`loupe-document${layout.density === "compact" ? " loupe-document-compact" : ""}`}>
      <header className="loupe-document-cover">
        <div className="loupe-document-masthead"><span>Loupe</span><span>Version {artifactRevision(artifact)} · {artifactText(artifact.metadata.status) || "Draft"}</span></div>
        <h1>{artifact.title}</h1>
        {!!metadata.case_label && <p className="loupe-document-note">{artifactText(metadata.case_label)}</p>}
        {!!metadata.classification && <p className="loupe-document-note">{artifactText(metadata.classification)}</p>}
        {!!artifact.data.purpose && <p className="loupe-document-lead">{artifactText(artifact.data.purpose)}</p>}
        {!!artifact.data.audience && <p className="loupe-document-audience">Prepared for {artifactText(artifact.data.audience)}</p>}
        {!!artifact.data.scope && <div className="loupe-document-scope"><span>Scope</span><AgentMarkdown content={artifactText(artifact.data.scope)} /></div>}
        {!!artifact.metadata.revision_note && <p className="loupe-document-note">Revision: {artifactText(artifact.metadata.revision_note)}</p>}
        {items.length > 0 && <details className="loupe-document-note"><summary>Included in this report ({items.length})</summary><ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul></details>}
      </header>
      {sections.map((section, index) => <section id={`${id}-section-${index}`} tabIndex={-1} key={artifactText(section.id) || index} className="loupe-document-section">
        <p className="loupe-document-section-number">{String(index + 1).padStart(2, "0")}</p>
        {createElement(`h${section.level}`, null, artifactText(section.heading) || `Section ${index + 1}`)}
        <AgentMarkdown content={artifactText(section.content)} className="loupe-document-body" />
        {artifactRows(section.embeds).map(renderEmbed)}
      </section>)}
      {!sections.length && <p className="p-6">No sections have been saved for this report.</p>}
      {questions.length > 0 && <section className="loupe-document-section"><h2>Open questions</h2><ol className="list-decimal space-y-2 pl-5">{questions.map((q, i) => <li key={i}>{q}</li>)}</ol></section>}
      {sources.length > 0 && <section className="loupe-document-section"><h2>Sources</h2><ol className="list-decimal space-y-3 pl-5 text-sm">{sources.map((source, index) => {
        if (!source || typeof source !== "object") return <li key={index}><AgentMarkdown content={artifactText(source)} /></li>
        const item = source as Record<string, unknown>
        const label = artifactText(item.label || item.title || item.url || "Source").replace(/[\\[\]<>]/g, "\\$&")
        const url = artifactText(item.url)
        const safe = /^(?:https?:|mailto:|doc:|txn:|rec:|artifact:|#|\/cases\/)/i.test(url) && !/[\s<>]/.test(url)
        return <li key={index}><AgentMarkdown content={`${safe ? `[${label}](<${url}>)` : label}${item.locator ? ` — ${artifactText(item.locator)}` : ""}`} /></li>
      })}</ol></section>}
      <footer className="loupe-document-footer">Loupe · {artifact.title} · Version {artifactRevision(artifact)}</footer>
    </article>
  </div>
}
