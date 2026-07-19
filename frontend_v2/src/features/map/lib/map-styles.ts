import { nodeColors, typeAliases } from "@/lib/theme"
import type { LayerProps } from "react-map-gl/maplibre"

/** Entity type → color match expression for MapLibre */
const entityColorMatch: unknown[] = [
  "match",
  ["get", "entityType"],
  ...Object.entries(nodeColors).flatMap(([type, color]) => [type, color]),
  ...Object.entries(typeAliases).flatMap(([alias, canonical]) => [alias, nodeColors[canonical]]),
  "#667D85", // fallback
]

export const pointLayer: LayerProps = {
  id: "unclustered-point",
  type: "circle",
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

export const boundingShapeFillLayer: LayerProps = {
  id: "bounding-shape-fill",
  type: "fill",
  paint: {
    "fill-color": "#B7791F",
    "fill-opacity": 0.12,
  },
}

export const boundingShapeOutlineLayer: LayerProps = {
  id: "bounding-shape-outline",
  type: "line",
  paint: {
    "line-color": "#B7791F",
    "line-width": 2,
    "line-opacity": 0.85,
  },
}

export const draftBoundingShapeFillLayer: LayerProps = {
  id: "draft-bounding-shape-fill",
  type: "fill",
  paint: {
    "fill-color": "#B7791F",
    "fill-opacity": 0.07,
  },
}

export const draftBoundingShapeOutlineLayer: LayerProps = {
  id: "draft-bounding-shape-outline",
  type: "line",
  paint: {
    "line-color": "#B7791F",
    "line-width": 2,
    "line-dasharray": [3, 2],
    "line-opacity": 0.65,
  },
}

export const drawingShapeFillLayer: LayerProps = {
  id: "drawing-shape-fill",
  type: "fill",
  paint: {
    "fill-color": "#B7791F",
    "fill-opacity": 0.08,
  },
}

export const drawingShapeOutlineLayer: LayerProps = {
  id: "drawing-shape-outline",
  type: "line",
  paint: {
    "line-color": "#B7791F",
    "line-width": 2,
    "line-dasharray": [2, 2],
    "line-opacity": 0.8,
  },
}

export const drawingLineLayer: LayerProps = {
  id: "drawing-shape-line",
  type: "line",
  paint: {
    "line-color": "#B7791F",
    "line-width": 2,
    "line-dasharray": [2, 2],
    "line-opacity": 0.8,
  },
}

export const drawingPointLayer: LayerProps = {
  id: "drawing-shape-point",
  type: "circle",
  paint: {
    "circle-color": "#ffffff",
    "circle-radius": 5,
    "circle-stroke-color": "#B7791F",
    "circle-stroke-width": 2,
  },
}
