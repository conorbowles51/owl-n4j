import { useEffect, useRef, useState } from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { getPhoneMapNear, getPhoneMapPoints, getPhoneMapSummary, type PhoneMapFilter } from "@/features/phones/api"
import { PhoneLayerPanel } from "./PhoneLayer"
import { NearMessageNote } from "./NearMessageNote"
import { useParams, useSearchParams } from "react-router-dom"
import { MapPin } from "lucide-react"
import { Button } from "@/components/ui/button"
import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { EmptyState } from "@/components/ui/empty-state"
import { useMapData, useMapReviewQueue } from "../hooks/use-map-data"
import { useProximityAnalysis } from "../hooks/use-proximity-analysis"
import { useMapStore } from "../stores/map.store"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { needsReview } from "@/lib/location-confidence"
import { MapCanvas } from "./MapCanvas"
import { MapToolbar } from "./MapToolbar"
import { MapLegend } from "./MapLegend"
import { MapControls } from "./MapControls"
import { NeedsReviewPanel } from "./NeedsReviewPanel"
import { ProximityAnalysisPanel } from "./ProximityAnalysisPanel"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"
import { SignificantEmptyState } from "@/features/significant/components/SignificantEmptyState"

export function MapPage() {
  const { id: caseId } = useParams()
  const caseLayer = useCaseLayer(caseId)
  const locationsQuery = useMapData(caseId)
  const { data: locations, isLoading } = locationsQuery
  const {
    data: reviewQueue,
    isLoading: isReviewQueueLoading,
    isError: isReviewQueueError,
    refetch: refetchReviewQueue,
  } = useMapReviewQueue(caseId)
  const safeLocations = locations ?? []
  const reviewQueueCount = (reviewQueue ?? []).filter(needsReview).length

  const zoomIn = useMapStore((s) => s.zoomIn)
  const zoomOut = useMapStore((s) => s.zoomOut)
  const fitBounds = useMapStore((s) => s.fitBounds)
  const flyTo = useMapStore((s) => s.flyTo)
  const proximityAnchorKey = useMapStore((s) => s.proximityAnchorKey)
  const proximityRadius = useMapStore((s) => s.proximityRadius)
  const needsReviewMode = useMapStore((s) => s.needsReviewMode)
  const setProximityRadius = useMapStore((s) => s.setProximityRadius)

  const { anchor, results } = useProximityAnalysis(safeLocations)
  // Show on Map from a record (03 section 3.6): ?phone_point=<lon>,<lat> opens the phone layer centred on it
  const [params] = useSearchParams()
  const focusPoint = parsePoint(params.get("phone_point"))
  // Show on Map from a message: ?phone_near=<record uid> shows the same phone's positions within the hour of it
  const nearUid = params.get("phone_near")
  const near = useQuery({
    queryKey: ["phone-map-near", caseId, nearUid],
    queryFn: ({ signal }) => getPhoneMapNear(caseId!, nearUid!, signal),
    enabled: !!caseId && !!nearUid,
  })
  const nearFilter: PhoneMapFilter | undefined =
    near.data && near.data.within > 0
      ? { phones: [near.data.extraction_id], from_instant: near.data.from_instant ?? undefined, to_instant: near.data.to_instant ?? undefined, include_no_time: false }
      : undefined
  const phones = usePhoneLayer(caseId, isLoading ? null : safeLocations.length, !!focusPoint || !!nearUid, nearFilter)

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

  if (isLoading || phones.summary.isLoading || (safeLocations.length === 0 && isReviewQueueLoading)) {
    // The page-speed standard's panel (step in words, true counts, time left, slow and failed parts named), not a
    // bare spinner: the located entities of a large case take 0.7-0.8 s on the server and arrive as 1.8 MB.
    return (
      <div className="flex h-full items-start justify-center pt-6">
        <div className="w-full max-w-2xl">
          <LoadProgress caseId={caseId} page="case/map" />
        </div>
      </div>
    )
  }

  // A read that failed is named with a retry; it is never shown as "No location data".
  const failed = [
    locationsQuery.isError && !locations ? "the case's located entities" : null,
    phones.summary.isError && !phones.summary.data ? "the phones' positions" : null,
    isReviewQueueError && !reviewQueue ? "the locations needing review" : null,
  ].filter((part): part is string => part !== null)
  const retryFailed = () => {
    if (locationsQuery.isError) void locationsQuery.refetch()
    if (phones.summary.isError) void phones.summary.refetch()
    if (isReviewQueueError) void refetchReviewQueue()
  }
  if (failed.length && !safeLocations.length && !phones.summary.data?.positioned) {
    return (
      <div className="flex h-full items-start justify-center pt-6">
        <div role="alert" className="w-full max-w-2xl space-y-2 rounded-md border border-border bg-card p-4 text-sm" data-testid="map-load-failed">
          <p>The map could not load {failed.join(" and ")}. Nothing is shown rather than an empty map.</p>
          <Button variant="outline" onClick={retryFailed}>
            Try again
          </Button>
        </div>
      </div>
    )
  }

  if (!safeLocations.length && reviewQueueCount === 0 && !phones.summary.data?.positioned) {
    if (caseId && caseLayer === "significant") {
      return (
        <SignificantEmptyState
          caseId={caseId}
          icon={MapPin}
          eligibleTitle="No significant entities can be mapped"
          eligibleDescription="Your Significant layer has entities, but none currently have usable geographic coordinates."
        />
      )
    }
    return (
      <EmptyState
        icon={MapPin}
        title="No location data"
        description="Process evidence with geographic data to populate the map"
      />
    )
  }

  return (
    <div className="flex h-full flex-col bg-canvas">
      {failed.length > 0 && (
        <div role="alert" className="flex items-center gap-3 border-b border-border bg-card px-3 py-2 text-sm" data-testid="map-part-failed">
          <span>The map could not load {failed.join(" and ")}; what is shown does not include them.</span>
          <Button size="sm" variant="outline" onClick={retryFailed}>
            Try again
          </Button>
        </div>
      )}
      <MapToolbar caseId={caseId!} locations={safeLocations} phonePositions={phones.on ? phones.summary.data?.positioned ?? null : null} />

      <div className="relative flex-1">
        <MapCanvas
          locations={safeLocations}
          phoneItems={phones.on ? phones.points.data?.items : undefined}
          onView={phones.setView}
          fitTo={phones.on ? phones.summary.data?.bbox ?? null : null}
          focusPoint={focusPoint}
          focusBox={nearFilter ? near.data?.bbox ?? null : null}
        />
        {nearUid && !focusPoint && <NearMessageNote loading={near.isLoading} failed={near.isError} near={near.data} />}
        {phones.summary.data && phones.summary.data.total > 0 && (
          <button
            type="button"
            aria-pressed={phones.on}
            onClick={() => phones.setOn(!phones.on)}
            className="absolute left-3 top-3 z-10 rounded-md border border-border bg-card px-2 py-1 text-xs shadow-sm"
          >
            Phones
          </button>
        )}
        {phones.on && phones.summary.data && phones.summary.data.total > 0 && (
          <PhoneLayerPanel caseId={caseId!} summary={phones.summary.data} points={phones.points.data} />
        )}
        <MapLegend locations={safeLocations} />
        <MapControls
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onFitBounds={fitBounds}
        />
        {needsReviewMode && (
          <NeedsReviewPanel caseId={caseId!} locations={safeLocations} />
        )}
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

/**
 * The Map phone layer's state (03 section 13.3): on at first use when the case has no other located items, off
 * otherwise; that choice is stored for this person and case at first use and never recomputed (07 4.12).
 */
function parsePoint(v: string | null): [number, number] | null {
  const m = v?.split(",").map(Number)
  return m && m.length === 2 && m.every(Number.isFinite) && Math.abs(m[0]) <= 180 && Math.abs(m[1]) <= 90 ? [m[0], m[1]] : null
}

function usePhoneLayer(caseId: string | undefined, graphLocations: number | null, forced = false, scope?: PhoneMapFilter) {
  const key = `loupe.map.phones.${caseId}`
  const [stored, setStored] = useState<string | null>(() => (caseId ? localStorage.getItem(key) : null))
  const [view, setView] = useState<{ bbox: number[]; zoom: number } | null>(null)
  const summary = useQuery({
    queryKey: ["phone-map-summary", caseId, scope ?? null],
    queryFn: ({ signal }) => getPhoneMapSummary(caseId!, scope ?? {}, signal),
    enabled: !!caseId,
    staleTime: 30_000,
  })
  useEffect(() => {
    if (!caseId || stored !== null || graphLocations === null || !summary.data) return
    const first = graphLocations === 0 ? "on" : "off"
    localStorage.setItem(key, first)
    setStored(first)
  }, [caseId, key, stored, graphLocations, summary.data])
  // a Show on Map link shows the layer for this visit without changing the stored choice
  const on = stored === "on" || forced
  const points = useQuery({
    queryKey: ["phone-map-points", caseId, view?.bbox.map((v) => v.toFixed(4)).join(","), view ? Math.round(view.zoom) : null, scope ?? null],
    queryFn: ({ signal }) => getPhoneMapPoints(caseId!, view!.bbox, view!.zoom, scope ?? {}, signal),
    enabled: !!caseId && on && !!view && !!summary.data?.positioned,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
  return {
    summary,
    points,
    on,
    setOn: (v: boolean) => {
      localStorage.setItem(key, v ? "on" : "off")
      setStored(v ? "on" : "off")
    },
    setView: (bbox: number[], zoom: number) => setView({ bbox, zoom }),
  }
}
