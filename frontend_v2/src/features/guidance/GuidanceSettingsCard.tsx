import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { useGuidance } from "./settings"
import { ACTION_WORDS, type ActionKind } from "./next-steps"
import { TOUR_TIP } from "./TourHost"
import { START_TIP } from "./start-steps"

const TIP_WORDS: Record<string, string> = { [TOUR_TIP]: "Tours that open by themselves", [START_TIP]: "Start here on the case home", ...ACTION_WORDS }

/** Settings → Guidance (lx-guide D): one switch, the tips hidden one by one, and Show again. Saved on the server. */
export function GuidanceSettingsCard() {
  const g = useGuidance(null)
  const s = g.settings
  const tours = Object.entries(s?.tours ?? {}).filter(([, t]) => t.state)
  return (
    <Card id="guidance">
      <CardHeader>
        <CardTitle className="text-sm">Guidance</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="font-medium">Tours and tips</p>
            <p className="text-xs text-muted-foreground">
              Off means no tours and no popups. Next steps after an action still wait behind a quiet link at the bottom left.
              This follows you to any computer.
            </p>
          </div>
          <Switch
            aria-label="Tours and tips"
            checked={g.on}
            disabled={!g.loaded || g.saving}
            onCheckedChange={(v) => void g.turn(v ? "on" : "off")}
          />
        </div>
        {s && s.source !== "user" && s.case_default && (
          <p className="text-xs">A case admin set guidance {s.case_default} for the open case; your own choice here wins over it.</p>
        )}
        {s && (s.tips_off.length > 0 || tours.length > 0) && (
          <div className="space-y-1">
            {s.tips_off.length > 0 && (
              <p className="text-xs">
                Hidden: {s.tips_off.map((k) => TIP_WORDS[k as ActionKind] ?? k).join(", ")}.
              </p>
            )}
            {tours.length > 0 && <p className="text-xs">Tours finished or skipped: {tours.length}.</p>}
            <Button size="sm" variant="outline" disabled={g.saving} onClick={() => void g.showAgain()}>
              Show tips and tours again
            </Button>
          </div>
        )}
        {g.error && <p role="alert" className="text-xs">Not saved: {g.error}</p>}
      </CardContent>
    </Card>
  )
}

/** Case settings: a case admin's default for everyone in the case who has not chosen for themselves. */
export function CaseGuidanceDefault({ caseId }: { caseId: string }) {
  const g = useGuidance(caseId)
  const value = g.settings?.case_default ?? null
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="flex-1">
        Tours and tips for this case: {value === null ? "on unless a person turns them off" : value === "on" ? "on" : "off"} by default.
        People who chose for themselves keep their choice.
      </span>
      {(["on", "off"] as const).map((v) => (
        <Button key={v} size="sm" variant={value === v ? "primary" : "outline"} disabled={g.saving} onClick={() => void g.setCaseDefault(v).catch(() => undefined)}>
          {v === "on" ? "On" : "Off"}
        </Button>
      ))}
      {value !== null && (
        <Button size="sm" variant="ghost" disabled={g.saving} onClick={() => void g.setCaseDefault(null).catch(() => undefined)}>
          No default
        </Button>
      )}
      {g.error && <p role="alert" className="w-full text-xs">Not saved: {g.error}</p>}
    </div>
  )
}
