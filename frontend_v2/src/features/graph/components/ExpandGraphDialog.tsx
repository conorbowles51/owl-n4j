import { useState } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { Badge } from "@/components/ui/badge"

interface ExpandGraphDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeCount: number
  onExpand: (depth: number) => void
}

export function ExpandGraphDialog({ open, onOpenChange, nodeCount, onExpand }: ExpandGraphDialogProps) {
  const [depth, setDepth] = useState([1])

  const handleExpand = () => {
    onExpand(depth[0])
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Expand Graph</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Expand <Badge variant="amber">{nodeCount}</Badge> selected node{nodeCount !== 1 ? "s" : ""} by finding connected entities.
          </p>
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs font-medium">Depth</label>
              <span className="text-xs text-muted-foreground">{depth[0]} hop{depth[0] !== 1 ? "s" : ""}</span>
            </div>
            <Slider value={depth} onValueChange={setDepth} min={1} max={5} step={1} />
          </div>
          <p className="text-[10px] text-muted-foreground">
            Higher depth values may return many nodes. Start with 1-2 hops.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="primary" onClick={handleExpand}>Expand</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
