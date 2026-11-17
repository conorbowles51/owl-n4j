import { Slider } from "@/components/ui/slider"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { RotateCcw } from "lucide-react"
import { useGraphStore } from "@/stores/graph.store"

const DEFAULTS = {
  linkDistance: 200,
  chargeStrength: -50,
  centerStrength: 0.4,
}

export function ForceControlsPanel() {
  const {
    linkDistance,
    chargeStrength,
    centerStrength,
    showRelationshipLabels,
    setLinkDistance,
    setChargeStrength,
    setCenterStrength,
    setShowRelationshipLabels,
  } = useGraphStore()

  const resetDefaults = () => {
    setLinkDistance(DEFAULTS.linkDistance)
    setChargeStrength(DEFAULTS.chargeStrength)
    setCenterStrength(DEFAULTS.centerStrength)
  }

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Spacing of the picture</h3>
        <Button variant="ghost" size="icon-sm" onClick={resetDefaults} title="Reset">
          <RotateCcw className="size-3.5" />
        </Button>
      </div>

      <div className="space-y-3">
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium">Line length</span>
            <span className="text-xs text-muted-foreground">{linkDistance}</span>
          </div>
          <Slider
            value={[linkDistance]}
            onValueChange={([v]) => setLinkDistance(v)}
            min={50}
            max={500}
            step={10}
          />
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium">Push apart</span>
            <span className="text-xs text-muted-foreground">{chargeStrength}</span>
          </div>
          <Slider
            value={[chargeStrength]}
            onValueChange={([v]) => setChargeStrength(v)}
            min={-2000}
            max={0}
            step={10}
          />
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-xs font-medium">Pull to the centre</span>
            <span className="text-xs text-muted-foreground">
              {centerStrength.toFixed(2)}
            </span>
          </div>
          <Slider
            value={[centerStrength * 100]}
            onValueChange={([v]) => setCenterStrength(v / 100)}
            min={0}
            max={100}
            step={1}
          />
        </div>

        <div className="flex items-center justify-between">
          <span className="text-xs font-medium">Name each line</span>
          <Switch
            aria-label="Name each line"
            checked={showRelationshipLabels}
            onCheckedChange={setShowRelationshipLabels}
          />
        </div>
      </div>
    </div>
  )
}
