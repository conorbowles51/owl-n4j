import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { useCreateDeadline } from "../hooks/use-deadlines"

interface AddDeadlineDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
}

export function AddDeadlineDialog({
  open,
  onOpenChange,
  caseId,
}: AddDeadlineDialogProps) {
  const [name, setName] = useState("")
  const [dueDate, setDueDate] = useState("")
  const createDeadline = useCreateDeadline(caseId)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await createDeadline.mutateAsync({ name, due_date: dueDate })
    setName("")
    setDueDate("")
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add Deadline</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Name
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Filing due, Court hearing"
              autoFocus
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Due Date
            </label>
            <Input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              type="button"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={!name.trim() || !dueDate || createDeadline.isPending}
            >
              {createDeadline.isPending ? (
                <LoadingSpinner size="sm" />
              ) : (
                "Add Deadline"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
