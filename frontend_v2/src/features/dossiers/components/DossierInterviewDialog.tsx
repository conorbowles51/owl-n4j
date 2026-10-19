import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { dossiersAPI, type Dossier, type DossierInterview } from "../api"
import { useDossierMutation } from "../hooks"
import {
  datePrecision,
  localInterviewTime,
  type InterviewDatePrecision,
} from "../interview-date"
import { DossierEvidencePicker } from "./DossierEvidencePicker"

export function DossierInterviewDialog({
  dossier,
  interview,
  onClose,
}: {
  dossier: Dossier
  interview?: DossierInterview | null
  onClose: () => void
}) {
  const initialDate = interview?.date_value ?? interview?.interview_date
  const [precision, setPrecision] = useState<InterviewDatePrecision>(
    datePrecision(initialDate)
  )
  const [date, setDate] = useState(localInterviewTime(initialDate))
  const [participants, setParticipants] = useState(
    interview?.participants
      .map((person) =>
        typeof person === "string" ? person : String(person.name ?? "")
      )
      .join(", ") ?? dossier.display_name
  )
  const [notes, setNotes] = useState(interview?.working_notes ?? "")
  const [error, setError] = useState("")
  const [sources, setSources] = useState(
    (interview?.evidence_links ?? []).map((link) => ({
      id: link.evidence_file_id,
      label: link.evidence.original_filename,
      source_anchor: link.source_anchor,
    }))
  )
  const mutation = useDossierMutation<void>(
    dossier.case_id,
    dossier.id,
    async () => {
      const value =
        precision === "unknown"
          ? null
          : precision === "time"
            ? new Date(date).toISOString()
            : date
      const input = {
        date_value: value,
        participants: participants
          .split(",")
          .map((name) => name.trim())
          .filter(Boolean),
        working_notes: notes || null,
        status: interview?.status ?? "completed",
        evidence_links: sources.map((item) => ({
          evidence_file_id: item.id,
          source_anchor: item.source_anchor,
        })),
      }
      return interview
        ? dossiersAPI.updateInterview(dossier.id, interview.id, input)
        : dossiersAPI.createInterview(dossier.id, input)
    }
  )
  const save = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    try {
      await mutation.mutateAsync()
      toast.success(interview ? "Interview updated" : "Interview added")
      onClose()
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Could not save the interview. Your changes are kept; try again."
      )
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(value) => {
        if (!value && !mutation.isPending) onClose()
      }}
    >
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {interview
              ? "Edit interview or statement"
              : "Add interview or statement"}
          </DialogTitle>
          <DialogDescription>
            Link original evidence and record only as much of the date as you
            know.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void save(event)} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="interview-precision">Date precision</Label>
            <select
              id="interview-precision"
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={precision}
              disabled={mutation.isPending}
              onChange={(event) => {
                setPrecision(event.target.value as InterviewDatePrecision)
                setDate("")
              }}
            >
              <option value="unknown">Date unknown</option>
              <option value="year">Year only</option>
              <option value="month">Month and year</option>
              <option value="day">Full date</option>
              <option value="time">Date and time</option>
            </select>
          </div>
          {precision !== "unknown" && (
            <div className="grid gap-2">
              <Label htmlFor="interview-date">
                {precision === "year"
                  ? "Year"
                  : precision === "month"
                    ? "Month and year"
                    : precision === "day"
                      ? "Date"
                      : "Date and time"}
              </Label>
              <Input
                id="interview-date"
                required
                disabled={mutation.isPending}
                type={
                  precision === "year"
                    ? "text"
                    : precision === "time"
                      ? "datetime-local"
                      : precision === "day"
                        ? "date"
                        : "month"
                }
                inputMode={precision === "year" ? "numeric" : undefined}
                pattern={precision === "year" ? "[0-9]{4}" : undefined}
                value={date}
                onChange={(event) => setDate(event.target.value)}
                placeholder={precision === "year" ? "2025" : undefined}
              />
            </div>
          )}
          <div className="grid gap-2">
            <Label htmlFor="interview-participants">Participants</Label>
            <Input
              id="interview-participants"
              value={participants}
              disabled={mutation.isPending}
              onChange={(event) => setParticipants(event.target.value)}
              placeholder="Comma-separated names"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="interview-notes">Working notes</Label>
            <Textarea
              id="interview-notes"
              rows={5}
              value={notes}
              disabled={mutation.isPending}
              onChange={(event) => setNotes(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Source evidence</Label>
            {sources.map((item) => (
              <div
                key={item.id}
                className="flex min-w-0 items-center gap-2 rounded border p-2 text-xs"
              >
                <span className="min-w-0 flex-1 break-all">{item.label}</span>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={mutation.isPending}
                  onClick={() =>
                    setSources((items) =>
                      items.filter((value) => value.id !== item.id)
                    )
                  }
                >
                  Remove
                </Button>
              </div>
            ))}
            <DossierEvidencePicker
              caseId={dossier.case_id}
              selectedIds={sources.map((item) => item.id)}
              onSelect={(item) =>
                setSources((items) => [
                  ...items,
                  { ...item, source_anchor: {} },
                ])
              }
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              disabled={mutation.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={mutation.isPending || !sources.length}
            >
              {mutation.isPending
                ? "Saving…"
                : interview
                  ? "Save interview"
                  : "Add interview"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
