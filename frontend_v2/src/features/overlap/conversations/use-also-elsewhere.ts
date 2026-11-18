import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { useSwitch } from "@/lib/ui-switches"
import { overlapAPI } from "../api"

const KEY = "loupe.conversations.also-elsewhere"

/** "Mark what also appears elsewhere" (lx-overlapviews-b B): on or off for this browser, behind corroborate-v2. */
export function useAlsoElsewhere(): [boolean, (on: boolean) => void] {
  const allowed = useSwitch("corroborate-v2")
  const [on, setOn] = useState(() => localStorage.getItem(KEY) === "on")
  return [allowed && on, (v: boolean) => { localStorage.setItem(KEY, v ? "on" : "off"); setOn(v) }]
}

export function useThreadMarks(caseId: string, extraction: string | undefined, threadKey: string | undefined, on: boolean) {
  return useQuery({
    queryKey: ["overlap-thread-marks", caseId, extraction, threadKey],
    queryFn: () => overlapAPI.threadMarks(caseId, extraction!, threadKey!),
    enabled: on && !!extraction && !!threadKey,
    staleTime: 60_000,
  })
}

