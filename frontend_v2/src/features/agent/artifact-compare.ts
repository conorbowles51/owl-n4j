import { artifactRows, artifactText } from "./artifact-data"
import type { AgentArtifact } from "./types"

type Row = Record<string, unknown>
export interface ComparedSection { key: string; heading: string; content: string; position: string; embeds: Row[] }
interface Dataset { key: string; label: string; rows: Row[]; columns: { key: string; label: string }[] }

function sectionsIn(value: unknown, parent: number[] = []): ComparedSection[] {
  return artifactRows(value).flatMap((section, index) => {
    const path = [...parent, index + 1]
    return [{ key: section.id ? `id:${artifactText(section.id)}` : `position:${path.join(".")}`, heading: artifactText(section.heading) || `Section ${path.join(".")}`, content: artifactText(section.content), position: path.join("."), embeds: artifactRows(section.embeds) },
      ...sectionsIn(artifactRows(section.sections).length ? section.sections : section.children, path)]
  })
}

function datasetsIn(artifact: AgentArtifact): Dataset[] {
  const datasets: Dataset[] = []
  const add = (key: string, label: string, data: Row) => {
    const raw = data.rows ?? data.events ?? data.locations
    if (!Array.isArray(raw)) return
    const rows = artifactRows(raw)
    const columns = (Array.isArray(data.columns) ? data.columns : []).map((column) => typeof column === "string" ? { key: column, label: column } : { key: artifactText(column?.key), label: artifactText(column?.label || column?.key) }).filter((column) => column.key)
    const keys = new Set(columns.map((column) => column.key))
    for (const row of rows) for (const name of Object.keys(row)) if (!keys.has(name)) { keys.add(name); columns.push({ key: name, label: name.replaceAll("_", " ") }) }
    datasets.push({ key, label, rows, columns })
  }
  add("main", "Dataset", artifact.data)
  artifactRows(artifact.data.sheets).forEach((sheet, index) => add(`sheet:${artifactText(sheet.id || sheet.name || index)}`, artifactText(sheet.name) || `Sheet ${index + 1}`, sheet))
  for (const section of sectionsIn(artifact.data.sections)) section.embeds.forEach((embed, index) => {
    if (embed.data && typeof embed.data === "object") add(`${section.key}/exhibit:${artifactText(embed.id || index)}`, artifactText(embed.title) || `${section.heading} exhibit ${index + 1}`, embed.data as Row)
  })
  if (Array.isArray(artifact.data.nodes)) add("nodes", "Nodes", { rows: artifact.data.nodes })
  if (Array.isArray(artifact.data.links)) add("links", "Relationships", { rows: artifact.data.links })
  return datasets
}

export function compareArtifacts(previous: AgentArtifact, current: AgentArtifact) {
  const beforeSections = new Map(sectionsIn(previous.data.sections).map((section) => [section.key, section]))
  const afterSections = new Map(sectionsIn(current.data.sections).map((section) => [section.key, section]))
  const sectionChanges = [...new Set([...afterSections.keys(), ...beforeSections.keys()])].flatMap((key) => {
    const before = beforeSections.get(key)
    const after = afterSections.get(key)
    const exhibitsChanged = JSON.stringify(before?.embeds ?? []) !== JSON.stringify(after?.embeds ?? [])
    if (before && after && before.heading === after.heading && before.content === after.content && before.position === after.position && !exhibitsChanged) return []
    return [{ key, kind: !before ? "Added" : !after ? "Removed" : "Changed", before, after, exhibitsChanged }]
  })
  const beforeData = new Map(datasetsIn(previous).map((dataset) => [dataset.key, dataset]))
  const afterData = new Map(datasetsIn(current).map((dataset) => [dataset.key, dataset]))
  const datasetChanges = [...new Set([...afterData.keys(), ...beforeData.keys()])].flatMap((key) => {
    const before = beforeData.get(key)
    const after = afterData.get(key)
    const rowsChanged = JSON.stringify(before?.rows ?? []) !== JSON.stringify(after?.rows ?? [])
    const columnsChanged = JSON.stringify(before?.columns ?? []) !== JSON.stringify(after?.columns ?? [])
    if (before && after && !rowsChanged && !columnsChanged) return []
    return [{ key, label: after?.label || before?.label || "Dataset", before, after, rowsChanged, columnsChanged }]
  })
  const details = ["purpose", "scope", "audience", "static_content"].flatMap((key) => {
    const before = artifactText(previous.data[key]); const after = artifactText(current.data[key])
    return before === after ? [] : [{ label: key === "static_content" ? "Readable alternative" : key[0].toUpperCase() + key.slice(1), before, after }]
  })
  const otherChanges = [
    ["sources", "Source list changed"], ["open_questions", "Open questions changed"], ["slides", "Slides or speaker notes changed"],
    ["html", "Saved layout changed"], ["interactions", "Interactive controls or calculations changed"],
  ].filter(([key]) => JSON.stringify(previous.data[key]) !== JSON.stringify(current.data[key])).map(([, label]) => label)
  return { titleChanged: previous.title !== current.title, sectionChanges, datasetChanges, details, otherChanges, contentChanged: previous.title !== current.title || JSON.stringify(previous.data) !== JSON.stringify(current.data) }
}
