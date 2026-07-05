import { useEffect, useMemo, useState } from "react"
import MapLibreMap, { Marker } from "react-map-gl/maplibre"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import { CalendarClock, ChevronDown, LocateFixed, MapPin, Search, X } from "lucide-react"
import { useQueryClient } from "@tanstack/react-query"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { NodeBadge } from "@/components/ui/node-badge"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { cn } from "@/lib/cn"
import { useMapTheme } from "@/features/map/hooks/use-map-theme"
import type { GraphEditPropertySchema } from "../api"
import { graphAPI } from "../api"
import { useGraphEditSchema, useNodeDetails } from "../hooks/use-node-details"

interface EditNodeDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeKey: string | null
  caseId: string
  onSaved?: () => void
}

interface EditableProperty {
  key: string
  label: string
  kind: "string" | "number" | "boolean"
  value: string
  enum?: string[]
}

interface Coordinates {
  latitude: number
  longitude: number
}

const FIELD_KEY_RE = /^[A-Za-z][A-Za-z0-9_]*$/
const NONE_VALUE = "__none"

const basicKeys = new Set(["name", "label", "summary", "notes", "specific_type"])
const timelineKeys = new Set(["date", "time", "date_precision"])
const locationKeys = new Set(["latitude", "longitude", "location_raw", "location_formatted", "location_name"])

function labelForKey(key: string) {
  return key.replace(/_/g, " ")
}

function scalarToString(value: unknown): string {
  if (value === null || value === undefined) return ""
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  return ""
}

function normalizeDate(value: unknown): string {
  const text = scalarToString(value)
  if (!text) return ""
  return text.includes("T") ? text.split("T")[0] : text.slice(0, 10)
}

function normalizeTime(dateValue: unknown, timeValue: unknown): string {
  const explicit = scalarToString(timeValue)
  if (explicit) return explicit.slice(0, 5)
  const dateText = scalarToString(dateValue)
  const match = dateText.match(/T(\d{2}:\d{2})/)
  return match?.[1] ?? ""
}

function numberOrNull(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function propertyKind(schema: GraphEditPropertySchema | undefined, value: unknown): EditableProperty["kind"] {
  if (schema?.type === "number" || typeof value === "number") return "number"
  if (schema?.type === "boolean" || typeof value === "boolean") return "boolean"
  return "string"
}

function editableProperties(
  properties: Record<string, unknown>,
  schemaProperties: GraphEditPropertySchema[],
  hiddenKeys: Set<string>
): EditableProperty[] {
  const byKey = new Map(schemaProperties.map((property) => [property.name, property]))
  const keys = new Set<string>()

  for (const property of schemaProperties) keys.add(property.name)
  for (const [key, value] of Object.entries(properties)) {
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      keys.add(key)
    }
  }

  return Array.from(keys)
    .filter((key) => {
      const lower = key.toLowerCase()
      return !hiddenKeys.has(lower) && !basicKeys.has(lower) && !timelineKeys.has(lower) && !locationKeys.has(lower)
    })
    .sort((a, b) => a.localeCompare(b))
    .map((key) => {
      const schema = byKey.get(key)
      const value = properties[key]
      return {
        key,
        label: labelForKey(key),
        kind: propertyKind(schema, value),
        value: scalarToString(value),
        enum: schema?.enum,
      }
    })
}

function LocationPicker({
  coordinates,
  onChange,
  className,
}: {
  coordinates: Coordinates | null
  onChange: (next: Coordinates) => void
  className?: string
}) {
  const { styleUrl } = useMapTheme()
  const center = coordinates ?? { latitude: 20, longitude: 0 }

  return (
    <div className={cn("h-80 overflow-hidden rounded-md border border-border lg:h-[420px]", className)}>
      <MapLibreMap
        key={`${center.latitude}:${center.longitude}`}
        mapLib={maplibregl}
        mapStyle={styleUrl}
        initialViewState={{
          latitude: center.latitude,
          longitude: center.longitude,
          zoom: coordinates ? 13 : 1.4,
        }}
        style={{ width: "100%", height: "100%" }}
        attributionControl={false}
        onClick={(event) =>
          onChange({
            latitude: event.lngLat.lat,
            longitude: event.lngLat.lng,
          })
        }
      >
        {coordinates && (
          <Marker
            latitude={coordinates.latitude}
            longitude={coordinates.longitude}
            draggable
            onDragEnd={(event) =>
              onChange({
                latitude: event.lngLat.lat,
                longitude: event.lngLat.lng,
              })
            }
          >
            <MapPin className="size-7 fill-amber-500 text-amber-700 drop-shadow" />
          </Marker>
        )}
      </MapLibreMap>
    </div>
  )
}

