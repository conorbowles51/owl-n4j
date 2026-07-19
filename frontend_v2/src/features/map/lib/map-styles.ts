import { nodeColors, typeAliases } from "@/lib/theme"
import type { LayerProps } from "react-map-gl/maplibre"
import type { FilterSpecification } from "maplibre-gl"

/** Entity type → color match expression for MapLibre */
const entityColorMatch: unknown[] = [
  "match",
  ["get", "entityType"],
  ...Object.entries(nodeColors).flatMap(([type, color]) => [type, color]),
  ...Object.entries(typeAliases).flatMap(([alias, canonical]) => [alias, nodeColors[canonical]]),
  "#667D85", // fallback
]

const exactLocationFilter: FilterSpecification = ["!=", ["get", "isApproximate"], true]
const approximateLocationFilter: FilterSpecification = ["==", ["get", "isApproximate"], true]

// MapLibre only allows ["zoom"] as the input of a top-level "interpolate"/"step",
// so the granularity branch must sit inside each stop's output, not wrap the interpolate.
const isCityGranularity = ["==", ["get", "locationGranularity"], "city"]
const approximateRadius = [
  "interpolate", ["linear"], ["zoom"],
  0, ["case", isCityGranularity, 18, 10],
  8, ["case", isCityGranularity, 34, 22],
  14, ["case", isCityGranularity, 64, 38],
]

export const approximateLocationAreaLayer: LayerProps = {
  id: "approximate-location-area",
  type: "circle",
  filter: approximateLocationFilter,
  paint: {
    "circle-color": entityColorMatch as unknown as string,
    "circle-radius": approximateRadius as unknown as number,
    "circle-blur": 0.75,
    "circle-opacity": 0.28,
  },
}

export const approximateLocationOutlineLayer: LayerProps = {
  id: "approximate-location-outline",
  type: "circle",
  filter: approximateLocationFilter,
  paint: {
    "circle-color": "transparent",
    "circle-radius": approximateRadius as unknown as number,
    "circle-stroke-color": entityColorMatch as unknown as string,
    "circle-stroke-width": 1.5,
    "circle-stroke-opacity": 0.58,
  },
}

export const pointLayer: LayerProps = {
  id: "unclustered-point",
  type: "circle",
  filter: exactLocationFilter,
  paint: {
    "circle-color": entityColorMatch as unknown as string,
    "circle-radius": [
      "interpolate", ["linear"], ["zoom"],
      0, 4,
      8, 7,
      14, 9,
    ],
    "circle-stroke-width": 2,
    "circle-stroke-color": "#ffffff",
    "circle-opacity": 0.9,
  },
}

export const pointSelectedLayer: LayerProps = {
  id: "unclustered-point-selected",
  type: "circle",
  filter: exactLocationFilter,
  paint: {
    "circle-color": "transparent",
    "circle-radius": 12,
    "circle-stroke-width": 2,
    "circle-stroke-color": "#0C9DA0",
    "circle-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 1, 0],
  },
}

export const heatmapLayer: LayerProps = {
  id: "heatmap-layer",
  type: "heatmap",
  paint: {
    "heatmap-weight": ["interpolate", ["linear"], ["get", "connectionCount"], 0, 0.5, 10, 1],
    "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 0, 0.5, 9, 1.5],
    "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 0, 15, 9, 30],
    "heatmap-opacity": 0.7,
    "heatmap-color": [
      "interpolate",
      ["linear"],
      ["heatmap-density"],
      0, "rgba(0,0,0,0)",
      0.2, "#4F69C6",
      0.4, "#17879E",
      0.6, "#36B3B2",
      0.8, "#B7791F",
      1.0, "#B55473",
    ],
  },
}

export const proximityFillLayer: LayerProps = {
  id: "proximity-fill",
  type: "fill",
  paint: {
    "fill-color": "#0C9DA0",
    "fill-opacity": 0.1,
  },
}

export const proximityOutlineLayer: LayerProps = {
  id: "proximity-outline",
  type: "line",
  paint: {
    "line-color": "#0C9DA0",
    "line-width": 2,
    "line-dasharray": [3, 2],
    "line-opacity": 0.6,
  },
}
