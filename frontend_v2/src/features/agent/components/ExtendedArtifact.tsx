import { useState, type ReactNode } from "react"
import { AgentMarkdown } from "./AgentCitations"
import { ArtifactDataTable } from "./ArtifactDataTable"
import { artifactRows, artifactText, isolatedArtifactDocument } from "../artifact-data"
import { ArtifactScenario } from "./ArtifactScenario"
import type { AgentArtifact } from "../types"

export function ExtendedArtifact({ artifact, renderEmbed }: {
  artifact: AgentArtifact; renderEmbed?: (embed: Record<string, unknown>, index: number) => ReactNode
}) {
  const [selected, setSelected] = useState(0)
  if (artifact.type === "interactive") return <div className="flex min-h-0 flex-1 flex-col gap-3">
    <p className="text-xs text-muted-foreground">Interactive view · Changes here do not change saved case records.</p>
    {!!artifact.data.interactions && <ArtifactScenario interactions={artifact.data.interactions as Record<string, unknown>} />}
    {!!artifact.data.rows && <ArtifactDataTable data={artifact.data} label={`${artifact.title} data`} />}
    {/<script[\s>]|\son\w+\s*=/i.test(artifactText(artifact.data.html)) && <p className="text-xs text-muted-foreground">This saved layout contains custom scripts. They are inactive; supported controls and calculations appear above.</p>}
    <iframe title={artifact.title} sandbox="" referrerPolicy="no-referrer" srcDoc={isolatedArtifactDocument(artifactText(artifact.data.html))} className="min-h-[28rem] w-full flex-1 rounded-lg border border-border bg-white" />
    {!!artifact.data.static_content && <details className="text-sm"><summary className="cursor-pointer">Readable alternative</summary><AgentMarkdown content={artifactText(artifact.data.static_content).replace(/<\/?(?:p|div|section)\b[^>]*>|<br\s*\/?>/gi, "\n\n").trim()} /></details>}
  </div>
  if (artifact.type === "workbook") {
    const sheets = artifactRows(artifact.data.sheets)
    const sheet = sheets[Math.min(selected, Math.max(0, sheets.length - 1))]
    return <div className="min-h-0 flex-1 space-y-4 overflow-auto">
      <div role="tablist" aria-label="Workbook sheets" className="flex flex-wrap gap-1 border-b border-border">{sheets.map((s, i) => <button key={i} role="tab" aria-selected={selected === i} onClick={() => setSelected(i)} className={`border-b-2 px-4 py-2 text-sm ${selected === i ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}>{artifactText(s.name) || `Sheet ${i + 1}`}</button>)}</div>
      {sheet ? <div role="tabpanel"><ArtifactDataTable key={selected} data={sheet} label={artifactText(sheet.name) || "Workbook data"} />
        {artifactRows(sheet.formulas).length > 0 && <details className="mt-4 text-xs"><summary>Formulas ({artifactRows(sheet.formulas).length})</summary><ArtifactDataTable data={{ rows: sheet.formulas }} label="Saved formulas" /><p className="mt-2 text-muted-foreground">Formulas recalculate when the workbook opens in a spreadsheet application.</p></details>}
      </div> : <p>No sheets saved.</p>}
    </div>
  }
  if (artifact.type === "presentation") {
    const slides = artifactRows(artifact.data.slides)
    return <div className="min-h-0 flex-1 overflow-auto space-y-5">{slides.map((slide, index) => <section key={index} className="rounded-lg border border-border bg-background p-6 shadow-sm">
      <div className="mb-6 flex justify-between border-b border-border pb-3 text-xs uppercase tracking-[.16em] text-muted-foreground"><span className="font-semibold text-primary">Loupe</span><span>{index + 1} / {slides.length}</span></div>
      <h2 className="mb-4 text-xl font-semibold tracking-tight">{artifactText(slide.title)}</h2>
      <AgentMarkdown content={artifactText(slide.content)} className="text-sm leading-7" />
      {renderEmbed && artifactRows(slide.embeds).map(renderEmbed)}
      {!!slide.notes && <details className="mt-6 border-t border-border pt-3 text-xs text-muted-foreground"><summary>Speaker notes</summary><AgentMarkdown content={artifactText(slide.notes)} /></details>}
    </section>)}</div>
  }
  return <div className="min-h-0 flex-1 overflow-auto"><ArtifactDataTable data={artifact.data} label={artifact.title} /></div>
}
