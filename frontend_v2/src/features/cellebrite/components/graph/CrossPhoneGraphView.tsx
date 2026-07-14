import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import ForceGraph2D, {
  type ForceGraphMethods,
  type NodeObject,
} from "react-force-graph-2d"
import { Maximize2, Search, ZoomIn, ZoomOut } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { cn } from "@/lib/cn"

import type { GraphLink, GraphNode, PhoneReport, RailSelection } from "../../types"
import { compactNumber, readNumber, readText, reportKey, truncate } from "../shared/cellebrite-format"
import { PhoneReportChip } from "../shared/PhoneReportChip"
import { SmallEmpty } from "../shared/SmallEmpty"
import { reportMaps } from "../events/eventUtils"
import {
  filterGraphByReportKeys,
  filterGraphBySearch,
  graphNodeId,
  isSharedNode,
  linkWeight,
  NODE_COLORS,
  nodeCommCount,
  nodeLabel,
  nodePhone,
  nodePrimaryReportKey,
  nodeReportKeys,
  nodeType,
  reportShortLabel,
  type ForceGraphLink,
  type ForceGraphNode,
} from "./graphUtils"

type GraphDatum = {
  nodes: ForceGraphNode[]
  links: ForceGraphLink[]
}

type GraphNodeObject = NodeObject<ForceGraphNode>
export function CrossPhoneGraphView({
  nodes,
  links,
  reports,
  reportKeys,
  loading,
  search,
  onSearchChange,
  onSelect,
  className,
}: {
  nodes: GraphNode[]
  links: GraphLink[]
  reports: PhoneReport[]
  reportKeys: string[] | null
  loading: boolean
  search: string
  onSearchChange: (value: string) => void
  onSelect: (selection: RailSelection) => void
  className?: string
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const graphRef = useRef<ForceGraphMethods<ForceGraphNode, ForceGraphLink> | undefined>(undefined)
  const [size, setSize] = useState({ width: 900, height: 520 })
  const [hoveredNode, setHoveredNode] = useState<GraphNodeObject | null>(null)
  const { colorByKey } = useMemo(() => reportMaps(reports), [reports])
  const activeReportSet = useMemo(() => new Set(reportKeys ?? []), [reportKeys])

  const graphData = useMemo<GraphDatum>(() => {
    const reportFiltered = filterGraphByReportKeys(nodes, links, reportKeys)
    return filterGraphBySearch(reportFiltered.nodes, reportFiltered.links, search)
  }, [links, nodes, reportKeys, search])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      const { width, height } = entry.contentRect
      setSize({
        width: Math.max(320, Math.floor(width)),
        height: Math.max(240, Math.floor(height)),
      })
    })

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (loading || graphData.nodes.length === 0) return
    const handle = window.setTimeout(() => graphRef.current?.zoomToFit(450, 44), 120)
    return () => window.clearTimeout(handle)
  }, [graphData.nodes.length, loading])

  const paintNode = useCallback(
    (node: GraphNodeObject, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const type = nodeType(node)
      const isReport = type === "PhoneReport"
      const shared = isSharedNode(node)
      const primaryReportKey = nodePrimaryReportKey(node)
      const reportColor = primaryReportKey ? colorByKey.get(primaryReportKey) : undefined
      const fillColor = isReport
        ? reportColor ?? NODE_COLORS.PhoneReport
        : shared
          ? NODE_COLORS.PersonShared
          : NODE_COLORS.Person
      const x = node.x ?? 0
      const y = node.y ?? 0
      const radius = isReport ? 8 : 4 + Math.min(nodeCommCount(node), 10) * 0.3

      if (!isReport && reportColor) {
        ctx.beginPath()
        ctx.arc(x, y, radius + 2, 0, 2 * Math.PI)
        ctx.fillStyle = reportColor
        ctx.fill()
      }

      ctx.beginPath()
      if (isReport) {
        roundedRect(ctx, x - radius, y - radius, radius * 2, radius * 2, 3)
      } else {
        ctx.arc(x, y, radius, 0, 2 * Math.PI)
      }
      ctx.fillStyle = fillColor
      ctx.fill()

      if (shared) {
        ctx.strokeStyle = "#0c9da0"
        ctx.lineWidth = 1.5
        ctx.stroke()
      }

      const fontSize = isReport ? 11 / globalScale : 9 / globalScale
      ctx.font = `${isReport ? "bold " : ""}${fontSize}px sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "top"
      ctx.fillStyle = document.documentElement.classList.contains("dark") ? "#e5e7eb" : "#334155"

      const report = reports.find((item) => reportKey(item) === primaryReportKey)
      const prefix = isReport && report ? `${reportShortLabel(report)} / ` : ""
      ctx.fillText(truncate(`${prefix}${nodeLabel(node)}`, 28), x, y + radius + 2 / globalScale)
    },
    [colorByKey, reports]
  )

  const selectNode = (node: GraphNodeObject) => {
    const type = nodeType(node)
    onSelect({
      id: graphNodeId(node),
      kind: type === "PhoneReport" ? "report" : "contact",
      title: nodeLabel(node),
      payload: node,
    })
  }

  const zoomIn = () => graphRef.current?.zoom(graphRef.current.zoom() * 1.5, 300)
  const zoomOut = () => graphRef.current?.zoom(graphRef.current.zoom() / 1.5, 300)
  const fit = () => graphRef.current?.zoomToFit(400, 44)
  const multipleReports = reports.length > 1

  return (
    <section className={cn("relative flex min-h-0 flex-col border-b border-border bg-background", className)}>
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card px-4 py-2">
        <div className="relative max-w-xs flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search contacts"
            className="h-8 pl-8 text-xs"
          />
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={zoomIn} title="Zoom in">
          <ZoomIn className="size-4" />
        </Button>
        <Button type="button" variant="ghost" size="icon-sm" onClick={zoomOut} title="Zoom out">
          <ZoomOut className="size-4" />
        </Button>
        <Button type="button" variant="ghost" size="icon-sm" onClick={fit} title="Fit to view">
          <Maximize2 className="size-4" />
        </Button>
        <div className="ml-2 whitespace-nowrap text-xs text-muted-foreground">
          {compactNumber(graphData.nodes.length)} nodes, {compactNumber(graphData.links.length)} links
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-border/70 bg-card px-4 py-1.5 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span className="size-3 rounded-full" style={{ backgroundColor: NODE_COLORS.Person }} />
          Contact
        </span>
        <span className="flex items-center gap-1">
          <span
            className="size-3 rounded-full border-2 border-amber-500"
            style={{ backgroundColor: NODE_COLORS.PersonShared }}
          />
          Shared Contact
        </span>
        {multipleReports && (
          <>
            <span className="h-4 w-px bg-border" />
            <span className="font-medium">Phones:</span>
            {reports.map((report) => {
              const key = reportKey(report)
              const disabled = activeReportSet.size > 0 && !activeReportSet.has(key)
              return (
                <span key={key} className={cn(disabled && "opacity-40")}>
                  <PhoneReportChip reportKey={key} report={report} color={colorByKey.get(key)} />
                </span>
              )
            })}
          </>
        )}
      </div>

      <div ref={containerRef} className="min-h-0 flex-1">
        {loading ? (
          <div className="flex h-full items-center justify-center">
            <LoadingSpinner />
          </div>
        ) : graphData.nodes.length === 0 ? (
          <SmallEmpty label={nodes.length === 0 ? "No cross-phone data available" : "No contacts match this view"} />
        ) : (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={size.width}
            height={size.height}
            backgroundColor="transparent"
            nodeCanvasObject={paintNode}
            nodePointerAreaPaint={(node, color, ctx) => {
              const radius = nodeType(node) === "PhoneReport" ? 9 : 7
              ctx.fillStyle = color
              ctx.beginPath()
              ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, 2 * Math.PI)
              ctx.fill()
            }}
            linkColor={() => "#64748b"}
            linkWidth={(link) => (linkWeight(link) ? Math.min(linkWeight(link) / 5, 3) : 0.5)}
            linkDirectionalArrowLength={0}
            onNodeHover={(node) => setHoveredNode(node)}
            onNodeClick={selectNode}
            warmupTicks={50}
            cooldownTicks={100}
            d3AlphaDecay={0.05}
            d3VelocityDecay={0.3}
          />
        )}
      </div>

      {hoveredNode && <GraphHoverCard node={hoveredNode} reports={reports} colorByKey={colorByKey} />}
    </section>
  )
}

function GraphHoverCard({
  node,
  reports,
  colorByKey,
}: {
  node: GraphNodeObject
  reports: PhoneReport[]
  colorByKey: Map<string, string>
}) {
  const type = nodeType(node)
  const reportKeys = nodeReportKeys(node)
  const primaryReportKey = nodePrimaryReportKey(node)
  const report = reports.find((item) => reportKey(item) === primaryReportKey)
  const deviceCount = readNumber(node, ["device_count", "report_count"], 0)
  const commCount = nodeCommCount(node)

  return (
    <div className="pointer-events-none absolute bottom-4 left-4 z-10 max-w-xs rounded-md border border-border bg-card p-3 text-xs shadow-xl">
      <div className="flex flex-wrap items-center gap-1.5 font-semibold text-foreground">
        <span>{nodeLabel(node)}</span>
        {type === "PhoneReport" && report && (
          <PhoneReportChip reportKey={primaryReportKey} report={report} color={colorByKey.get(primaryReportKey)} compact />
        )}
      </div>
      {type === "PhoneReport" && readText(node, ["phone_owner", "owner_name"]) && (
        <div className="mt-1 text-muted-foreground">Owner: {readText(node, ["phone_owner", "owner_name"])}</div>
      )}
      {nodePhone(node) && <div className="mt-1 text-muted-foreground">Phone: {nodePhone(node)}</div>}
      {deviceCount > 1 && (
        <div className="mt-1 font-medium text-amber-600 dark:text-amber-300">
          Appears on {compactNumber(deviceCount)} devices
        </div>
      )}
      {commCount > 0 && (
        <div className="mt-1 text-muted-foreground">{compactNumber(commCount)} communications</div>
      )}
      {type !== "PhoneReport" && reportKeys.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground">On:</span>
          {reportKeys.map((key) => (
            <PhoneReportChip
              key={key}
              reportKey={key}
              report={reports.find((item) => reportKey(item) === key)}
              color={colorByKey.get(key)}
              compact
            />
          ))}
        </div>
      )}
    </div>
  )
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number
) {
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  ctx.lineTo(x + radius, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
}
