import { useEffect, useRef } from "react"
import { useParams } from "react-router-dom"
import { MapPin } from "lucide-react"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useMapData } from "../hooks/use-map-data"
import { useProximityAnalysis } from "../hooks/use-proximity-analysis"
import { useMapStore } from "../stores/map.store"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { MapCanvas } from "./MapCanvas"
import { MapToolbar } from "./MapToolbar"
import { MapLegend } from "./MapLegend"
import { MapControls } from "./MapControls"
import { ProximityAnalysisPanel } from "./ProximityAnalysisPanel"

export function MapPage() {
  const { id: caseId } = useParams()
  const { data: locations, isLoading } = useMapData(caseId)
  const safeLocations = locations ?? []

  const zoomIn = useMapStore((s) => s.zoomIn)
  const zoomOut = useMapStore((s) => s.zoomOut)
  const fitBounds = useMapStore((s) => s.fitBounds)
  const flyTo = useMapStore((s) => s.flyTo)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const proximityRadius = useMapStore((s) => s.proximityRadius)
  const setProximityRadius = useMapStore((s) => s.setProximityRadius)

  const { anchor, results } = useProximityAnalysis(safeLocations)

  // Auto-expand CaseLayout's side panel to detail tab when a node is selected from the map
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)
  const selectedNodeKeys = useGraphStore((s) => s.selectedNodeKeys)

  const prevKeysRef = useRef(selectedNodeKeys)
  useEffect(() => {
    const prev = prevKeysRef.current
    prevKeysRef.current = selectedNodeKeys
    if (selectedNodeKeys.size > 0 && selectedNodeKeys !== prev) {
      expandGraphPanelTo("detail")
    }
  }, [selectedNodeKeys, expandGraphPanelTo])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!safeLocations.length) {
    return (
      <EmptyState
        icon={MapPin}
        title="No location data"
        description="Process evidence with geographic data to populate the map"
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      <MapToolbar caseId={caseId!} locations={safeLocations} />

      <div className="relative flex-1">
        <MapCanvas locations={safeLocations} />
        <MapLegend locations={safeLocations} />
        <MapControls
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onFitBounds={fitBounds}
        />
        {proximityAnchorKey && (
          <div className="absolute bottom-3 right-3 z-10 w-72 rounded-lg border border-border bg-card/95 p-3 shadow-md backdrop-blur">
            <ProximityAnalysisPanel
              anchor={anchor}
              radius={proximityRadius}
              onRadiusChange={setProximityRadius}
              results={results}
              onSelectResult={(loc) =>
                flyTo({ longitude: loc.longitude, latitude: loc.latitude })
              }
            />
          </div>
        )}
      </div>
    </div>
  )
}
