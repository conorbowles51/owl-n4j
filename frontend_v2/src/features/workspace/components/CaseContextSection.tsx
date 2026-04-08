import { useState } from "react"
import { FileText, Edit2, Save, X, Calendar, Scale } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { useCaseContext, useUpdateCaseContext } from "../hooks/use-workspace"
import { formatWorkspaceDate } from "../lib/format-date"

interface CaseContextSectionProps {
  caseId: string
}

function stringifyRecord(value: unknown) {
  if (!value || typeof value !== "object") return ""
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return ""
  }
}

function parseRecord(value: string) {
  if (!value.trim()) return {}
  try {
    const parsed = JSON.parse(value)
    return typeof parsed === "object" && parsed !== null ? parsed : {}
  } catch {
    return { notes: value.trim() }
  }
}

function ListField({
  label,
  items,
  editing,
  onChange,
}: {
  label: string
  items: string[]
  editing: boolean
  onChange: (items: string[]) => void
}) {
  if (!editing && items.length === 0) return null

  return (
    <div className="space-y-1">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </p>
      {editing ? (
        <div className="space-y-1">
          {items.map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <Input
                value={item}
                onChange={(e) => {
                  const next = [...items]
                  next[i] = e.target.value
                  onChange(next)
                }}
                className="h-7 text-xs"
              />
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              >
                <X className="size-3" />
              </Button>
            </div>
          ))}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange([...items, ""])}
            className="text-xs"
          >
            + Add item
          </Button>
        </div>
      ) : (
        <ul className="space-y-0.5">
          {items.map((item, i) => (
            <li key={i} className="text-xs text-foreground/80">
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function CaseContextSection({ caseId }: CaseContextSectionProps) {
  const { data: context, isLoading } = useCaseContext(caseId)
  const updateMutation = useUpdateCaseContext(caseId)
  const [editing, setEditing] = useState(false)

  // Edit state
  const [summary, setSummary] = useState("")
  const [charges, setCharges] = useState<string[]>([])
  const [allegations, setAllegations] = useState<string[]>([])
  const [denials, setDenials] = useState<string[]>([])
  const [defenseStrategy, setDefenseStrategy] = useState<string[]>([])
  const [trialDate, setTrialDate] = useState("")
  const [clientProfile, setClientProfile] = useState("")
  const [legalExposure, setLegalExposure] = useState("")
  const [courtInfo, setCourtInfo] = useState("")

  const handleEdit = () => {
    setSummary(context?.summary ?? "")
    setCharges(context?.charges ?? [])
    setAllegations(context?.allegations ?? [])
    setDenials(context?.denials ?? [])
    setDefenseStrategy(context?.defense_strategy ?? [])
    setTrialDate(context?.trial_date ?? "")
    setClientProfile(stringifyRecord(context?.client_profile))
    setLegalExposure(stringifyRecord(context?.legal_exposure))
    setCourtInfo(stringifyRecord(context?.court_info))
    setEditing(true)
  }

  const handleSave = () => {
    updateMutation.mutate(
      {
        ...context,
        summary,
        charges: charges.filter(Boolean),
        allegations: allegations.filter(Boolean),
        denials: denials.filter(Boolean),
        defense_strategy: defenseStrategy.filter(Boolean),
        trial_date: trialDate || null,
        client_profile: parseRecord(clientProfile),
        legal_exposure: parseRecord(legalExposure),
        court_info: parseRecord(courtInfo),
      },
      { onSuccess: () => setEditing(false) },
    )
  }

  const hasSummary = !!context?.summary
  const hasCharges = (context?.charges?.length ?? 0) > 0
  const hasAllegations = (context?.allegations?.length ?? 0) > 0
  const hasDenials = (context?.denials?.length ?? 0) > 0
  const hasStrategy = (context?.defense_strategy?.length ?? 0) > 0
  const hasProfile = !!context?.client_profile && Object.keys(context.client_profile).length > 0
  const hasExposure = !!context?.legal_exposure && Object.keys(context.legal_exposure).length > 0
  const hasCourtInfo = !!context?.court_info && Object.keys(context.court_info).length > 0
  const hasAnyContent =
    hasSummary ||
    hasCharges ||
    hasAllegations ||
    hasDenials ||
    hasStrategy ||
    hasProfile ||
    hasExposure ||
    hasCourtInfo ||
    !!context?.trial_date

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText className="size-4 text-emerald-500" />
          <h3 className="text-xs font-semibold">Case Context</h3>
        </div>
        {editing ? (
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
              <X className="size-3" />
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSave}
              disabled={updateMutation.isPending}
            >
              <Save className="mr-1 size-3" />
              Save
            </Button>
          </div>
        ) : (
          <Button variant="ghost" size="sm" onClick={handleEdit}>
            <Edit2 className="size-3" />
          </Button>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="h-20 animate-pulse rounded-md bg-muted/30" />
      ) : editing ? (
        <div className="space-y-4 rounded-lg border border-border p-3">
          {/* Summary */}
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Summary
            </p>
            <Textarea
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Describe the case context..."
              rows={3}
              className="text-xs"
            />
          </div>

          {/* Trial Date */}
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Trial Date
            </p>
            <Input
              type="date"
              value={trialDate}
              onChange={(e) => setTrialDate(e.target.value)}
              className="h-7 w-48 text-xs"
            />
          </div>

          <ListField label="Charges" items={charges} editing onChange={setCharges} />
          <ListField label="Allegations" items={allegations} editing onChange={setAllegations} />
          <ListField label="Denials" items={denials} editing onChange={setDenials} />
          <ListField label="Defense Strategy" items={defenseStrategy} editing onChange={setDefenseStrategy} />

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Client Profile
              </p>
              <Textarea
                value={clientProfile}
                onChange={(e) => setClientProfile(e.target.value)}
                placeholder='JSON or free text, e.g. {"name":"Client"}'
                rows={6}
                className="text-xs"
              />
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Legal Exposure
              </p>
              <Textarea
                value={legalExposure}
                onChange={(e) => setLegalExposure(e.target.value)}
                placeholder='JSON or free text, e.g. {"max_sentence":"..."}'
                rows={6}
                className="text-xs"
              />
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Court Info
              </p>
              <Textarea
                value={courtInfo}
                onChange={(e) => setCourtInfo(e.target.value)}
                placeholder='JSON or free text, e.g. {"court":"..."}'
                rows={6}
                className="text-xs"
              />
            </div>
          </div>
        </div>
      ) : hasAnyContent ? (
        <div className="space-y-3 rounded-lg border border-border p-3">
          {hasSummary && (
            <p className="text-xs leading-relaxed text-foreground/80">{context.summary}</p>
          )}

          {context?.trial_date && (
            <div className="flex items-center gap-1.5">
              <Calendar className="size-3 text-muted-foreground" />
              <span className="text-[10px] font-medium">
                Trial: {formatWorkspaceDate(context.trial_date)}
              </span>
            </div>
          )}

          <ListField label="Charges" items={context?.charges ?? []} editing={false} onChange={() => {}} />
          <ListField label="Allegations" items={context?.allegations ?? []} editing={false} onChange={() => {}} />
          <ListField label="Denials" items={context?.denials ?? []} editing={false} onChange={() => {}} />
          <ListField label="Defense Strategy" items={context?.defense_strategy ?? []} editing={false} onChange={() => {}} />

          {context?.objectives && context.objectives.length > 0 && (
            <ListField label="Objectives" items={context.objectives} editing={false} onChange={() => {}} />
          )}

          <div className="grid gap-3 md:grid-cols-3">
            {hasProfile && (
              <div className="space-y-1 rounded-md bg-muted/20 p-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Client Profile
                </p>
                <pre className="whitespace-pre-wrap text-[11px] text-foreground/80">
                  {stringifyRecord(context?.client_profile)}
                </pre>
              </div>
            )}
            {hasExposure && (
              <div className="space-y-1 rounded-md bg-muted/20 p-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Legal Exposure
                </p>
                <pre className="whitespace-pre-wrap text-[11px] text-foreground/80">
                  {stringifyRecord(context?.legal_exposure)}
                </pre>
              </div>
            )}
            {hasCourtInfo && (
              <div className="space-y-1 rounded-md bg-muted/20 p-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Court Info
                </p>
                <pre className="whitespace-pre-wrap text-[11px] text-foreground/80">
                  {stringifyRecord(context?.court_info)}
                </pre>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-border py-6 text-center">
          <Scale className="mx-auto size-6 text-muted-foreground/30" />
          <p className="mt-1 text-xs text-muted-foreground">
            No context set. Click edit to add case details.
          </p>
        </div>
      )}
    </div>
  )
}
