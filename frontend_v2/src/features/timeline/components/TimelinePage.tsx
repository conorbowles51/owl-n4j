import { useEffect, useMemo, useCallback, useRef, useState } from "react"
import { TimelineWindowBar } from "@/features/pattern/components/WindowPanel"
import { toWindowEvent } from "../lib/timeline-utils"
import { useParams, useLocation, useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { FinancialAccessProvider } from "@/features/financial/components/FinancialAccessProvider"
import { LedgerSourceDialog } from "@/features/financial/components/LedgerSourceDialog"
import { CaseworkDetailSheet } from "@/features/workspace/components/CaseworkDetailSheet"
import { useFinancialAccess } from "@/features/financial/hooks/use-financial-access"
import { Clock } from "lucide-react"
import { LoadProgress } from "@/features/financial/components/LoadProgress"
import { EmptyState } from "@/components/ui/empty-state"
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet"
import { useMediaQuery } from "@/hooks/use-media-query"
import { useGraphStore } from "@/stores/graph.store"
import { useUIStore } from "@/stores/ui.store"
import { useTimelineData } from "../hooks/use-timeline-data"
import { useTimelineStore } from "../stores/timeline.store"
import { useFilteredEvents } from "../hooks/use-filtered-events"
import { useKeyboardNavigation } from "../hooks/use-keyboard-navigation"
import { detectClusters } from "../lib/timeline-utils"
import { FilterSidebar } from "./FilterSidebar"
import { EventStream } from "./EventStream"
import { TimelineToolbar } from "./TimelineToolbar"
import { TimelineExportDialog } from "./TimelineExportDialog"
import type { TimelineExportSource } from "../lib/timeline-export"
import { useCaseLayer } from "@/features/significant/stores/case-layer.store"
import { useQuery } from "@tanstack/react-query"
import { getPhones } from "@/features/phones/api"
import { useCase } from "@/features/cases/hooks/use-cases"
import { PhoneLens, PhoneLensToggle } from "../lens/PhoneLens"
import { SCOPE_PARAMS } from "@/features/phones/ui/scope"
import { usePhoneLens } from "../lens/usePhoneLens"
import { PeriodPhones } from "../lens/PeriodPhones"
import { UndatedEvents } from "./UndatedEvents"
import { SignificantEmptyState } from "@/features/significant/components/SignificantEmptyState"

export function TimelinePage() {
  const { id: caseId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [source, setSource] = useState<{
    kind: "transaction" | "workspace_entry" | "money_trail"
    id: string
  } | null>(null)
  const requestedKey = new URLSearchParams(location.search).get("event")
  // Show on Timeline from a phone record (03 section 3.6): the lens opens on that record for this visit
  const phoneRecord = new URLSearchParams(location.search).get("phone_record")
  const returnTo =
    typeof location.state?.financialReturnTo === "string" &&
    location.state.financialReturnTo.startsWith(`/cases/${caseId}/financial`)
      ? location.state.financialReturnTo
      : `/cases/${caseId}/financial?view=transactions`
  const caseLayer = useCaseLayer(caseId)
  const { events, undatedEvents, eventTypes, entities, isLoading, dataKey, error, retry } =
    useTimelineData({ caseId })
  // The phone lens (03 section 9): shown only on a case with phones; off, the page is the existing Timeline (T-5).
  const phonesQ = useQuery({ queryKey: ["phones", caseId], queryFn: () => getPhones(caseId!), enabled: !!caseId })
  const phoneCount = phonesQ.data?.total ?? 0
  const caseName = useCase(caseId ?? "").data?.title ?? "This case"
  // the first-use choice is stored only from a complete load of the whole case, never from a failed read or a layer
  const lens = usePhoneLens(caseId ?? "", events.length > 0, phoneCount > 0, !isLoading && !error && caseLayer !== "significant")
  // a phone scope carried here (07 4.5) opens the lens too: it is what the scope filters
  const carriedScope = SCOPE_PARAMS.some((k) => new URLSearchParams(location.search).has(k))
  const lensOn = lens.on || ((!!phoneRecord || carriedScope) && phoneCount > 0)
  // turning the lens off also leaves the record a Show on Timeline link opened, or the link would keep it on
  const setLens = (v: boolean) => {
    lens.setOn(v)
    if (!v && (phoneRecord || carriedScope)) {
      const q = new URLSearchParams(location.search)
      q.delete("phone_record")
      for (const k of SCOPE_PARAMS) q.delete(k)
      navigate({ pathname: location.pathname, search: q.toString() }, { replace: true })
    }
  }
  const lensToggle = phoneCount > 0 ? <PhoneLensToggle on={lensOn} onChange={setLens} phones={phoneCount} /> : undefined

  const searchInputRef = useRef<HTMLInputElement>(null)
  const [exportOpen, setExportOpen] = useState(false)
  // Below 768 px (the app's narrow breakpoint) the filters open as a sheet over the Timeline instead of a
  // resizable column, which a narrow screen squeezes to about 56 px. Closed until the user asks for it.
  const narrowViewport = useMediaQuery("(max-width: 767px)")
  const [filterSheetOpen, setFilterSheetOpen] = useState(false)
  const [exportSource, setExportSource] = useState<TimelineExportSource | null>(
    null
  )

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
  const filterSidebarOpen = useTimelineStore((s) => s.filterSidebarOpen)
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
  const toggleFilterSidebar = useTimelineStore((s) => s.toggleFilterSidebar)
  const setClusters = useTimelineStore((s) => s.setClusters)
  const prevCluster = useTimelineStore((s) => s.prevCluster)
  const nextCluster = useTimelineStore((s) => s.nextCluster)
  const scrollToEvent = useTimelineStore((s) => s.scrollToEvent)
  const clearScrollTarget = useTimelineStore((s) => s.clearScrollTarget)

  // Select event: highlight in timeline + open entity detail in CaseLayout side panel
  const handleSelectEvent = useCallback(
    (key: string) => {
      timelineSelectEvent(key)
      const financial = events.find((event) => event.key === key)?.source
      if (financial) {
        setSource(financial)
        return
      }
      selectNodes([key])
      expandGraphPanelTo("detail")
    },
    [timelineSelectEvent, selectNodes, expandGraphPanelTo, events]
  )

  const handleMultiSelectEvent = useCallback(
    (key: string) => {
      multiSelectEvent(key)
      if (events.find((event) => event.key === key)?.source) return
      selectNodes([key])
      expandGraphPanelTo("detail")
    },
    [multiSelectEvent, selectNodes, expandGraphPanelTo, events]
  )

  const handleClearSelection = useCallback(() => {
    clearSelection()
  }, [clearSelection])

  // Each layer is a distinct timeline dataset. Reset dataset-dependent filters
  // when its response arrives so stale event types cannot make the other layer
  // look empty or incomplete.
  const initializedDataKeyRef = useRef<string | null>(null)
  useEffect(() => {
    if (!dataKey || initializedDataKeyRef.current === dataKey) return
    selectAllTypes(eventTypes)
    clearEntityFilter()
    clearSelection()
    setClusters(detectClusters(events))
    initializedDataKeyRef.current = dataKey
  }, [
    clearEntityFilter,
    clearSelection,
    dataKey,
    eventTypes,
    events,
    selectAllTypes,
    setClusters,
  ])

  const handoffRef = useRef<string | null>(null)
  useEffect(() => {
    if (
      !requestedKey ||
      !dataKey ||
      isLoading ||
      handoffRef.current === location.key
    )
      return
    if (!events.some((event) => event.key === requestedKey)) return
    clearAllFilters(eventTypes)
    selectAllTypes(eventTypes)
    clearSelection()
    timelineSelectEvent(requestedKey)
    scrollToEvent(requestedKey)
    handoffRef.current = location.key
  }, [
    requestedKey,
    dataKey,
    isLoading,
    location.key,
    events,
    eventTypes,
    clearAllFilters,
    selectAllTypes,
    clearSelection,
    timelineSelectEvent,
    scrollToEvent,
  ])

  // Update clusters when events change
  useEffect(() => {
    if (!dataKey || initializedDataKeyRef.current !== dataKey) return
    setClusters(detectClusters(events))
  }, [dataKey, events, setClusters])

  // Filtering pipeline
  const {
    items,
    filteredEvents,
    filteredCount,
    totalCount,
    entityFilterCounts,
  } = useFilteredEvents({
    events,
    selectedTypes,
    selectedEntityKeys,
    dateRange,
    visibleWindow,
    searchTerm,
    includedEventKeys: null,
  })

  // Count active filters (type + entity only — search & date are in toolbar)
  const activeFilterCount = useMemo(() => {
    let count = 0
    if (selectedTypes.size > 0 && selectedTypes.size < eventTypes.length)
      count++
    if (selectedEntityKeys.size > 0) count++
    return count
  }, [selectedTypes, selectedEntityKeys, eventTypes.length])

  // Handlers
  const handleSelectAllTypes = useCallback(
    () => selectAllTypes(eventTypes),
    [selectAllTypes, eventTypes]
  )

  const handleClearAll = useCallback(() => {
    clearAllFilters(eventTypes)
  }, [clearAllFilters, eventTypes])

  const openExportDialog = useCallback(
    (source: TimelineExportSource | null = null) => {
      setExportSource(source)
      setExportOpen(true)
    },
    []
  )

  const handleFocusEntity = useCallback(
    (key: string) => {
      setSelectedEntities(new Set([key]))
      // On a narrow screen the sheet covers the events; Focus closes it so the focused events are in view.
      setFilterSheetOpen(false)
    },
    [setSelectedEntities]
  )

  const handleToggleFilters = useCallback(() => {
    if (narrowViewport) setFilterSheetOpen((open) => !open)
    else toggleFilterSidebar()
  }, [narrowViewport, toggleFilterSidebar])

  // Keyboard navigation
  useKeyboardNavigation({
    items,
    selectedEventKey,
    onSelectEvent: handleSelectEvent,
    onClearSelection: handleClearSelection,
    onPrevCluster: prevCluster,
    onNextCluster: nextCluster,
    onToggleFilterSidebar: handleToggleFilters,
    searchInputRef,
    scrollToEvent,
  })

  const filterSidebar = (
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
  )

  if (error)
    return (
      <div role="alert" className="p-6 space-y-3">
        <p>
          Timeline could not be loaded completely. Your saved entries are
          retained.
        </p>
        <Button onClick={retry}>Retry Timeline</Button>
        <Button variant="outline" onClick={() => navigate(returnTo)}>
          Back to Financial
        </Button>
      </div>
    )

  if (isLoading) {
    return (
      <div className="flex h-full items-start justify-center pt-6">
        <div className="w-full max-w-2xl">
          <LoadProgress caseId={caseId} page="case/timeline" />
        </div>
      </div>
    )
  }

  // The window around a moment (07 J-5): device lanes and the Case events lane, drawn by the shared Lanes component.
  const windowEvents = events.map(toWindowEvent)
  // XF-4: a period chosen on the Timeline opens what the phones did in it (shown when a from and to date are set)
  const windowBar = caseId ? (
    <>
      <TimelineWindowBar caseId={caseId} events={windowEvents} selectedKey={selectedEventKey ?? requestedKey} />
      {phoneCount > 0 && <PeriodPhones caseId={caseId} caseName={caseName} from={dateRange.start} to={dateRange.end} />}
    </>
  ) : null

  if (events.length === 0) {
    if (caseId && phoneCount > 0 && caseLayer !== "significant") {
      return (
        <div className="flex h-full flex-col">
          {windowBar}
          <div className="flex items-center justify-end gap-2 border-b px-4 py-1.5">{lensToggle}</div>
          {lensOn ? (
            <PhoneLens caseId={caseId} caseName={caseName} note={lens.note} focusRecord={phoneRecord} />
          ) : (
            <EmptyState icon={Clock} title="No timeline events" description="This case's phone entries are hidden. Turn on Phones to show them." />
          )}
          {undatedEvents.length > 0 && <UndatedEvents events={undatedEvents} />}
        </div>
      )
    }
    if (windowBar && caseLayer !== "significant") {
      return (
        <div className="flex h-full flex-col">
          {windowBar}
          <EmptyState icon={Clock} title="No timeline events" description="Process evidence with temporal data to populate the timeline" />
        </div>
      )
    }
    if (caseId && caseLayer === "significant") {
      return (
        <SignificantEmptyState
          caseId={caseId}
          icon={Clock}
          eligibleTitle="No significant entities belong on the timeline"
          eligibleDescription="Your Significant layer has entities, but none currently contain a usable date or time."
        />
      )
    }
    return (
      <EmptyState
        icon={Clock}
        title="No timeline events"
        description="Process evidence with temporal data to populate the timeline"
      />
    )
  }

  const eventStream = (
    <EventStream
      items={items}
      totalCount={totalCount}
      selectedEventKey={selectedEventKey}
      multiSelectedKeys={multiSelectedKeys}
      searchTerm={searchTerm}
      selectedEntityKeys={selectedEntityKeys}
      scrollToEventKey={scrollToEventKey}
      onSelectEvent={handleSelectEvent}
      onMultiSelectEvent={handleMultiSelectEvent}
      onClearScrollTarget={clearScrollTarget}
      onClearFilters={handleClearAll}
    />
  )

  return (
    <div className="flex h-full flex-col bg-background">
      {windowBar}
      {requestedKey && (
        <div
          className="flex flex-wrap items-center gap-3 border-b bg-primary/5 px-4 py-2 text-sm"
          role="status"
        >
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(returnTo)}
          >
            Back to Financial
          </Button>
          <p>
            {events.some((event) => event.key === requestedKey)
              ? "Your added event is selected. Select an event to inspect its original payment, finding or observation."
              : "The requested event is not visible in this Timeline scope."}
          </p>
        </div>
      )}
      {caseId && source && (
        <FinancialAccessProvider caseId={caseId}>
          <TimelineSource
            caseId={caseId}
            source={source}
            onClose={() => {
              setSource(null)
              retry()
            }}
            onOpenEntry={(id) => setSource({ kind: "workspace_entry", id })}
          />
        </FinancialAccessProvider>
      )}
      {/* Toolbar: search + date presets + filter toggle */}
      <TimelineToolbar
        ref={searchInputRef}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        dateRange={dateRange}
        onDateRangeChange={setDateRange}
        filteredCount={filteredCount}
        totalCount={totalCount}
        onToggleFilterSidebar={handleToggleFilters}
        activeFilterCount={activeFilterCount}
        onExport={() => openExportDialog(null)}
        extra={lensToggle}
      />

      {/* 2-panel layout: filter sidebar + event stream */}
      <ResizablePanelGroup orientation="horizontal" className="flex-1">
        {/* Filter sidebar */}
        {!narrowViewport && filterSidebarOpen && (
          <>
            <ResizablePanel
              defaultSize="20"
              minSize="15"
              maxSize="30"
              className="border-r border-border bg-panel"
            >
              {filterSidebar}
            </ResizablePanel>
            <ResizableHandle />
          </>
        )}

        {/* Center: event stream */}
        <ResizablePanel defaultSize="80" minSize="30">
          {lensOn || undatedEvents.length > 0 ? (
            <div className="flex h-full min-h-0 flex-col">
              <div className="min-h-0 flex-1 overflow-hidden">{eventStream}</div>
              {undatedEvents.length > 0 && <UndatedEvents events={undatedEvents} />}
              {lensOn && caseId && (
                <div className="flex min-h-0 flex-1 flex-col border-t">
                  <PhoneLens caseId={caseId} caseName={caseName} note={lens.note} focusRecord={phoneRecord} />
                </div>
              )}
            </div>
          ) : (
            eventStream
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {narrowViewport && (
        <Sheet open={filterSheetOpen} onOpenChange={setFilterSheetOpen}>
          <SheetContent
            side="left"
            className="w-[85vw] max-w-sm gap-0 bg-panel p-0 pt-10"
          >
            <SheetTitle className="sr-only">Timeline filters</SheetTitle>
            <SheetDescription className="sr-only">
              Choose the event types and entities the Timeline shows.
            </SheetDescription>
            <div className="min-h-0 flex-1">{filterSidebar}</div>
          </SheetContent>
        </Sheet>
      )}

      {caseId && (
        <TimelineExportDialog
          open={exportOpen}
          onOpenChange={(open) => {
            setExportOpen(open)
            if (!open) setExportSource(null)
          }}
          caseId={caseId}
          filteredEvents={filteredEvents}
          selectedKeys={multiSelectedKeys}
          preferredSource={exportSource}
        />
      )}
    </div>
  )
}

function TimelineSource({
  caseId,
  source,
  onClose,
  onOpenEntry,
}: {
  caseId: string
  source: {
    kind: "transaction" | "workspace_entry" | "money_trail"
    id: string
  }
  onClose: () => void
  onOpenEntry: (id: string) => void
}) {
  const { canEdit } = useFinancialAccess()
  return source.kind === "money_trail" ? (
    <MoneyTrailReview caseId={caseId} trailId={source.id} initialOpen onClose={onClose} />
  ) : source.kind === "transaction" ? (
    <LedgerSourceDialog
      caseId={caseId}
      transactionId={source.id}
      onClose={onClose}
    />
  ) : (
    <CaseworkDetailSheet
      caseId={caseId}
      entryId={source.id}
      open
      canEdit={canEdit}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      onOpenEntry={onOpenEntry}
    />
  )
}
import { MoneyTrailReview } from "@/features/financial/components/MoneyTrailReview"
