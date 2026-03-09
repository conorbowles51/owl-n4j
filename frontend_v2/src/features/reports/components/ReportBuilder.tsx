import { useState } from "react"
import { FileBarChart, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useCreateReport } from "../hooks/use-reports"

interface ReportBuilderProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseId: string
}

const SECTIONS = [
  { key: "summary", label: "Executive Summary" },
  { key: "entities", label: "Key Entities" },
  { key: "relationships", label: "Relationships" },
  { key: "timeline", label: "Timeline" },
  { key: "financial", label: "Financial Analysis" },
  { key: "evidence", label: "Evidence Summary" },
  { key: "theories", label: "Theories" },
]

export function ReportBuilder({
  open,
  onOpenChange,
  caseId,
}: ReportBuilderProps) {
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [format, setFormat] = useState("html")
  const [sections, setSections] = useState<Set<string>>(
    new Set(SECTIONS.map((s) => s.key))
  )

  const createMutation = useCreateReport(caseId)

  const toggleSection = (key: string) => {
    const next = new Set(sections)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setSections(next)
  }

  const handleCreate = () => {
    if (!title.trim()) return
    createMutation.mutate(
      {
        title,
        description,
        format,
        sections: Array.from(sections),
      },
      {
        onSuccess: () => {
          onOpenChange(false)
          setTitle("")
          setDescription("")
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-sm">
            <FileBarChart className="size-4" />
            Create Report
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="mb-1 text-xs font-medium">Title</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Investigation Report"
            />
          </div>

          <div>
            <label className="mb-1 text-xs font-medium">Description</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description..."
              rows={2}
            />
          </div>

          <div>
            <label className="mb-1 text-xs font-medium">Format</label>
            <Select value={format} onValueChange={setFormat}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="html">HTML</SelectItem>
                <SelectItem value="pdf">PDF</SelectItem>
                <SelectItem value="markdown">Markdown</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="mb-1 text-xs font-medium">Sections</label>
            <div className="space-y-1 rounded-md border border-border p-2">
              {SECTIONS.map((section) => (
                <button
                  key={section.key}
                  onClick={() => toggleSection(section.key)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
                >
                  <Checkbox checked={sections.has(section.key)} />
                  {section.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={handleCreate}
            disabled={!title.trim() || createMutation.isPending}
          >
            <Sparkles className="size-3.5" />
            {createMutation.isPending ? "Generating..." : "Generate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
