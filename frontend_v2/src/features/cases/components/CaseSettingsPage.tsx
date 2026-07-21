import { useState, type FormEvent } from "react"
import {
  AlertCircle,
  CheckCircle2,
  CirclePause,
  Clock3,
  FilePenLine,
  LoaderCircle,
  RotateCcw,
  Save,
  ShieldCheck,
} from "lucide-react"
import { useParams } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { PageHeader } from "@/components/ui/page-header"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/cn"
import type {
  Case,
  CaseMetadataUpdate,
  CaseStatus,
} from "@/types/case.types"
import { useCase, useUpdateCase } from "../hooks/use-cases"

const STATUS_OPTIONS: Array<{
  value: CaseStatus
  label: string
  description: string
}> = [
  {
    value: "active",
    label: "Active",
    description: "Investigation work is in progress.",
  },
  {
    value: "on_hold",
    label: "On hold",
    description: "Work is paused but the case remains available.",
  },
  {
    value: "closed",
    label: "Closed",
    description: "Investigation work is complete.",
  },
]

const STATUS_BADGES: Record<
  CaseStatus,
  { label: string; variant: "success" | "warning" | "slate" }
> = {
  active: { label: "Active", variant: "success" },
  on_hold: { label: "On hold", variant: "warning" },
  closed: { label: "Closed", variant: "slate" },
}

function canEditCase(caseData: Case) {
  return ["owner", "editor", "admin_access"].includes(caseData.user_role)
}

function CaseMetadataForm({
  caseData,
  onSave,
  isSaving,
}: {
  caseData: Case
  onSave: (update: CaseMetadataUpdate) => Promise<Case>
  isSaving: boolean
}) {
  const editable = canEditCase(caseData)
  const [title, setTitle] = useState(caseData.title)
  const [description, setDescription] = useState(caseData.description ?? "")
  const [status, setStatus] = useState<CaseStatus>(caseData.status)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const normalizedTitle = title.trim().replace(/\s+/g, " ")
  const isDirty =
    normalizedTitle !== caseData.title ||
    description.trim() !== (caseData.description ?? "") ||
    status !== caseData.status
  const titleError = normalizedTitle.length === 0 ? "Enter a case title." : null
  const selectedStatus = STATUS_OPTIONS.find((option) => option.value === status)!

  const reset = () => {
    setTitle(caseData.title)
    setDescription(caseData.description ?? "")
    setStatus(caseData.status)
    setError(null)
    setSaved(false)
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!editable || titleError || !isDirty) return

    setError(null)
    setSaved(false)
    try {
      const updated = await onSave({
        title: normalizedTitle,
        description: description.trim() || null,
        status,
      })
      setTitle(updated.title)
      setDescription(updated.description ?? "")
      setStatus(updated.status)
      setSaved(true)
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Case details could not be saved. Try again."
      )
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {!editable && (
        <div className="flex gap-3 rounded-md border border-amber-500/25 bg-amber-500/8 px-3.5 py-3 text-sm text-foreground">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <div>
            <p className="font-medium">You have view-only access</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              A case owner or editor can change these details.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/8 px-3.5 py-3 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">Changes were not saved</p>
            <p className="mt-0.5 text-xs opacity-90">{error}</p>
          </div>
        </div>
      )}

      {saved && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-md border border-emerald-500/25 bg-emerald-500/8 px-3.5 py-2.5 text-sm text-emerald-700 dark:text-emerald-300"
        >
          <CheckCircle2 className="size-4" />
          <span className="font-medium">Case details saved</span>
        </div>
      )}

      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between gap-4">
          <Label htmlFor="case-title">Case title</Label>
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {title.length}/255
          </span>
        </div>
        <Input
          id="case-title"
          value={title}
          onChange={(event) => {
            setTitle(event.target.value)
            setSaved(false)
          }}
          maxLength={255}
          disabled={!editable || isSaving}
          aria-invalid={!!titleError}
          aria-describedby={titleError ? "case-title-error" : "case-title-help"}
        />
        {titleError ? (
          <p id="case-title-error" className="text-xs text-destructive">
            {titleError}
          </p>
        ) : (
          <p id="case-title-help" className="text-xs text-muted-foreground">
            The name shown in case navigation, reports, and audit history.
          </p>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex items-baseline justify-between gap-4">
          <Label htmlFor="case-description">Description</Label>
          <span className="text-[11px] tabular-nums text-muted-foreground">
            {description.length}/5000
          </span>
        </div>
        <Textarea
          id="case-description"
          value={description}
          onChange={(event) => {
            setDescription(event.target.value)
            setSaved(false)
          }}
          maxLength={5000}
          rows={5}
          disabled={!editable || isSaving}
          placeholder="Add the purpose, scope, or handling context for this case."
          className="min-h-28 resize-y"
        />
        <p className="text-xs text-muted-foreground">
          Optional. Leave blank to remove the current description.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="case-status">Case status</Label>
        <select
          id="case-status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as CaseStatus)
            setSaved(false)
          }}
          disabled={!editable || isSaving}
          className={cn(
            "h-9 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground shadow-xs outline-none transition-[border-color,box-shadow]",
            "focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30",
            "disabled:cursor-not-allowed disabled:opacity-50"
          )}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {status === "active" ? (
            <CheckCircle2 className="size-3.5 text-emerald-500" />
          ) : status === "on_hold" ? (
            <CirclePause className="size-3.5 text-amber-500" />
          ) : (
            <Clock3 className="size-3.5" />
          )}
          {selectedStatus.description} Status does not archive the case.
        </p>
      </div>

      {editable && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            Saved changes are recorded in the system audit log.
          </p>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={reset}
              disabled={!isDirty || isSaving}
            >
              <RotateCcw />
              Reset
            </Button>
            <Button
              type="submit"
              disabled={!isDirty || !!titleError || isSaving}
            >
              {isSaving ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Save />
              )}
              {isSaving ? "Saving..." : "Save changes"}
            </Button>
          </div>
        </div>
      )}
    </form>
  )
}

