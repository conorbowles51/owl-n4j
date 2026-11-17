import { Layer, Source } from "react-map-gl/maplibre"
import { useQuery } from "@tanstack/react-query"
import type { FeatureCollection, Point } from "geojson"
import { MAX_TOGETHER_PHONES, overlapsQuery } from "./phone-together"

/** Meeting points of the chosen phones on the Map: a ring per meeting, in the "together" accent. Child of a react-map-gl Map. */
export function MeetingLayer({ caseId, phoneIds, from, to, picked }: { caseId: string; phoneIds: string[]; from?: string | null; to?: string | null; picked?: string | null }) {
  const q = useQuery({ ...overlapsQuery(caseId, phoneIds, from, to), enabled: phoneIds.length >= 2 && phoneIds.length <= MAX_TOGETHER_PHONES })
  const data: FeatureCollection<Point> = {
    type: "FeatureCollection",
    features: (q.data?.together ?? []).map((m) => ({ type: "Feature", properties: { id: m.id, picked: m.id === picked ? 1 : 0 }, geometry: { type: "Point", coordinates: [m.place.lon, m.place.lat] } })),
  }
  return (
    <Source id="together-meetings" type="geojson" data={data}>
      <Layer id="together-ring" type="circle" paint={{ "circle-radius": ["case", ["==", ["get", "picked"], 1], 16, 11], "circle-color": "#6a2c91", "circle-opacity": 0.18, "circle-stroke-color": "#6a2c91", "circle-stroke-width": 2 }} />
    </Source>
  )
}
