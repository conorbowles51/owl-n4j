import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { guidanceAPI, guidanceKey, type GuidanceSettings } from "./api"

/** This person's guidance settings (server-side), with the changes they can make from any popup or Settings. */
export function useGuidance(caseId: string | null | undefined) {
  const qc = useQueryClient()
  const query = useQuery({
    queryKey: guidanceKey(caseId),
    queryFn: () => guidanceAPI.me(caseId),
    staleTime: 5 * 60_000,
  })
  const save = (data: GuidanceSettings) => {
    // every cached copy (other cases, Settings) holds the same person's marks; refresh them all
    qc.setQueryData(guidanceKey(caseId), data)
    void qc.invalidateQueries({ queryKey: ["guidance"], refetchType: "inactive" })
  }
  const change = useMutation({
    mutationFn: (fn: () => Promise<GuidanceSettings>) => fn(),
    onSuccess: save,
  })
  const run = (fn: () => Promise<GuidanceSettings>) => change.mutateAsync(fn)
  const data = query.data
  return {
    settings: data,
    loaded: !!data,
    /** Off, or not yet read: no popup appears until the person's choice is known. */
    on: data?.guidance === "on",
    tipHidden: (kind: string) => !!data?.tips_off.includes(kind),
    saving: change.isPending,
    error: change.error instanceof Error ? change.error.message : null,
    turn: (value: "on" | "off") => run(() => guidanceAPI.set(value, caseId)),
    hideTip: (kind: string) => run(() => guidanceAPI.hideTip(kind, caseId)),
    showAgain: () => run(() => guidanceAPI.showAgain(caseId)),
    tour: (area: string, body: { state?: "done" | "skipped" | "reset"; step?: number }) =>
      run(() => guidanceAPI.tour(area, body, caseId)),
    setHistoryCollapsed: (collapsed: boolean) => run(() => guidanceAPI.history(collapsed, caseId)),
    setCaseDefault: (value: "on" | "off" | null) => (caseId ? run(() => guidanceAPI.caseDefault(caseId, value)) : Promise.reject(new Error("Open a case first."))),
  }
}
