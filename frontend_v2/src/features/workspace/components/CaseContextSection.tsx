import { useEffect, useMemo, useState, type ReactNode } from "react"
import { BookOpenCheck, Check, ChevronDown, ChevronUp, Edit3, FileText, History, Plus, Save, ShieldAlert, X } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useDossiers } from "@/features/dossiers/hooks"
import { useCaseContext, useCreateMandateVersion, useMandateVersions, useUpdateCaseContext } from "../hooks/use-workspace"
import type { CaseContextTemplateField, CaseContextUpdate, MandateVersionCreate } from "../api"

interface Props { caseId: string; canEdit: boolean }

const EMPTY_MANDATE: MandateVersionCreate = {
  objective: "", key_questions: [], in_scope: "", out_of_scope: "",
  perspective: "", success_criteria: "", constraints: "",
}

function Label({ children }: { children: ReactNode }) {
  return <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">{children}</label>
}

function valueLabel(value: unknown, dossiers: Array<{ id: string; display_name?: string | null }>) {
  if (Array.isArray(value)) return value.join(", ")
  if (typeof value === "boolean") return value ? "Yes" : "No"
  const dossier = dossiers.find((item) => item.id === String(value))
  return dossier?.display_name || String(value)
}

function TypedField({ field, value, dossiers, onChange }: {
  field: CaseContextTemplateField
  value: unknown
  dossiers: Array<{ id: string; display_name?: string | null }>
  onChange: (value: unknown) => void
}) {
  if (field.type === "long_text") {
    return <Textarea aria-label={field.label} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} rows={4} />
  }
  if (field.type === "boolean") {
    return <label className="flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs"><input type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} />{value === true ? "Yes" : "No"}</label>
  }
  if (field.type === "single_choice" || field.type === "dossier_reference") {
    const choices = field.type === "dossier_reference"
      ? dossiers.map((item) => ({ value: item.id, label: item.display_name || "Untitled Dossier" }))
      : field.choices.map((item) => ({ value: item, label: item }))
    return <select aria-label={field.label} value={String(value ?? "")} onChange={(event) => onChange(event.target.value || null)} className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"><option value="">Select…</option>{choices.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
  }
  if (field.type === "multiple_choice") {
    const selected = Array.isArray(value) ? value.map(String) : []
    return <div className="flex flex-wrap gap-2 rounded-md border border-border p-2">{field.choices.map((choice) => <label key={choice} className="flex items-center gap-1.5 text-xs"><input type="checkbox" checked={selected.includes(choice)} onChange={(event) => onChange(event.target.checked ? [...selected, choice] : selected.filter((item) => item !== choice))} />{choice}</label>)}</div>
  }
  return <Input aria-label={field.label} type={field.type === "date" ? "date" : field.type === "number" ? "number" : "text"} value={value === null || value === undefined ? "" : String(value)} onChange={(event) => onChange(field.type === "number" ? (event.target.value ? Number(event.target.value) : null) : event.target.value)} />
}

