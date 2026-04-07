import { useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Plus, X } from "lucide-react"
import { toast } from "sonner"

interface InstructionListEditorProps {
  label: string
  description?: string
  instructions: string[]
  onChange: (instructions: string[]) => void
  placeholder?: string
  badgeVariant?: "secondary" | "amber" | "info" | "warning" | "slate"
}

export function InstructionListEditor({
  label,
  description,
  instructions,
  onChange,
  placeholder = "Extract every transaction as a separate financial event.",
  badgeVariant = "secondary",
}: InstructionListEditorProps) {
  const [newInstruction, setNewInstruction] = useState("")

  const addInstruction = () => {
    const instruction = newInstruction.trim()
    if (!instruction) return

    if (instructions.some((item) => item.toLowerCase() === instruction.toLowerCase())) {
      toast.error("Instruction already exists")
      return
    }

    onChange([...instructions, instruction])
    setNewInstruction("")
  }

  const removeInstruction = (index: number) => {
    onChange(instructions.filter((_, itemIndex) => itemIndex !== index))
  }

  return (
    <div className="space-y-2 rounded-lg border border-border p-4">
      <div className="space-y-1">
        <Label>{label}</Label>
        {description ? (
          <p className="text-[10px] text-muted-foreground">{description}</p>
        ) : null}
      </div>

      {instructions.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {instructions.map((instruction, index) => (
            <Badge key={`${instruction}-${index}`} variant={badgeVariant} className="gap-1 pr-1">
              <span className="max-w-[420px] truncate" title={instruction}>
                {instruction}
              </span>
              <button
                type="button"
                onClick={() => removeInstruction(index)}
                className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-muted/40"
                aria-label={`Remove instruction ${index + 1}`}
              >
                <X className="size-2.5" />
              </button>
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          No mandatory instructions set.
        </p>
      )}

      <div className="grid gap-2 md:grid-cols-[1fr_auto]">
        <Input
          value={newInstruction}
          onChange={(event) => setNewInstruction(event.target.value)}
          placeholder={placeholder}
          className="h-8 text-xs"
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault()
              addInstruction()
            }
          }}
        />
        <Button
          variant="outline"
          size="sm"
          onClick={addInstruction}
          disabled={!newInstruction.trim()}
        >
          <Plus className="size-3.5" />
          Add Rule
        </Button>
      </div>
    </div>
  )
}
