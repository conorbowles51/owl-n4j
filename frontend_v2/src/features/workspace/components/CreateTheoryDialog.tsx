import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Lightbulb } from "lucide-react"
import { useCreateTheory } from "../hooks/use-workspace"

interface CreateTheoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
}

export function CreateTheoryDialog({
  open,
  onOpenChange,
  caseId,
}: CreateTheoryDialogProps) {
  const [title, setTitle] = useState("")
  const [type, setType] = useState<"PRIMARY" | "SECONDARY" | "NOTE">("PRIMARY")
  const [hypothesis, setHypothesis] = useState("")
  const [confidenceScore, setConfidenceScore] = useState(50)
  const [privilegeLevel, setPrivilegeLevel] = useState<
    "PUBLIC" | "ATTORNEY_ONLY" | "PRIVATE"
  >("PUBLIC")

  const createTheory = useCreateTheory(caseId)
  const isDirty = !!title.trim() || !!hypothesis.trim() || confidenceScore !== 50 || type !== "PRIMARY" || privilegeLevel !== "PUBLIC"

  function resetForm() {
    setTitle("")
    setType("PRIMARY")
    setHypothesis("")
    setConfidenceScore(50)
    setPrivilegeLevel("PUBLIC")
  }

  function handleSubmit() {
    createTheory.mutate(
      {
        title,
        type,
        hypothesis: hypothesis || undefined,
        confidence_score: confidenceScore,
        privilege_level: privilegeLevel,
      },
      {
        onSuccess: () => {
          resetForm()
          onOpenChange(false)
        },
      },
    )
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen && isDirty) return
        onOpenChange(nextOpen)
      }}
    >
      <DialogContent
        className="sm:max-w-md"
        onInteractOutside={(event) => {
          if (isDirty) event.preventDefault()
        }}
        onEscapeKeyDown={(event) => {
          if (isDirty) event.preventDefault()
        }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Lightbulb className="h-5 w-5" />
            New Theory
          </DialogTitle>
          <DialogDescription>
            Add a theory to this investigation. You can expand on it later.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="theory-title">Title</Label>
            <Input
              id="theory-title"
              placeholder="e.g. Primary suspect motive"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select value={type} onValueChange={(v) => setType(v as typeof type)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PRIMARY">Primary</SelectItem>
                  <SelectItem value="SECONDARY">Secondary</SelectItem>
                  <SelectItem value="NOTE">Note</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Privilege</Label>
              <Select
                value={privilegeLevel}
                onValueChange={(v) => setPrivilegeLevel(v as typeof privilegeLevel)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PUBLIC">Public</SelectItem>
                  <SelectItem value="ATTORNEY_ONLY">Attorney Only</SelectItem>
                  <SelectItem value="PRIVATE">Private</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="theory-hypothesis">Hypothesis</Label>
            <Textarea
              id="theory-hypothesis"
              placeholder="Describe your theory..."
              rows={3}
              value={hypothesis}
              onChange={(e) => setHypothesis(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label>Confidence — {confidenceScore}%</Label>
            <Slider
              value={[confidenceScore]}
              onValueChange={(vals) => setConfidenceScore(vals[0])}
              min={0}
              max={100}
              step={1}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!title.trim() || createTheory.isPending}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
