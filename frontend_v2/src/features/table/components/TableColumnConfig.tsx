import { useState } from "react"
import { Columns, GripVertical, Eye, EyeOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Checkbox } from "@/components/ui/checkbox"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/cn"

export interface ColumnConfig {
  key: string
  label: string
  visible: boolean
}

interface TableColumnConfigProps {
  columns: ColumnConfig[]
  onChange: (columns: ColumnConfig[]) => void
}

export function TableColumnConfig({ columns, onChange }: TableColumnConfigProps) {
  const [open, setOpen] = useState(false)

  const toggleColumn = (key: string) => {
    onChange(
      columns.map((col) =>
        col.key === key ? { ...col, visible: !col.visible } : col
      )
    )
  }

  const visibleCount = columns.filter((c) => c.visible).length

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          <Columns className="size-3.5" />
          Columns
          <span className="ml-1 text-muted-foreground">({visibleCount})</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-56 p-0">
        <div className="border-b border-border px-3 py-2">
          <p className="text-xs font-semibold">Toggle columns</p>
        </div>
        <ScrollArea className="max-h-64">
          <div className="p-1">
            {columns.map((col) => (
              <button
                key={col.key}
                onClick={() => toggleColumn(col.key)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs hover:bg-muted",
                  !col.visible && "text-muted-foreground"
                )}
              >
                <Checkbox checked={col.visible} />
                <GripVertical className="size-3 text-muted-foreground" />
                <span className="flex-1 text-left">{col.label}</span>
                {col.visible ? (
                  <Eye className="size-3 text-muted-foreground" />
                ) : (
                  <EyeOff className="size-3 text-muted-foreground" />
                )}
              </button>
            ))}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
