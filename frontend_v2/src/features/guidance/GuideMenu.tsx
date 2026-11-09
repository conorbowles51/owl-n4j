import { useLocation, useNavigate } from "react-router-dom"
import { CircleHelp } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useGuidance } from "./settings"
import { START_TOUR } from "./TourHost"
import { tourArea, TOURS } from "./tours"
import { useNextSteps } from "./announce"

/** "Guide" in the case's bottom bar (lx-guide C, D): the tour of this screen, tips back, guidance on or off. */
export function GuideMenu({ caseId }: { caseId: string }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const area = tourArea(pathname)
  const g = useGuidance(caseId)
  const waiting = useNextSteps((s) => s.cards.filter((c) => c.caseId === caseId).length)
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        data-guide="guide-menu"
        className="flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[11px] hover:bg-muted"
      >
        <CircleHelp className="size-3.5" aria-hidden="true" />
        Guide
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="top" className="w-64">
        <DropdownMenuLabel className="text-xs">
          Guidance is {g.on ? "on" : "off"}
          {g.settings?.source === "case" ? " (the case's default)" : ""}
        </DropdownMenuLabel>
        {area && (
          <DropdownMenuItem onSelect={() => window.dispatchEvent(new CustomEvent(START_TOUR, { detail: area }))}>
            Take the tour of {TOURS[area].name}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => window.dispatchEvent(new CustomEvent(START_TOUR, { detail: "workspace" }))}>
          Start here: the case home tour
        </DropdownMenuItem>
        {waiting > 0 && <DropdownMenuLabel className="text-xs font-normal">{waiting} next {waiting === 1 ? "step card is" : "step cards are"} waiting at the bottom left.</DropdownMenuLabel>}
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={g.saving} onSelect={() => void g.showAgain()}>
          Show tips and tours again
        </DropdownMenuItem>
        <DropdownMenuItem disabled={g.saving || !g.loaded} onSelect={() => void g.turn(g.on ? "off" : "on")}>
          {g.on ? "Turn guidance off" : "Turn guidance on"}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => navigate("/settings#guidance")}>Guidance settings</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
