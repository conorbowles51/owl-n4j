import type { PhoneMapItem } from "@/features/phones/api"
import { accuracyPixelsAtZoom20 } from "../components/map-accuracy"

/**
 * The Map phone layer's features. A point whose record is in the lead shown with "Show these records" carries
 * `shown: true`, which draws an amber ring around it. A cluster cannot say which records it holds, so it is never
 * marked; the points appear, marked, once the map is close enough to draw them one by one.
 */
export function phoneGeoJSON(items: PhoneMapItem[], isShown: (recordUid: string) => boolean = () => false): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: items.map((i) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [i.lon, i.lat] },
      properties: i.type === "point"
        ? { kind: "point", has_accuracy: i.accuracy_m !== null, accuracy_m: i.accuracy_m ?? 0, r20: accuracyPixelsAtZoom20(i.accuracy_m ?? 0, i.lat), label: i.phone_label, phone: i.extraction_id, shown: isShown(i.record_uid) }
        : { kind: "cluster", has_accuracy: false, count: i.count, label: i.count.toLocaleString("en-US"), shown: false },
    })),
  }
}