export function CaseSettingsPage() {
  const { id } = useParams()
  const { data: caseData, isLoading, isError, refetch } = useCase(id)
  const updateCase = useUpdateCase(id)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (isError || !caseData) {
    return (
      <div className="flex h-full items-center justify-center bg-background p-6">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle>Case settings are unavailable</CardTitle>
            <CardDescription>
              The case details could not be loaded. Your data has not changed.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="outline" onClick={() => refetch()}>
              Try again
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const statusBadge = STATUS_BADGES[caseData.status]

  return (
    <div className="h-full overflow-y-auto bg-background">
      <div className="mx-auto w-full max-w-3xl p-6 lg:p-8">
        <PageHeader
          title="Case settings"
          description="Manage the identifying details and workflow state for this case."
          actions={<Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>}
        />

        <Card className="mt-6 gap-5 p-5">
          <CardHeader className="grid-cols-[auto_1fr] grid-rows-[auto_auto] gap-x-3">
            <div className="row-span-2 flex size-9 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
              <FilePenLine className="size-4" />
            </div>
            <CardTitle className="self-end text-base">Case details</CardTitle>
            <CardDescription>
              Keep the title, context, and lifecycle state accurate for everyone
              working in the case.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <CaseMetadataForm
              caseData={caseData}
              onSave={(update) => updateCase.mutateAsync(update)}
              isSaving={updateCase.isPending}
            />
          </CardContent>
          <CardFooter className="justify-between gap-3 text-[11px] text-muted-foreground">
            <span>Case ID {caseData.id}</span>
            <span>
              Last updated {new Date(caseData.updated_at).toLocaleString()}
            </span>
          </CardFooter>
        </Card>
      </div>
    </div>
  )
}
