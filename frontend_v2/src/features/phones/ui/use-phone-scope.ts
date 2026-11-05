import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useRef, useState } from "react"
import { useLocation, useSearchParams } from "react-router-dom"
import { phonesQuery } from "../phones-query"
import { peopleAPI } from "../people.api"
import { EMPTY_SCOPE, SCOPE_PARAMS, paramsToScopeIds, recallScope, rememberScope, scopeToParams, scopeToSearch } from "./scope"
import type { Scope, ScopePreset } from "./ScopeBar"

/** The label a key reads as when no name is known: the value without its kind ("phone:+1202" reads "+1202"). */
export const keyWords = (key: string) => key.replace(/^[a-z_]+:/, "")

/** "Phones of <dossier>" (owner-linked) and "Phones where <person> appears" (07 4.5), from the case's identity links. */
export function useScopePresets(caseId: string) {
  const people = useQuery({ queryKey: ["phone-scope-presets", caseId], queryFn: () => peopleAPI.scopePresets(caseId), enabled: !!caseId, staleTime: 60_000 })
  const phones = useQuery({ ...phonesQuery(caseId), enabled: !!caseId })
  return useMemo(() => {
    const list = phones.data?.phones ?? []
    const chip = (id: string) => {
      const k = list.findIndex((p) => p.extraction_id === id)
      return { id, label: list[k]?.label ?? "A phone", index: Math.max(0, k) }
    }
    const presets: ScopePreset[] = []
    const names = new Map<string, string>()
    for (const p of people.data?.people ?? []) {
      for (const key of p.identity_keys) names.set(key, p.name)
      if (p.owned_phones.length) presets.push({ label: `Phones of ${p.name}`, scope: { ...EMPTY_SCOPE, phones: p.owned_phones.map(chip) } })
      if (p.appears_on.length) presets.push({ label: `Phones where ${p.name} appears`, scope: { ...EMPTY_SCOPE, phones: p.appears_on.map(chip) } })
    }
    return { presets, names, chip }
  }, [people.data, phones.data])
}

/**
 * The scope's memory on one screen (07 4.5): the scope lives in the URL and the last one is kept per case for the
 * session. A screen opened with nothing in its address takes the last selection back and says so, with Reset; a
 * link that names anything is followed as it stands.
 */
export function useScopeMemory(caseId: string, scope: Scope, apply: (s: Scope) => void, canRestore: boolean) {
  const key = scopeToSearch(scope)
  const tried = useRef(false)
  const [restoredKey, setRestoredKey] = useState<string | null>(null)
  useEffect(() => {
    if (tried.current || !caseId) return
    tried.current = true
    if (!canRestore || key) return
    const { last } = recallScope(caseId)
    if (last && scopeToSearch(last)) {
      setRestoredKey(scopeToSearch(last))
      apply(last)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- on arrival only
  }, [caseId])
  useEffect(() => {
    if (caseId && key) rememberScope(caseId, scope)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the key is the scope
  }, [caseId, key])
  const recent = useMemo(() => recallScope(caseId).recent.filter((s) => scopeToSearch(s) !== key), [caseId, key])
  return { recent, restored: restoredKey !== null && restoredKey === key }
}

/**
 * A screen whose scope is only in its address (Map, Timeline lens, Media): the same chips, presets and memory as
 * Conversations. `applies` names what the screen can filter by; the rest is stated, and stays in the address so it
 * travels on to the next screen.
 */
export function useUrlScope(caseId: string, applies: { people?: boolean; window?: boolean; kinds?: boolean; restore?: boolean } = {}) {
  const location = useLocation()
  const [, setParams] = useSearchParams()
  const { presets, names, chip } = useScopePresets(caseId)
  const ids = useMemo(() => paramsToScopeIds(location.search), [location.search])
  const scope: Scope = {
    ...EMPTY_SCOPE,
    mode: ids.mode,
    people: ids.people.map((k) => ({ key: k, label: names.get(k) ?? keyWords(k) })),
    phones: ids.phones.map(chip),
    window: ids.window,
    kinds: ids.kinds,
  }
  const apply = (s: Scope) =>
    setParams((p) => {
      const next = new URLSearchParams(p)
      for (const k of SCOPE_PARAMS) next.delete(k)
      for (const [k, v] of Object.entries(scopeToParams(s))) next.set(k, v)
      return next
    }, { replace: true })
  const memory = useScopeMemory(caseId, scope, apply, applies.restore !== false && location.search === "")
  const notApplied = [
    ...(scope.people.length && !applies.people ? ["the people chosen"] : []),
    ...(scope.window && !applies.window ? ["the dates"] : []),
    ...(scope.kinds.length && !applies.kinds ? ["the kinds of record"] : []),
  ]
  return { scope, apply, presets, notApplied, ...memory }
}
