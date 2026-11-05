import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { fetchAPI } from "@/lib/api-client"
import type { ReplacedState } from "./replaced-links"

/** 07 section 6.3: a link's state, worked out on the server when the link is shown. Counts are true totals; a list
 * clipped to the first items says so through ``clipped``. */
export interface LinkStateItem {
  record_uid: string
  field: string
  was: string | null
  now: string | null
  by: string | null
  at: string
  words: string
}

export interface LinkStateList {
  count: number
  records: number
  items: LinkStateItem[]
  clipped: boolean
}

export interface LinkState {
  link_id: string
  link_kind: "entry" | "dossier" | "assessment" | "interview"
  target_type: string
  target_id: string
  states: ("corrected" | "reading_changed" | "set_aside")[]
  records: number
  corrected: LinkStateList
  reading_changed: LinkStateList
  set_aside: { shown_record_uid: string; words: string } | null
  reread: { at: string | null; words: string } | null
  replaced?: ReplacedState | null
  added_by: string | null
  through_seq: number
  needs_choice: boolean
  can_choose: boolean
  can_remove: boolean
  kept: { by: string; at: string; words: string } | null
}

export type LinkContainer = "entry" | "dossier"

export const linkStatesKey = (caseId: string, container: LinkContainer, id: string | undefined) =>
  ["phone-link-states", caseId, container, id] as const

/** Every phone link of one finding or dossier, one request whatever their number. */
export function useLinkStates(caseId: string, container: LinkContainer, id: string | undefined, enabled: boolean) {
  const q = useQuery({
    queryKey: linkStatesKey(caseId, container, id),
    queryFn: () => fetchAPI<{ links: Record<string, LinkState> }>("/api/phones/links/states",
      { method: "POST", body: { case_id: caseId, container, container_id: id } }),
    enabled: !!caseId && !!id && enabled,
  })
  return q.data?.links ?? {}
}

export function useLinkChoice(caseId: string, container: LinkContainer, id: string | undefined, onDone?: () => void) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { state: LinkState; choice: "keep" | "remove"; expectedVersion?: number }) =>
      fetchAPI<{ choice: string; removed: boolean }>(`/api/phones/links/${encodeURIComponent(v.state.link_id)}/choice`, {
        method: "POST",
        body: { case_id: caseId, link_kind: v.state.link_kind, choice: v.choice, through_seq: v.state.through_seq,
                expected_version: v.expectedVersion ?? null },
      }),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: linkStatesKey(caseId, container, id) })
      onDone?.()
    },
  })
}
