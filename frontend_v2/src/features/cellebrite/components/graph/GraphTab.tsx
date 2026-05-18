import { useMemo, useState } from "react"

import type { CellebriteRecord, PhoneReport, RailSelection } from "../../types"
import { useCellebriteCommunicationNetwork, useCellebriteCrossPhoneGraph } from "../../hooks/use-cellebrite"
import { isRecord, readText } from "../shared/cellebrite-format"
import { IntersectionPanel } from "../events/IntersectionPanel"
import { CrossPhoneGraphView } from "./CrossPhoneGraphView"
import { SharedContactsTable } from "./SharedContactsTable"

type DateFilters = {
  startDate: string
  endDate: string
}

export function GraphTab({
  active,
  caseId,
  reportKeys,
  reports,
  dateFilters,
  onSelect,
}: {
  active: boolean
  caseId: string
  reportKeys: string[] | null
  reports: PhoneReport[]
  dateFilters: DateFilters
  onSelect: (selection: RailSelection) => void
}) {
  const graphQuery = useCellebriteCrossPhoneGraph(caseId, active)
  const networkQuery = useCellebriteCommunicationNetwork(caseId, active)
  const [search, setSearch] = useState("")
  const [intersectionResults, setIntersectionResults] = useState<Record<string, CellebriteRecord>>({})
  const [intersectionsCollapsed, setIntersectionsCollapsed] = useState(false)

  const nodes = graphQuery.data?.nodes ?? []
  const links = graphQuery.data?.links ?? graphQuery.data?.edges ?? []
  const sharedContacts = useMemo(
    () => graphQuery.data?.shared_contacts ?? networkQuery.data?.shared_contacts ?? [],
    [graphQuery.data?.shared_contacts, networkQuery.data?.shared_contacts]
  )

  const jumpToMatch = (match: CellebriteRecord) => {
    const evidence = Array.isArray(match.evidence) ? match.evidence.find(isRecord) : null
    const payload = evidence ?? match
    onSelect({
      id: readText(payload, ["id", "node_key", "key"], readText(match, ["id"], "intersection")),
      kind: "event",
      title: readText(match, ["summary", "label", "method"], "Intersection match"),
      payload,
    })
  }

  return (
    <section className="flex h-full min-h-0 overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col">
        <CrossPhoneGraphView
          nodes={nodes}
          links={links}
          reports={reports}
          reportKeys={reportKeys}
          loading={graphQuery.isLoading}
          search={search}
          onSearchChange={setSearch}
          onSelect={onSelect}
          className="flex-1"
        />
        <SharedContactsTable
          rows={sharedContacts}
          loading={networkQuery.isLoading}
          search={search}
          onSelect={onSelect}
        />
      </div>
      <IntersectionPanel
        caseId={caseId}
        reportKeys={reportKeys}
        startDate={dateFilters.startDate}
        endDate={dateFilters.endDate}
        results={intersectionResults}
        collapsed={intersectionsCollapsed}
        onResult={(method, result) =>
          setIntersectionResults((current) => ({
            ...current,
            [method]: result,
          }))
        }
        onJumpToMatch={jumpToMatch}
        onCollapsedChange={setIntersectionsCollapsed}
      />
    </section>
  )
}
