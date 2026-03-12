import { Popup } from "react-map-gl/maplibre"
import { Crosshair, ExternalLink, MapPin } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NodeBadge } from "@/components/ui/node-badge"
import { Badge } from "@/components/ui/badge"
import type { MapLocation } from "../hooks/use-map-data"
import type { EntityType } from "@/lib/theme"

interface EntityPopupProps {
  location: MapLocation
  onClose: () => void
  onSetProximityAnchor: (key: string) => void
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export function EntityPopup({
  location,
  onClose,
  onSetProximityAnchor,
  onMouseEnter,
  onMouseLeave,
}: EntityPopupProps) {
  return (
    <Popup
      longitude={location.longitude}
      latitude={location.latitude}
      onClose={onClose}
      closeOnClick={false}
      offset={12}
      className="map-entity-popup"
      maxWidth="280px"
    >
      <div className="flex flex-col gap-2 p-1" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
        {/* Header */}
        <div className="flex items-center gap-2">
          <NodeBadge type={location.type as EntityType} />
          <span className="text-xs font-semibold">{location.name}</span>
        </div>

        {/* Coordinates */}
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <MapPin className="size-3" />
          <span>
            {location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}
          </span>
          {location.geocoding_confidence && (
            <Badge variant="outline" className="ml-1 text-[9px]">
              {location.geocoding_confidence}
            </Badge>
          )}
        </div>

        {/* Location info */}
        {location.location_formatted && (
          <p className="text-[10px] text-muted-foreground">
            {location.location_formatted}
          </p>
        )}

        {/* Summary */}
        {location.summary && (
          <p className="text-[10px] leading-relaxed text-muted-foreground line-clamp-2">
            {location.summary}
          </p>
        )}

        {/* Date */}
        {location.date && (
          <p className="text-[10px] text-muted-foreground">
            Date: {location.date}
          </p>
        )}

        {/* Connections */}
        {location.connections && location.connections.length > 0 && (
          <p className="text-[10px] text-muted-foreground">
            {location.connections.length} connection{location.connections.length !== 1 ? "s" : ""}
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center gap-1 border-t border-border pt-1.5">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px]"
            onClick={() => onSetProximityAnchor(location.key)}
          >
            <Crosshair className="mr-1 size-3" />
            Set as anchor
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-[10px]"
            asChild
          >
            <a href={`#graph?highlight=${location.key}`}>
              <ExternalLink className="mr-1 size-3" />
              View in graph
            </a>
          </Button>
        </div>
      </div>
    </Popup>
  )
}
