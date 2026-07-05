import { useEffect, useMemo, useCallback, useRef, useState } from "react"
import { useParams } from "react-router-dom"
import { Clock } from "lucide-react"
import { toast } from "sonner"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { EmptyState } from "@/components/ui/empty-state"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { useTimelineData } from "../hooks/use-timeline-data"
import {
  useTimelineView,
  useTimelineViews,
  useUpdateTimelineViewEvents,
} from "../hooks/use-timeline-views"
import { useTimelineStore } from "../stores/timeline.store"
import { useFilteredEvents } from "../hooks/use-filtered-events"
import { useKeyboardNavigation } from "../hooks/use-keyboard-navigation"
import { detectClusters } from "../lib/timeline-utils"
import { FilterSidebar } from "./FilterSidebar"
import { EventStream } from "./EventStream"
import { TimelineToolbar } from "./TimelineToolbar"
import { TimelineCurationBar } from "./TimelineCurationBar"
import { CreateTimelineViewDialog } from "./CreateTimelineViewDialog"
import { TimelineExportDialog } from "./TimelineExportDialog"
import type { TimelineExportSource } from "../lib/timeline-export"

export function TimelinePage() {
  const { id: caseId } = useParams()
  const { events, eventTypes, entities, isLoading } =
    useTimelineData({ caseId })

  const searchInputRef = useRef<HTMLInputElement>(null)
  const [createViewOpen, setCreateViewOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [exportSource, setExportSource] = useState<TimelineExportSource | null>(null)
  const [createViewEventKeys, setCreateViewEventKeys] = useState<string[]>([])
  const [targetViewId, setTargetViewId] = useState<string | null>(null)

  // Graph store — selecting an event opens the shared entity detail panel
  const selectNodes = useGraphStore((s) => s.selectNodes)
  const expandGraphPanelTo = useUIStore((s) => s.expandGraphPanelTo)

  // Timeline store state
  const selectedTypes = useTimelineStore((s) => s.selectedTypes)
  const selectedEntityKeys = useTimelineStore((s) => s.selectedEntityKeys)
  const dateRange = useTimelineStore((s) => s.dateRange)
  const searchTerm = useTimelineStore((s) => s.searchTerm)
  const selectedEventKey = useTimelineStore((s) => s.selectedEventKey)
  const multiSelectedKeys = useTimelineStore((s) => s.multiSelectedKeys)
  const curationSelectedKeys = useTimelineStore((s) => s.curationSelectedKeys)
  const activeViewId = useTimelineStore((s) => s.activeViewId)
  const filterSidebarOpen = useTimelineStore((s) => s.filterSidebarOpen)
  const curationMode = useTimelineStore((s) => s.curationMode)
  const visibleWindow = useTimelineStore((s) => s.visibleWindow)
  const scrollToEventKey = useTimelineStore((s) => s.scrollToEventKey)

  // Timeline store actions
  const toggleType = useTimelineStore((s) => s.toggleType)
  const selectAllTypes = useTimelineStore((s) => s.selectAllTypes)
  const clearAllTypes = useTimelineStore((s) => s.clearAllTypes)
  const toggleEntity = useTimelineStore((s) => s.toggleEntity)
  const setSelectedEntities = useTimelineStore((s) => s.setSelectedEntities)
  const clearEntityFilter = useTimelineStore((s) => s.clearEntityFilter)
  const setDateRange = useTimelineStore((s) => s.setDateRange)
  const setSearchTerm = useTimelineStore((s) => s.setSearchTerm)
  const clearAllFilters = useTimelineStore((s) => s.clearAllFilters)
  const timelineSelectEvent = useTimelineStore((s) => s.selectEvent)
  const multiSelectEvent = useTimelineStore((s) => s.multiSelectEvent)
  const clearSelection = useTimelineStore((s) => s.clearSelection)
  const setActiveViewId = useTimelineStore((s) => s.setActiveViewId)
  const toggleCurationSelection = useTimelineStore((s) => s.toggleCurationSelection)
  const clearCurationSelection = useTimelineStore((s) => s.clearCurationSelection)
  const toggleFilterSidebar = useTimelineStore((s) => s.toggleFilterSidebar)
  const toggleCurationMode = useTimelineStore((s) => s.toggleCurationMode)
  const setClusters = useTimelineStore((s) => s.setClusters)
  const prevCluster = useTimelineStore((s) => s.prevCluster)
  const nextCluster = useTimelineStore((s) => s.nextCluster)
  const scrollToEvent = useTimelineStore((s) => s.scrollToEvent)
  const clearScrollTarget = useTimelineStore((s) => s.clearScrollTarget)

  const viewsQuery = useTimelineViews(caseId)
  const views = useMemo(() => viewsQuery.data?.views ?? [], [viewsQuery.data?.views])
  const activeViewQuery = useTimelineView(caseId, activeViewId)
  const activeView = activeViewQuery.data ?? null
  const updateViewEvents = useUpdateTimelineViewEvents(caseId)
  const resolvedTargetViewId = useMemo(
    () =>
      targetViewId && views.some((view) => view.id === targetViewId)
        ? targetViewId
        : views[0]?.id ?? null,
    [targetViewId, views]
  )

  // Select event: highlight in timeline + open entity detail in CaseLayout side panel
  const handleSelectEvent = useCallback(
    (key: string) => {
      timelineSelectEvent(key)
      selectNodes([key])
      expandGraphPanelTo("detail")
    },
    [timelineSelectEvent, selectNodes, expandGraphPanelTo]
  )

  const handleMultiSelectEvent = useCallback(
    (key: string) => {
      multiSelectEvent(key)
      selectNodes([key])
      expandGraphPanelTo("detail")
    },
    [multiSelectEvent, selectNodes, expandGraphPanelTo]
  )

  const handleClearSelection = useCallback(() => {
    clearSelection()
  }, [clearSelection])

  // Initialize store on first data load
  const initializedRef = useRef(false)
  useEffect(() => {
    if (initializedRef.current || eventTypes.length === 0) return
    selectAllTypes(eventTypes)
    setClusters(detectClusters(events))
    initializedRef.current = true
  }, [eventTypes, events, selectAllTypes, setClusters])

  // Update clusters when events change
  useEffect(() => {
    if (!initializedRef.current || events.length === 0) return
    setClusters(detectClusters(events))
  }, [events, setClusters])

  // Filtering pipeline
  const activeViewKeys = useMemo(() => {
    if (!activeViewId) return null
    return new Set(activeView?.events.map((event) => event.event_key) ?? [])
  }, [activeView?.events, activeViewId])

  const { items, filteredEvents, filteredCount, totalCount, entityFilterCounts } =
    useFilteredEvents({
      events,
      selectedTypes,
      selectedEntityKeys,
      dateRange,
      visibleWindow,
      searchTerm,
      includedEventKeys: activeViewId ? activeViewKeys : null,
    })

  // Count active filters (type + entity only — search & date are in toolbar)
  const activeFilterCount = useMemo(() => {
    let count = 0
    if (selectedTypes.size > 0 && selectedTypes.size < eventTypes.length) count++
    if (selectedEntityKeys.size > 0) count++
    return count
  }, [selectedTypes, selectedEntityKeys, eventTypes.length])

  // Handlers
  const handleSelectAllTypes = useCallback(
    () => selectAllTypes(eventTypes),
    [selectAllTypes, eventTypes]
  )

  const handleClearAll = useCallback(
    () => {
      clearAllFilters(eventTypes)
    },
    [clearAllFilters, eventTypes]
  )

  const filterSnapshot = useMemo(
    () => ({
      selected_types: Array.from(selectedTypes),
      selected_entity_keys: Array.from(selectedEntityKeys),
      date_range: dateRange,
      search_term: searchTerm,
      source_view_id: activeViewId,
    }),
    [activeViewId, dateRange, searchTerm, selectedEntityKeys, selectedTypes]
  )

  const handleCreateViewFromFiltered = useCallback(() => {
    setCreateViewEventKeys(filteredEvents.map((event) => event.key))
    setCreateViewOpen(true)
  }, [filteredEvents])

  const handleCreateViewFromSelection = useCallback(() => {
    setCreateViewEventKeys(Array.from(curationSelectedKeys))
    setCreateViewOpen(true)
  }, [curationSelectedKeys])

  const handleAddSelectionToView = useCallback(() => {
    if (!resolvedTargetViewId || curationSelectedKeys.size === 0) return
    updateViewEvents.mutate(
      {
        viewId: resolvedTargetViewId,
        action: "add",
        eventKeys: Array.from(curationSelectedKeys),
      },
      {
        onSuccess: () => {
          toast.success("Events added to timeline view")
          clearCurationSelection()
        },
        onError: (error) => {
          toast.error(error instanceof Error ? error.message : "Failed to update timeline view")
        },
      }
    )
  }, [clearCurationSelection, curationSelectedKeys, resolvedTargetViewId, updateViewEvents])

  const handleRemoveSelectionFromView = useCallback(() => {
    if (!activeView || curationSelectedKeys.size === 0) return
    updateViewEvents.mutate(
      {
        viewId: activeView.id,
        action: "remove",
        eventKeys: Array.from(curationSelectedKeys),
      },
      {
        onSuccess: () => {
          toast.success("Events removed from timeline view")
          clearCurationSelection()
        },
        onError: (error) => {
          toast.error(error instanceof Error ? error.message : "Failed to update timeline view")
        },
      }
    )
  }, [activeView, clearCurationSelection, curationSelectedKeys, updateViewEvents])

  const openExportDialog = useCallback((source: TimelineExportSource | null = null) => {
    setExportSource(source)
    setExportOpen(true)
  }, [])

  const handleFocusEntity = useCallback(
    (key: string) => setSelectedEntities(new Set([key])),
    [setSelectedEntities]
  )

  // Keyboard navigation
  useKeyboardNavigation({
    items,
    selectedEventKey,
    onSelectEvent: handleSelectEvent,
    onClearSelection: handleClearSelection,
    onPrevCluster: prevCluster,
    onNextCluster: nextCluster,
    onToggleFilterSidebar: toggleFilterSidebar,
    searchInputRef,
    scrollToEvent,
  })

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <EmptyState
        icon={Clock}
        title="No timeline events"
        description="Process evidence with temporal data to populate the timeline"
      />
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar: search + date presets + filter toggle */}
      <TimelineToolbar
        ref={searchInputRef}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        dateRange={dateRange}
        onDateRangeChange={setDateRange}
        filteredCount={filteredCount}
        totalCount={totalCount}
        onToggleFilterSidebar={toggleFilterSidebar}
        activeFilterCount={activeFilterCount}
        views={views}
        activeViewId={activeViewId}
        onActiveViewChange={setActiveViewId}
        curationMode={curationMode}
        curationSelectedCount={curationSelectedKeys.size}
        onToggleCurationMode={toggleCurationMode}
        onCreateView={handleCreateViewFromFiltered}
        onExport={() => openExportDialog(null)}
      />

      {curationMode && (
        <TimelineCurationBar
          selectedCount={curationSelectedKeys.size}
          views={views}
          activeView={activeView}
          targetViewId={resolvedTargetViewId}
          onTargetViewChange={setTargetViewId}
          onCreateFromSelection={handleCreateViewFromSelection}
          onAddToView={handleAddSelectionToView}
          onRemoveFromView={handleRemoveSelectionFromView}
          onExportSelected={() => openExportDialog("selection")}
          onClear={clearCurationSelection}
        />
      )}

      {/* 2-panel layout: filter sidebar + event stream */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        {/* Filter sidebar */}
        {filterSidebarOpen && (
          <>
            <ResizablePanel
              defaultSize="20"
              minSize="15"
              maxSize="30"
              className="border-r border-border"
            >
              <FilterSidebar
                eventTypes={eventTypes}
                selectedTypes={selectedTypes}
                onToggleType={toggleType}
                onSelectAllTypes={handleSelectAllTypes}
                onClearAllTypes={clearAllTypes}
                entities={entities}
                selectedEntityKeys={selectedEntityKeys}
                entityFilterCounts={entityFilterCounts}
                onToggleEntity={toggleEntity}
                onClearEntityFilter={clearEntityFilter}
                onFocusEntity={handleFocusEntity}
                activeFilterCount={activeFilterCount}
                onClearAll={handleClearAll}
              />
            </ResizablePanel>
            <ResizableHandle />
          </>
        )}

        {/* Center: event stream */}
        <ResizablePanel defaultSize="80" minSize="30">
          <EventStream
            items={items}
            totalCount={totalCount}
            selectedEventKey={selectedEventKey}
            multiSelectedKeys={multiSelectedKeys}
            curationMode={curationMode}
            curationSelectedKeys={curationSelectedKeys}
            searchTerm={searchTerm}
            selectedEntityKeys={selectedEntityKeys}
            scrollToEventKey={scrollToEventKey}
            onSelectEvent={handleSelectEvent}
            onMultiSelectEvent={handleMultiSelectEvent}
            onToggleCurationSelection={toggleCurationSelection}
            onClearScrollTarget={clearScrollTarget}
            onClearFilters={handleClearAll}
          />
        </ResizablePanel>
      </ResizablePanelGroup>

      {caseId && (
        <>
          <CreateTimelineViewDialog
            open={createViewOpen}
            onOpenChange={setCreateViewOpen}
            caseId={caseId}
            eventKeys={createViewEventKeys}
            filterSnapshot={filterSnapshot}
            onCreated={(view) => {
              setActiveViewId(view.id)
              setTargetViewId(view.id)
              clearCurationSelection()
            }}
          />
          <TimelineExportDialog
            open={exportOpen}
            onOpenChange={(open) => {
              setExportOpen(open)
              if (!open) setExportSource(null)
            }}
            caseId={caseId}
            activeView={activeView}
            filteredEvents={filteredEvents}
            selectedKeys={curationSelectedKeys}
            preferredSource={exportSource}
          />
        </>
      )}
    </div>
  )
}
