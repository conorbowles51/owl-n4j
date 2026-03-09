import { useParams } from "react-router-dom"
import { MapPin, Layers, Filter } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import { useQuery } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"

interface MapLocation {
  key: string
  label: string
  type: string
  latitude: number
  longitude: number
}

function useMapData(caseId: string | undefined) {
  return useQuery({
    queryKey: ["map", caseId],
    queryFn: () =>
      fetchAPI<MapLocation[]>(`/api/graph/locations?case_id=${caseId}`),
    enabled: !!caseId,
  })
}

export function MapPage() {
  const { id: caseId } = useParams()
  const { data: locations, isLoading } = useMapData(caseId)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (!locations?.length) {
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
      {/* Controls */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Button variant="ghost" size="sm">
          <Filter className="size-3.5" />
          Filters
        </Button>
        <Button variant="ghost" size="sm">
          <Layers className="size-3.5" />
          Layers
        </Button>
        <div className="flex-1" />
        <span className="text-xs text-muted-foreground">
          {locations.length} locations
        </span>
      </div>

      {/* Map placeholder — Leaflet integration will go here */}
      <div className="relative flex-1 bg-slate-900">
        <div className="flex h-full items-center justify-center">
          <div className="text-center">
            <MapPin className="mx-auto mb-2 size-8 text-amber-500" />
            <p className="text-sm font-medium">
              {locations.length} locations loaded
            </p>
            <p className="text-xs text-muted-foreground">
              Leaflet map integration pending
            </p>
          </div>
        </div>

        {/* Location list overlay */}
        <div className="absolute bottom-3 left-3 max-h-[200px] w-64 overflow-auto rounded-lg border border-border bg-card/95 p-2 backdrop-blur">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Locations
          </p>
          {locations.slice(0, 20).map((loc) => (
            <div
              key={loc.key}
              className="flex items-center gap-2 rounded px-2 py-1 text-xs hover:bg-muted"
            >
              <MapPin className="size-3 text-amber-500" />
              <span className="truncate">{loc.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
