import { useEffect, useMemo, useState, type ReactNode } from "react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useDossiers } from "@/features/dossiers/hooks"
import {
  useCaseContext,
  useCreateMandateVersion,
  useMandateVersions,
  useUpdateCaseContext,
} from "../hooks/use-workspace"
import type {
  CaseContextTemplateField,
  CaseContextUpdate,
  MandateVersionCreate,
} from "../api"
interface Props {
  caseId: string
  canEdit: boolean
  onDirtyChange?: (dirty: boolean) => void
}
const EMPTY_MANDATE: MandateVersionCreate = {
  objective: "",
  key_questions: [],
  in_scope: "",
  out_of_scope: "",
  perspective: "",
  success_criteria: "",
  constraints: "",
}
function Label({ children }: { children: ReactNode }) {
  return (
    <label className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
      {children}
    </label>
  )
}
function valueLabel(
  value: unknown,
  dossiers: Array<{ id: string; display_name?: string | null }>
) {
  if (Array.isArray(value)) return value.join(", ")
  if (typeof value === "boolean") return value ? "Yes" : "No"
  const dossier = dossiers.find((item) => item.id === String(value))
  return dossier?.display_name || String(value)
}
function TypedField({
  field,
  value,
  dossiers,
  onChange,
}: {
  field: CaseContextTemplateField
  value: unknown
  dossiers: Array<{ id: string; display_name?: string | null }>
  onChange: (value: unknown) => void
}) {
  if (field.type === "long_text") {
    return (
      <Textarea
        aria-label={field.label}
        value={String(value ?? "")}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
      />
    )
  }
  if (field.type === "boolean") {
    return (
      <label className="flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
        />
        {value === true ? "Yes" : "No"}
      </label>
    )
  }
  if (field.type === "single_choice" || field.type === "dossier_reference") {
    const choices =
      field.type === "dossier_reference"
        ? dossiers.map((item) => ({
            value: item.id,
            label: item.display_name || "Untitled Dossier",
          }))
        : field.choices.map((item) => ({ value: item, label: item }))
    return (
      <select
        aria-label={field.label}
        value={String(value ?? "")}
        onChange={(event) => onChange(event.target.value || null)}
        className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"
      >
        <option value="">Select…</option>
        {choices.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    )
  }
  if (field.type === "multiple_choice") {
    const selected = Array.isArray(value) ? value.map(String) : []
    return (
      <div className="flex flex-wrap gap-2 rounded-md border border-border p-2">
        {field.choices.map((choice) => (
          <label key={choice} className="flex items-center gap-1.5 text-xs">
            <input
              type="checkbox"
              checked={selected.includes(choice)}
              onChange={(event) =>
                onChange(
                  event.target.checked
                    ? [...selected, choice]
                    : selected.filter((item) => item !== choice)
                )
              }
            />
            {choice}
          </label>
        ))}
      </div>
    )
  }
  return (
    <Input
      aria-label={field.label}
      type={
        field.type === "date"
          ? "date"
          : field.type === "number"
            ? "number"
            : "text"
      }
      value={value === null || value === undefined ? "" : String(value)}
      onChange={(event) =>
        onChange(
          field.type === "number"
            ? event.target.value
              ? Number(event.target.value)
              : null
            : event.target.value
        )
      }
    />
  )
}
const RETIRED_FIELDS = new Set(["denials", "legal_exposure"])

const contextDraft = (
  context: NonNullable<ReturnType<typeof useCaseContext>["data"]>
): CaseContextUpdate => ({
  case_summary: context.case_summary ?? "",
  background: context.background ?? "",

  investigation_type: context.investigation_type ?? "",
  jurisdiction: context.jurisdiction ?? "",

  active_template_key: context.active_template_key,
  custom_values: context.custom_values ?? {},

  template_values: context.template_values ?? {
    [context.active_template_key]: context.custom_values ?? {},
  },
})

export function CaseContextSection({ caseId, canEdit, onDirtyChange }: Props) {
  const contextQuery = useCaseContext(caseId)

  const versionsQuery = useMandateVersions(caseId)

  const dossiersQuery = useDossiers({ caseId, limit: 100 })

  const updateContext = useUpdateCaseContext(caseId)

  const createVersion = useCreateMandateVersion(caseId)

  const context = contextQuery.data

  const dossiers = dossiersQuery.data?.dossiers ?? []

  const [editingContext, setEditingContext] = useState(false)

  const [editingMandate, setEditingMandate] = useState(false)

  const [draft, setDraft] = useState<CaseContextUpdate>({
    active_template_key: "generic",
    custom_values: {},
  })

  const [mandate, setMandate] = useState<MandateVersionCreate>(EMPTY_MANDATE)

  const [baseline, setBaseline] = useState("")

  const dirty =
    (editingContext && JSON.stringify(draft) !== baseline) ||
    (editingMandate && JSON.stringify(mandate) !== baseline)

  useEffect(() => {
    onDirtyChange?.(dirty)
    return () => onDirtyChange?.(false)
  }, [dirty, onDirtyChange])

  useEffect(() => {
    if (!dirty) return

    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }

    window.addEventListener("beforeunload", warn)

    return () => window.removeEventListener("beforeunload", warn)
  }, [dirty])

  const activeTemplate = useMemo(
    () =>
      context?.templates.find((item) => item.key === draft.active_template_key),
    [context?.templates, draft.active_template_key]
  )

  const cancel = () => {
    if (dirty && !window.confirm("Discard your unsaved setup changes?")) return

    setEditingContext(false)
    setEditingMandate(false)
  }

  const startContext = () => {
    if (!context) return

    const next = contextDraft(context)
    setDraft(next)
    setBaseline(JSON.stringify(next))
    setEditingContext(true)
  }

  const startObjective = () => {
    const current = context?.active_mandate

    const next = current
      ? {
          objective: current.objective ?? "",
          key_questions: current.key_questions,

          in_scope: current.in_scope ?? "",
          out_of_scope: current.out_of_scope ?? "",
          perspective: current.perspective ?? "",

          success_criteria: current.success_criteria ?? "",
          constraints: current.constraints ?? "",
        }
      : EMPTY_MANDATE

    setMandate(next)
    setBaseline(JSON.stringify(next))
    setEditingMandate(true)
  }

  const saveContext = async () => {
    try {
      const original = JSON.parse(baseline) as CaseContextUpdate
      const originalValues = {
        ...original.template_values,
        [original.active_template_key]: original.custom_values,
      }
      const values = {
        ...draft.template_values,
        [draft.active_template_key]: draft.custom_values,
      }
      const changed = Object.fromEntries(
        Object.entries(values)
          .map(([key, fields]) => [
            key,
            Object.fromEntries(
              Object.entries(fields).filter(
                ([field, value]) =>
                  JSON.stringify(value) !==
                  JSON.stringify(originalValues[key]?.[field])
              )
            ),
          ])
          .filter(([, fields]) => Object.keys(fields).length > 0)
      ) as Record<string, Record<string, unknown>>
      await updateContext.mutateAsync({
        ...Object.fromEntries(
          (
            [
              "case_summary",
              "background",
              "investigation_type",
              "jurisdiction",
            ] as const
          )
            .filter((key) => draft[key] !== original[key])
            .map((key) => [key, draft[key]])
        ),
        active_template_key: draft.active_template_key,
        custom_values: changed[draft.active_template_key] ?? {},
        template_values: changed,
      })
      setEditingContext(false)
      toast.success("Case summary saved")
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not save case summary. Your changes are still here; try again."
      )
    }
  }

  const saveObjective = async () => {
    try {
      await createVersion.mutateAsync(mandate)
      setEditingMandate(false)
      toast.success("Objective saved")
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not save objective. Your changes are still here; try again."
      )
    }
  }

  const switchTemplate = (key: string) =>
    setDraft((current) => {
      const values = {
        ...current.template_values,
        [current.active_template_key]: current.custom_values,
      }

      return {
        ...current,
        active_template_key: key,
        custom_values: values[key] ?? {},
        template_values: values,
      }
    })

  if (contextQuery.isLoading)
    return <div className="h-64 animate-pulse rounded-xl bg-muted/30" />

  if (contextQuery.isError || !context)
    return (
      <div role="alert" className="rounded-xl border p-4">
        Case setup could not be loaded.{" "}
        <Button variant="outline" onClick={() => contextQuery.refetch()}>
          Try again
        </Button>
      </div>
    )

  const busy = updateContext.isPending || createVersion.isPending

  const retiredField = (key: string, templateKey = draft.active_template_key) =>
    templateKey === "criminal_defense" && RETIRED_FIELDS.has(key)
  const savedValues = context.template_values ?? {
    [context.active_template_key]: context.custom_values,
  }

  const advancedFields = [
    ["in_scope", "In scope"],
    ["out_of_scope", "Out of scope"],
    ["perspective", "Perspective / posture"],
    ["success_criteria", "Expected output / success criteria"],
  ] as const

  return (
    <div className="grid items-start gap-5 xl:grid-cols-2">
      <section className="min-w-0 rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Case Summary</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              What the case is about. Add detail when it helps.
            </p>
          </div>
          {canEdit && !editingContext && (
            <Button
              variant="outline"
              size="sm"
              disabled={editingMandate}
              onClick={startContext}
            >
              Edit summary
            </Button>
          )}
        </div>

        {editingContext ? (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Case summary</Label>
              <Textarea
                aria-label="Case summary"
                rows={3}
                value={draft.case_summary ?? ""}
                onChange={(e) =>
                  setDraft((v) => ({ ...v, case_summary: e.target.value }))
                }
                placeholder="What is this investigation about?"
              />
            </div>

            <details>
              <summary className="cursor-pointer text-xs font-medium">
                Additional case details (optional)
              </summary>
              <div className="mt-3 space-y-3">
                {(
                  [
                    ["background", "Background / triggering event"],
                    ["investigation_type", "Investigation type"],
                    ["jurisdiction", "Jurisdiction / operating context"],
                  ] as const
                ).map(([key, label]) => (
                  <div key={key} className="space-y-1.5">
                    <Label>{label}</Label>
                    <Textarea
                      aria-label={label}
                      rows={2}
                      value={draft[key] ?? ""}
                      onChange={(e) =>
                        setDraft((v) => ({ ...v, [key]: e.target.value }))
                      }
                    />
                  </div>
                ))}
              </div>
            </details>

            <div className="space-y-3 border-t pt-3">
              <label
                className="block text-xs font-medium"
                htmlFor="case-template"
              >
                Specialised template
              </label>
              <select
                id="case-template"
                className="h-9 w-full rounded-md border bg-background px-3 text-xs"
                value={draft.active_template_key}
                onChange={(e) => switchTemplate(e.target.value)}
              >
                {context.templates.map((t) => (
                  <option key={t.key} value={t.key}>
                    {t.name}
                  </option>
                ))}
              </select>

              <p className="text-xs text-muted-foreground">
                Switching templates keeps the information entered in each one.
                Court information stays here; deadlines record names and dates.
              </p>

              {activeTemplate?.fields
                .filter((f) => !retiredField(f.key))
                .map((field) => (
                  <div key={field.key} className="space-y-1.5">
                    <Label>{field.label}</Label>
                    <TypedField
                      field={field}
                      value={draft.custom_values[field.key]}
                      dossiers={dossiers}
                      onChange={(value) =>
                        setDraft((v) => ({
                          ...v,
                          custom_values: {
                            ...v.custom_values,
                            [field.key]: value,
                          },
                        }))
                      }
                    />
                  </div>
                ))}

              {activeTemplate?.fields.some(
                (f) => retiredField(f.key) && draft.custom_values[f.key]
              ) && (
                <details>
                  <summary className="cursor-pointer text-xs">
                    Previously recorded information
                  </summary>
                  <p className="my-2 text-xs text-muted-foreground">
                    Preserved from earlier setup. Record new client accounts in
                    linked notes or documents.
                  </p>
                  {activeTemplate.fields
                    .filter(
                      (f) => retiredField(f.key) && draft.custom_values[f.key]
                    )
                    .map((f) => (
                      <div key={f.key}>
                        <Label>{f.label}</Label>
                        <p className="whitespace-pre-wrap text-xs">
                          {valueLabel(draft.custom_values[f.key], dossiers)}
                        </p>
                      </div>
                    ))}
                </details>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="ghost" disabled={busy} onClick={cancel}>
                Cancel
              </Button>
              <Button onClick={saveContext} disabled={busy}>
                Save summary
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 text-sm">
            <p className="whitespace-pre-wrap">
              {context.case_summary ||
                "Add a short summary when you are ready."}
            </p>
            {context.background && (
              <p className="whitespace-pre-wrap text-xs text-muted-foreground">
                {context.background}
              </p>
            )}
            {context.investigation_type && (
              <Badge variant="outline">{context.investigation_type}</Badge>
            )}
            {context.jurisdiction && (
              <Badge variant="outline">{context.jurisdiction}</Badge>
            )}

            {context.templates
              .filter((t) => Object.keys(savedValues[t.key] ?? {}).length > 0)
              .map((t) => (
                <details
                  key={t.key}
                  open={t.key === context.active_template_key}
                >
                  <summary className="cursor-pointer text-xs font-medium">
                    {t.name}
                    {t.key !== context.active_template_key
                      ? " (saved information)"
                      : ""}
                  </summary>
                  <dl className="mt-3 space-y-3">
                    {t.fields
                      .filter((f) => savedValues[t.key]?.[f.key] !== undefined)
                      .map((f) => (
                        <div key={f.key}>
                          <dt className="text-xs font-medium">
                            {f.label}
                            {retiredField(f.key, t.key)
                              ? " (previously recorded)"
                              : ""}
                          </dt>
                          <dd className="mt-1 whitespace-pre-wrap text-xs text-muted-foreground">
                            {valueLabel(savedValues[t.key][f.key], dossiers)}
                          </dd>
                        </div>
                      ))}
                  </dl>
                </details>
              ))}
          </div>
        )}
      </section>

      <section className="min-w-0 rounded-xl border border-border bg-card p-4 shadow-sm">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Objective</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              What you want to establish, used by Chat and Agent.
            </p>
          </div>
          {canEdit && !editingMandate && (
            <Button
              variant="outline"
              size="sm"
              disabled={editingContext}
              onClick={startObjective}
            >
              {context.active_mandate ? "Edit objective" : "Add objective"}
            </Button>
          )}
        </div>

        {editingMandate ? (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Objective</Label>
              <Textarea
                aria-label="Objective"
                rows={4}
                value={mandate.objective ?? ""}
                onChange={(e) =>
                  setMandate((v) => ({ ...v, objective: e.target.value }))
                }
                placeholder="What do you need to find out?"
              />
            </div>

            <div className="space-y-1.5">
              <Label>Constraints / special instructions (optional)</Label>
              <Textarea
                aria-label="Constraints / special instructions"
                rows={2}
                value={mandate.constraints ?? ""}
                onChange={(e) =>
                  setMandate((v) => ({ ...v, constraints: e.target.value }))
                }
              />
            </div>

            <details>
              <summary className="cursor-pointer text-xs font-medium">
                Advanced instructions (optional)
              </summary>
              <div className="mt-3 space-y-3">
                <Label>Key questions (one per line)</Label>
                <Textarea
                  aria-label="Key questions (one per line)"
                  value={mandate.key_questions.join("\n")}
                  onChange={(e) =>
                    setMandate((v) => ({
                      ...v,
                      key_questions: e.target.value.split("\n"),
                    }))
                  }
                />
                {advancedFields.map(([key, label]) => (
                  <div key={key}>
                    <Label>{label}</Label>
                    <Textarea
                      aria-label={label}
                      rows={2}
                      value={mandate[key] ?? ""}
                      onChange={(e) =>
                        setMandate((v) => ({ ...v, [key]: e.target.value }))
                      }
                    />
                  </div>
                ))}
              </div>
            </details>

            <p className="text-xs text-muted-foreground">
              Existing conversations keep their earlier objective until you
              choose to update them.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" disabled={busy} onClick={cancel}>
                Cancel
              </Button>
              <Button
                disabled={busy || !mandate.objective?.trim()}
                onClick={saveObjective}
              >
                Save objective
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="whitespace-pre-wrap text-sm">
              {context.active_mandate?.objective ||
                "No objective saved yet. You can still use Chat and Agent."}
            </p>
            {context.active_mandate?.constraints && (
              <div>
                <Label>Constraints / special instructions</Label>
                <p className="whitespace-pre-wrap text-xs">
                  {context.active_mandate.constraints}
                </p>
              </div>
            )}
            {context.active_mandate && (
              <details>
                <summary className="cursor-pointer text-xs">
                  Advanced instructions
                </summary>
                <div className="mt-2 space-y-2">
                  {context.active_mandate.key_questions.map((q, i) => (
                    <p key={i} className="text-xs">
                      {q}
                    </p>
                  ))}
                  {advancedFields.map(([key, label]) =>
                    context.active_mandate?.[key] ? (
                      <div key={key}>
                        <Label>{label}</Label>
                        <p className="whitespace-pre-wrap text-xs">
                          {context.active_mandate[key]}
                        </p>
                      </div>
                    ) : null
                  )}
                </div>
              </details>
            )}
          </div>
        )}

        {!editingMandate && (
          <details className="mt-4 border-t pt-3">
            <summary className="cursor-pointer text-xs">
              Objective history
            </summary>
            {versionsQuery.isError ? (
              <p role="alert" className="mt-2 text-xs">
                History could not be loaded.{" "}
                <button onClick={() => versionsQuery.refetch()}>
                  Try again
                </button>
              </p>
            ) : (
              versionsQuery.data?.map((v) => (
                <div key={v.id} className="mt-3 text-xs">
                  <p className="font-medium">
                    Version {v.version_number}
                    {v.id === context.active_mandate?.id ? " · current" : ""}
                  </p>
                  <p className="whitespace-pre-wrap">
                    {v.objective || "No objective recorded"}
                  </p>
                  <p className="text-muted-foreground">
                    {v.author_name || "Earlier case record"}
                    {v.created_at
                      ? ` · ${new Date(v.created_at).toLocaleString()}`
                      : ""}
                  </p>
                </div>
              ))
            )}
          </details>
        )}
      </section>
    </div>
  )
}