export function EditNodeDialog({ open, onOpenChange, nodeKey, caseId, onSaved }: EditNodeDialogProps) {
  const queryClient = useQueryClient()
  const { data: node, isLoading, error } = useNodeDetails(open ? nodeKey : null, caseId)
  const { data: editSchema, isLoading: schemaLoading } = useGraphEditSchema(open)

  const [name, setName] = useState("")
  const [category, setCategory] = useState("")
  const [specificType, setSpecificType] = useState("")
  const [summary, setSummary] = useState("")
  const [notes, setNotes] = useState("")
  const [date, setDate] = useState("")
  const [time, setTime] = useState("")
  const [datePrecision, setDatePrecision] = useState("")
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null)
  const [locationName, setLocationName] = useState("")
  const [locationSearch, setLocationSearch] = useState("")
  const [propertyValues, setPropertyValues] = useState<Record<string, string>>({})
  const [customProperties, setCustomProperties] = useState<EditableProperty[]>([])
  const [customKey, setCustomKey] = useState("")
  const [customValue, setCustomValue] = useState("")
  const [saving, setSaving] = useState(false)
  const [geocoding, setGeocoding] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const hiddenKeys = useMemo(
    () => new Set((editSchema?.hidden_properties ?? []).map((key) => key.toLowerCase())),
    [editSchema]
  )

  const categoryOptions = useMemo(() => editSchema?.categories ?? [], [editSchema])
  const schemaProperties = useMemo(
    () => editSchema?.category_properties[category] ?? [],
    [category, editSchema]
  )
  const editable = useMemo(
    () => editableProperties(node?.properties ?? {}, schemaProperties, hiddenKeys),
    [hiddenKeys, node?.properties, schemaProperties]
  )
  const renderedProperties = useMemo(() => {
    const existing = new Set(editable.map((property) => property.key))
    return [
      ...editable,
      ...customProperties.filter((property) => !existing.has(property.key)),
    ]
  }, [customProperties, editable])

  useEffect(() => {
    if (!node || !open) return
    const props = node.properties ?? {}
    const schemaCategory = categoryOptions.find((item) => item.name === node.type)?.name
    const fallbackCategory = categoryOptions.find(
      (item) => item.name.toLowerCase() === String(node.type).toLowerCase()
    )?.name

    setName(node.label)
    setCategory(schemaCategory ?? fallbackCategory ?? "")
    setSpecificType(scalarToString(props.specific_type))
    setSummary(String(node.summary ?? ""))
    setNotes(String(node.notes ?? ""))
    setDate(normalizeDate(props.date))
    setTime(normalizeTime(props.date, props.time))
    setDatePrecision(scalarToString(props.date_precision))

    const latitude = numberOrNull(props.latitude)
    const longitude = numberOrNull(props.longitude)
    setCoordinates(latitude !== null && longitude !== null ? { latitude, longitude } : null)
    setLocationName(
      scalarToString(props.location_formatted) ||
        scalarToString(props.location_name) ||
        scalarToString(props.location_raw)
    )
    setLocationSearch("")
    setCustomProperties([])
    setCustomKey("")
    setCustomValue("")
    setSaveError(null)
  }, [categoryOptions, node, open])

  useEffect(() => {
    if (!open) return
    const base = Object.fromEntries(editable.map((property) => [property.key, property.value]))
    setPropertyValues((current) => ({
      ...base,
      ...Object.fromEntries(
        customProperties.map((property) => [
          property.key,
          current[property.key] ?? property.value,
        ])
      ),
    }))
  }, [customProperties, editable, open])

  const handleAddCustomProperty = () => {
    const key = customKey.trim()
    if (!FIELD_KEY_RE.test(key)) {
      setSaveError("Custom field names must start with a letter and use letters, numbers, or underscores.")
      return
    }
    if (hiddenKeys.has(key.toLowerCase()) || timelineKeys.has(key.toLowerCase()) || locationKeys.has(key.toLowerCase())) {
      setSaveError("That field is reserved.")
      return
    }
    setCustomProperties((current) => [
      ...current.filter((property) => property.key !== key),
      { key, label: labelForKey(key), kind: "string", value: customValue },
    ])
    setPropertyValues((current) => ({ ...current, [key]: customValue }))
    setCustomKey("")
    setCustomValue("")
    setSaveError(null)
  }

  const handleGeocode = async () => {
    if (!node || !locationSearch.trim()) return
    setGeocoding(true)
    setSaveError(null)
    try {
      const result = await graphAPI.geocodeNode(node.key, caseId, locationSearch.trim(), false)
      if (!result.success) {
        setSaveError(result.error ?? "Could not geocode address.")
        return
      }
      setCoordinates({ latitude: result.latitude, longitude: result.longitude })
      setLocationName(result.formatted_address || locationSearch.trim())
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not geocode address.")
    } finally {
      setGeocoding(false)
    }
  }

  const handleSave = async () => {
    if (!node) return

    const properties: Record<string, string | number | boolean | null> = {
      date: date || null,
      time: date && time ? time : null,
      date_precision: datePrecision || null,
      latitude: coordinates?.latitude ?? null,
      longitude: coordinates?.longitude ?? null,
      location_raw: locationName || null,
      location_formatted: locationName || null,
      location_name: locationName || null,
    }

    for (const property of renderedProperties) {
      const rawValue = propertyValues[property.key] ?? ""
      if (property.kind === "number") {
        if (rawValue.trim() === "") {
          properties[property.key] = null
          continue
        }
        const parsed = Number(rawValue)
        if (!Number.isFinite(parsed)) {
          setSaveError(`"${property.label}" must be a number.`)
          return
        }
        properties[property.key] = parsed
      } else if (property.kind === "boolean") {
        properties[property.key] = rawValue === "true"
      } else {
        properties[property.key] = rawValue === "" ? null : rawValue
      }
    }

    setSaving(true)
    setSaveError(null)
    try {
      await graphAPI.updateNode(node.key, {
        case_id: caseId,
        name: name.trim(),
        category,
        specific_type: specificType.trim(),
        summary,
        notes,
        properties,
        source_view: "entity_detail",
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["graph", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["graph", "node", node.key, caseId] }),
        queryClient.invalidateQueries({ queryKey: ["graph", "summary", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["graph", "entity-types", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["timeline", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["map", caseId] }),
        queryClient.invalidateQueries({ queryKey: ["financial", caseId] }),
      ])
      onSaved?.()
      onOpenChange(false)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save entity changes.")
    } finally {
      setSaving(false)
    }
  }

  const loading = isLoading || schemaLoading

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] w-[96vw] max-w-[calc(100vw-2rem)] flex-col overflow-hidden gap-0 p-0 sm:max-w-[88rem]">
        <DialogHeader className="shrink-0 border-b border-border px-6 py-4">
          <DialogTitle className="flex items-center gap-2">
            {node ? <NodeBadge type={category || node.type} /> : null}
            Edit Entity
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex min-h-48 items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : !node || !editSchema ? (
          <div className="m-6 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error instanceof Error ? error.message : "Unable to load entity details."}
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
            <div className="space-y-5">
              <section className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px]">
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Name</span>
                    <Input value={name} onChange={(event) => setName(event.target.value)} />
                  </label>
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Category</span>
                    <Select value={category} onValueChange={setCategory}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {categoryOptions.map((option) => (
                          <SelectItem key={option.name} value={option.name}>
                            {option.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </label>
                </div>

                <label className="space-y-1.5 text-xs font-medium">
                  <span>Specific type</span>
                  <Input
                    value={specificType}
                    onChange={(event) => setSpecificType(event.target.value)}
                  />
                </label>

                <label className="space-y-1.5 text-xs font-medium">
                  <span>Summary</span>
                  <Textarea
                    value={summary}
                    onChange={(event) => setSummary(event.target.value)}
                    className="h-72 min-h-40 resize-y [field-sizing:fixed]"
                  />
                </label>

                <label className="space-y-1.5 text-xs font-medium">
                  <span>Notes</span>
                  <Textarea
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    className="h-28 min-h-20 resize-y [field-sizing:fixed]"
                  />
                </label>
              </section>

              <section className="space-y-3 border-t border-border pt-4">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <CalendarClock className="size-3.5" />
                  Timeline
                </div>
                <div className="grid gap-3 sm:grid-cols-[160px_120px_minmax(0,1fr)_auto]">
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Date</span>
                    <Input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
                  </label>
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Time</span>
                    <Input type="time" value={time} onChange={(event) => setTime(event.target.value)} />
                  </label>
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Precision</span>
                    <Select
                      value={datePrecision || NONE_VALUE}
                      onValueChange={(value) => setDatePrecision(value === NONE_VALUE ? "" : value)}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={NONE_VALUE}>None</SelectItem>
                        <SelectItem value="day">Day</SelectItem>
                        <SelectItem value="month">Month</SelectItem>
                        <SelectItem value="year">Year</SelectItem>
                        <SelectItem value="approximate">Approximate</SelectItem>
                      </SelectContent>
                    </Select>
                  </label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="self-end"
                    onClick={() => {
                      setDate("")
                      setTime("")
                      setDatePrecision("")
                    }}
                  >
                    <X className="size-4" />
                  </Button>
                </div>
              </section>

              <section className="space-y-3 border-t border-border pt-4">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <LocateFixed className="size-3.5" />
                  Location
                </div>
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,420px)]">
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Search</span>
                    <div className="flex gap-2">
                      <Input
                        value={locationSearch}
                        onChange={(event) => setLocationSearch(event.target.value)}
                        placeholder="Search address or place"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="icon"
                        onClick={handleGeocode}
                        disabled={!locationSearch.trim() || geocoding}
                      >
                        <Search className={cn("size-4", geocoding && "animate-spin")} />
                      </Button>
                    </div>
                  </label>
                  <label className="space-y-1.5 text-xs font-medium">
                    <span>Location name</span>
                    <Input value={locationName} onChange={(event) => setLocationName(event.target.value)} />
                  </label>
                </div>
                <LocationPicker coordinates={coordinates} onChange={setCoordinates} />
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] text-muted-foreground">
                    {coordinates
                      ? `${coordinates.latitude.toFixed(5)}, ${coordinates.longitude.toFixed(5)}`
                      : "No coordinates"}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setCoordinates(null)
                      setLocationName("")
                    }}
                  >
                    Clear
                  </Button>
                </div>
              </section>

              <details className="group border-t border-border pt-4">
                <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" />
                  Additional Details
                </summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  {renderedProperties.map((property) => (
                    <label key={property.key} className="space-y-1.5 text-xs font-medium capitalize">
                      <span>{property.label}</span>
                      {property.enum && property.enum.length > 0 ? (
                        <Select
                          value={propertyValues[property.key] || NONE_VALUE}
                          onValueChange={(value) =>
                            setPropertyValues((current) => ({
                              ...current,
                              [property.key]: value === NONE_VALUE ? "" : value,
                            }))
                          }
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value={NONE_VALUE}>None</SelectItem>
                            {property.enum.map((item) => (
                              <SelectItem key={item} value={item}>
                                {item}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : property.kind === "boolean" ? (
                        <Select
                          value={propertyValues[property.key] || "false"}
                          onValueChange={(value) =>
                            setPropertyValues((current) => ({ ...current, [property.key]: value }))
                          }
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="true">Yes</SelectItem>
                            <SelectItem value="false">No</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          type={property.kind === "number" ? "number" : "text"}
                          value={propertyValues[property.key] ?? ""}
                          onChange={(event) =>
                            setPropertyValues((current) => ({
                              ...current,
                              [property.key]: event.target.value,
                            }))
                          }
                        />
                      )}
                    </label>
                  ))}
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-[180px_minmax(0,1fr)_auto]">
                  <Input
                    value={customKey}
                    onChange={(event) => setCustomKey(event.target.value)}
                    placeholder="custom_field"
                  />
                  <Input
                    value={customValue}
                    onChange={(event) => setCustomValue(event.target.value)}
                    placeholder="Value"
                  />
                  <Button type="button" variant="outline" onClick={handleAddCustomProperty}>
                    Add
                  </Button>
                </div>
              </details>
            </div>

            {saveError && (
              <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {saveError}
              </div>
            )}
          </div>
        )}

        <DialogFooter className="shrink-0 border-t border-border px-6 py-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            disabled={!node || !name.trim() || !category || saving || loading}
          >
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