export function CaseContextSection({ caseId, canEdit }: Props) {
  const contextQuery = useCaseContext(caseId)
  const versionsQuery = useMandateVersions(caseId)
  const dossiersQuery = useDossiers({ caseId, limit: 100 })
  const updateContext = useUpdateCaseContext(caseId)
  const createVersion = useCreateMandateVersion(caseId)
  const context = contextQuery.data
  const dossiers = dossiersQuery.data?.dossiers ?? []
  const [editingContext, setEditingContext] = useState(false)
  const [editingMandate, setEditingMandate] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [draft, setDraft] = useState<CaseContextUpdate>({ case_summary: "", background: "", investigation_type: "", jurisdiction: "", active_template_key: "generic", custom_values: {} })
  const [mandate, setMandate] = useState<MandateVersionCreate>(EMPTY_MANDATE)

  useEffect(() => {
    if (!context || editingContext) return
    setDraft({ case_summary: context.case_summary ?? "", background: context.background ?? "", investigation_type: context.investigation_type ?? "", jurisdiction: context.jurisdiction ?? "", active_template_key: context.active_template_key, custom_values: context.custom_values ?? {} })
  }, [context, editingContext])

  const activeTemplate = useMemo(() => context?.templates.find((item) => item.key === draft.active_template_key), [context?.templates, draft.active_template_key])
  const displayedTemplate = context?.templates.find((item) => item.key === context.active_template_key)

  const saveContext = async () => {
    try { await updateContext.mutateAsync(draft); setEditingContext(false); toast.success("Case context updated") }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not update case context") }
  }
  const saveMandate = async () => {
    try { await createVersion.mutateAsync(mandate); setEditingMandate(false); setMandate(EMPTY_MANDATE); toast.success("New mandate version is active") }
    catch (error) { toast.error(error instanceof Error ? error.message : "Could not create mandate version") }
  }
  const startMandate = () => {
    const current = context?.active_mandate
    setMandate(current ? {
      objective: current.objective ?? "", key_questions: current.key_questions,
      in_scope: current.in_scope ?? "", out_of_scope: current.out_of_scope ?? "",
      perspective: current.perspective ?? "", success_criteria: current.success_criteria ?? "",
      constraints: current.constraints ?? "",
    } : EMPTY_MANDATE)
    setEditingMandate(true)
  }

  if (contextQuery.isLoading) return <div className="h-64 animate-pulse rounded-xl bg-muted/30" />

  return <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="flex gap-2.5"><FileText className="mt-0.5 size-4 text-emerald-500" /><div><h2 className="text-sm font-semibold">Case context</h2><p className="mt-0.5 text-xs text-muted-foreground">The stable orientation investigators need before working the case.</p></div></div>
        {canEdit && (editingContext ? <div className="flex gap-1"><Button variant="ghost" size="icon-sm" aria-label="Cancel context changes" onClick={() => setEditingContext(false)}><X className="size-3.5" /></Button><Button size="sm" onClick={saveContext} disabled={updateContext.isPending}><Save className="size-3.5" /> Save</Button></div> : <Button variant="ghost" size="sm" onClick={() => setEditingContext(true)}><Edit3 className="size-3.5" /> Edit</Button>)}
      </div>
      {editingContext ? <div className="space-y-5 p-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5 sm:col-span-2"><Label>Case summary</Label><Textarea aria-label="Case summary" value={draft.case_summary ?? ""} onChange={(event) => setDraft((value) => ({ ...value, case_summary: event.target.value }))} rows={3} placeholder="What is this investigation about?" /></div>
          <div className="space-y-1.5 sm:col-span-2"><Label>Background / triggering event</Label><Textarea aria-label="Background / triggering event" value={draft.background ?? ""} onChange={(event) => setDraft((value) => ({ ...value, background: event.target.value }))} rows={3} placeholder="What caused the investigation to begin?" /></div>
          <div className="space-y-1.5"><Label>Investigation type</Label><Input aria-label="Investigation type" value={draft.investigation_type ?? ""} onChange={(event) => setDraft((value) => ({ ...value, investigation_type: event.target.value }))} placeholder="e.g. corporate misconduct" /></div>
          <div className="space-y-1.5"><Label>Jurisdiction / operating context</Label><Input aria-label="Jurisdiction / operating context" value={draft.jurisdiction ?? ""} onChange={(event) => setDraft((value) => ({ ...value, jurisdiction: event.target.value }))} placeholder="e.g. Ireland and United Kingdom" /></div>
        </div>
        <div className="border-t border-border pt-4">
          <div className="mb-3 grid gap-1.5 sm:grid-cols-[180px_minmax(0,1fr)] sm:items-center"><Label>Specialised template</Label><select aria-label="Specialised template" value={draft.active_template_key} onChange={(event) => setDraft((value) => ({ ...value, active_template_key: event.target.value, custom_values: {} }))} className="h-9 rounded-md border border-input bg-background px-3 text-xs">{context?.templates.map((template) => <option key={template.key} value={template.key}>{template.name}</option>)}</select></div>
          {activeTemplate?.description && <p className="mb-3 text-xs text-muted-foreground">{activeTemplate.description}</p>}
          <div className="grid gap-4 sm:grid-cols-2">{activeTemplate?.fields.map((field) => <div key={field.key} className={`space-y-1.5 ${field.type === "long_text" ? "sm:col-span-2" : ""}`}><Label>{field.label}{field.required ? " *" : ""}</Label><TypedField field={field} value={draft.custom_values[field.key]} dossiers={dossiers} onChange={(value) => setDraft((current) => ({ ...current, custom_values: { ...current.custom_values, [field.key]: value } }))} /></div>)}</div>
        </div>
      </div> : <div className="p-4">{context?.case_summary || context?.background || context?.investigation_type || context?.jurisdiction ? <div className="space-y-4">
        {context.case_summary && <div><Label>Case summary</Label><p className="mt-1 text-sm leading-relaxed">{context.case_summary}</p></div>}
        {context.background && <div><Label>Background / triggering event</Label><p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-foreground/80">{context.background}</p></div>}
        <div className="grid gap-3 sm:grid-cols-2">{context.investigation_type && <div className="rounded-lg bg-muted/25 p-3"><Label>Investigation type</Label><p className="mt-1 text-xs">{context.investigation_type}</p></div>}{context.jurisdiction && <div className="rounded-lg bg-muted/25 p-3"><Label>Jurisdiction / context</Label><p className="mt-1 text-xs">{context.jurisdiction}</p></div>}</div>
        {displayedTemplate && displayedTemplate.fields.length > 0 && <div className="border-t border-border pt-4"><div className="mb-3 flex items-center gap-2"><Badge variant="outline">{displayedTemplate.name}</Badge><span className="text-[10px] text-muted-foreground">Specialised context</span></div><dl className="grid gap-3 sm:grid-cols-2">{displayedTemplate.fields.map((field) => { const value = context.custom_values[field.key]; if (value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) return null; return <div key={field.key} className={field.type === "long_text" ? "sm:col-span-2" : ""}><dt><Label>{field.label}</Label></dt><dd className="mt-1 whitespace-pre-wrap text-xs text-foreground/80">{valueLabel(value, dossiers)}</dd></div> })}</dl></div>}
      </div> : <div className="py-8 text-center"><FileText className="mx-auto size-7 text-muted-foreground/30" /><p className="mt-2 text-xs text-muted-foreground">No case context has been recorded yet.</p></div>}</div>}
    </section>

    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      <div className="border-b border-border px-4 py-3"><div className="flex items-start justify-between gap-3"><div className="flex gap-2.5"><BookOpenCheck className="mt-0.5 size-4 text-violet-500" /><div><div className="flex items-center gap-2"><h2 className="text-sm font-semibold">Case mandate</h2>{context?.active_mandate ? <Badge variant="secondary">v{context.active_mandate.version_number}</Badge> : <Badge variant="outline">Incomplete</Badge>}</div><p className="mt-0.5 text-xs text-muted-foreground">Visible working instructions used by Chat and Agent.</p></div></div>{canEdit && !editingMandate && <Button variant="ghost" size="sm" onClick={startMandate}><Plus className="size-3.5" /> New version</Button>}</div></div>
      {editingMandate ? <div className="space-y-3 p-4">
        <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3 text-xs text-muted-foreground">Saving creates a new immutable version. Existing AI conversations keep the version they started with until explicitly updated.</div>
        <div className="space-y-1.5"><Label>Objective</Label><Textarea aria-label="Objective" value={mandate.objective ?? ""} onChange={(event) => setMandate((value) => ({ ...value, objective: event.target.value }))} rows={2} /></div>
        <div className="space-y-1.5"><Label>Key questions (one per line)</Label><Textarea aria-label="Key questions (one per line)" value={mandate.key_questions.join("\n")} onChange={(event) => setMandate((value) => ({ ...value, key_questions: event.target.value.split("\n") }))} rows={3} /></div>
        {([['in_scope', 'In scope'], ['out_of_scope', 'Out of scope'], ['perspective', 'Perspective / posture'], ['success_criteria', 'Expected output / success criteria'], ['constraints', 'Constraints / special instructions']] as const).map(([key, label]) => <div key={key} className="space-y-1.5"><Label>{label}</Label><Textarea aria-label={label} value={mandate[key] ?? ""} onChange={(event) => setMandate((value) => ({ ...value, [key]: event.target.value }))} rows={2} /></div>)}
        <div className="flex justify-end gap-2"><Button variant="ghost" size="sm" onClick={() => setEditingMandate(false)}>Cancel</Button><Button size="sm" onClick={saveMandate} disabled={createVersion.isPending}><Check className="size-3.5" /> Activate version</Button></div>
      </div> : context?.active_mandate ? <div className="space-y-3 p-4">
        {context.active_mandate.objective && <div><Label>Objective</Label><p className="mt-1 text-sm font-medium leading-relaxed">{context.active_mandate.objective}</p></div>}
        {context.active_mandate.key_questions.length > 0 && <div><Label>Key questions</Label><ul className="mt-1.5 space-y-1">{context.active_mandate.key_questions.map((question) => <li key={question} className="flex gap-2 text-xs text-foreground/80"><span className="text-violet-500">•</span>{question}</li>)}</ul></div>}
        {([['in_scope', 'In scope'], ['out_of_scope', 'Out of scope'], ['perspective', 'Perspective / posture'], ['success_criteria', 'Success criteria'], ['constraints', 'Constraints']] as const).map(([key, label]) => context.active_mandate?.[key] ? <div key={key}><Label>{label}</Label><p className="mt-1 whitespace-pre-wrap text-xs text-foreground/80">{context.active_mandate[key]}</p></div> : null)}
        <div className="border-t border-border pt-3 text-[10px] text-muted-foreground">Authored by {context.active_mandate.author_name || "a migrated case record"} · {context.active_mandate.created_at ? new Date(context.active_mandate.created_at).toLocaleString() : "date unavailable"}</div>
      </div> : <div className="p-4"><div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-center"><ShieldAlert className="mx-auto size-6 text-amber-500" /><p className="mt-2 text-xs font-medium">No case mandate yet</p><p className="mt-1 text-xs text-muted-foreground">Chat and Agent can still be used, but they will not have saved investigative framing.</p></div></div>}
      {(versionsQuery.data?.length ?? 0) > 0 && !editingMandate && <div className="border-t border-border"><button type="button" onClick={() => setHistoryOpen((value) => !value)} className="flex w-full items-center justify-between px-4 py-2.5 text-xs text-muted-foreground hover:bg-muted/25 hover:text-foreground"><span className="flex items-center gap-2"><History className="size-3.5" /> Version history ({versionsQuery.data?.length})</span>{historyOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}</button>{historyOpen && <div className="divide-y divide-border border-t border-border">{versionsQuery.data?.map((version) => <div key={version.id} className="flex items-start justify-between gap-3 px-4 py-2.5"><div><p className="text-xs font-medium">Version {version.version_number}{version.id === context?.active_mandate?.id ? " · active" : ""}</p><p className="mt-0.5 line-clamp-1 text-[10px] text-muted-foreground">{version.objective || "No objective recorded"}</p></div><span className="whitespace-nowrap text-[10px] text-muted-foreground">{version.created_at ? new Date(version.created_at).toLocaleDateString() : "—"}</span></div>)}</div>}</div>}
    </section>
  </div>
}
