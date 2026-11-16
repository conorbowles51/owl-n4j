import { useEffect, useState } from "react"
import { Layer, Popup, Source, useMap } from "react-map-gl/maplibre"
import type { FeatureCollection, LineString } from "geojson"
import type { Trajectory } from "../lib/places-geo"
import { instantWords } from "@/features/phones/lib/time-words"

const ARROW = "route-arrow"
const EMPTY = { type: "FeatureCollection", features: [] } as FeatureCollection<LineString>

/** A white arrowhead pointing right, drawn once as an SDF image so each route tints it in its phone's colour. */
function arrowImage(): ImageData {
  const size = 24
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = size
  const ctx = canvas.getContext("2d")!
  ctx.fillStyle = "#fff"
  ctx.beginPath()
  ctx.moveTo(20, 12)
  ctx.lineTo(5, 3)
  ctx.lineTo(9, 12)
  ctx.lineTo(5, 21)
  ctx.closePath()
  ctx.fill()
  return ctx.getImageData(0, 0, size, size)
}

/**
 * Each phone's route in its colour with pointed arrowheads along it. The arrow is placed along the line every
 * 90 screen pixels, so it stays readable zoomed out, and turns with the line from the earlier position to the later.
 * Hovering a leg states its from and to times and positions. Child of a react-map-gl Map.
 */
export function RouteLayers({ route, colours, labels, zone, idPrefix = "route" }: { route: Trajectory; colours: Record<string, string>; labels: Record<string, string>; zone: string; idPrefix?: string }) {
  const { current: ref } = useMap()
  const [ready, setReady] = useState(false)
  const [hover, setHover] = useState<{ lng: number; lat: number; text: string } | null>(null)
  const hit = `${idPrefix}-hit`
  useEffect(() => {
    const map = ref?.getMap()
    if (!map) return
    if (!map.hasImage(ARROW)) map.addImage(ARROW, arrowImage(), { sdf: true })
    setReady(true)
    const move = (e: { lngLat: { lng: number; lat: number }; features?: { properties?: Record<string, string> }[] }) => {
      const f = e.features?.[0]?.properties
      if (!f) return
      map.getCanvas().style.cursor = "pointer"
      setHover({ lng: e.lngLat.lng, lat: e.lngLat.lat, text: `${labels[f.phone] ? `${labels[f.phone]}: ` : ""}from ${instantWords(f.from, zone)} at ${f.from_at} to ${instantWords(f.to, zone)} at ${f.to_at}` })
    }
    const leave = () => { map.getCanvas().style.cursor = ""; setHover(null) }
    map.on("mousemove", hit, move)
    map.on("mouseleave", hit, leave)
    return () => { map.off("mousemove", hit, move); map.off("mouseleave", hit, leave) }
  }, [ref, hit, zone, labels])
  const colour: unknown[] = ["match", ["get", "phone"], ...Object.entries(colours).flatMap(([k, v]) => [k, v]), "#444444"]
  return (
    <>
      <Source id={`${idPrefix}-lines`} type="geojson" data={route.lines ?? EMPTY}>
        <Layer id={`${idPrefix}-line`} type="line" paint={{ "line-color": colour as never, "line-width": 2.5, "line-opacity": 0.85 }} />
        {ready && (
          <Layer id={`${idPrefix}-arrows`} type="symbol"
            layout={{ "symbol-placement": "line", "symbol-spacing": 90, "icon-image": ARROW, "icon-size": 0.7, "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-rotation-alignment": "map", "text-font": ["Noto Sans Regular"] }}
            paint={{ "icon-color": colour as never, "icon-halo-color": "#ffffff", "icon-halo-width": 1 }} />
        )}
      </Source>
      <Source id={`${idPrefix}-legs`} type="geojson" data={route.legs ?? EMPTY}>
        <Layer id={hit} type="line" paint={{ "line-color": "#000000", "line-opacity": 0, "line-width": 14 }} />
      </Source>
      {hover && <Popup longitude={hover.lng} latitude={hover.lat} closeButton={false} closeOnClick={false} anchor="bottom"><span className="text-xs text-black">{hover.text}</span></Popup>}
    </>
  )
}
