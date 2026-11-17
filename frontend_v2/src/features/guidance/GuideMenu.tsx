import { lazy, Suspense, useState } from "react"
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
import { usePanelArea } from "./panel-area"
import { tourArea, TOURS } from "./tours"
import { useNextSteps } from "./announce"
import { GUIDES, guidesFor, AREA_GUIDE } from "./guides"
import { GLOSSARY_GUIDE } from "@/components/ui/glossary"

// the guide reader (markdown) loads only when a guide is opened
const GuideDialog = lazy(() => import("@/components/ui/guide-dialog").then((m) => ({ default: m.GuideDialog })))

/** "Guide" in the case's bottom bar (lx-guide C, D): the tour of this screen, tips back, guidance on or off. */
export function GuideMenu({ caseId }: { caseId: string }) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const area = tourArea(pathname)
  const panel = usePanelArea(pathname)
  const g = useGuidance(caseId)
  const waiting = useNextSteps((s) => s.cards.filter((c) => c.caseId === caseId).length)
  const [reading, setReading] = useState<"area" | "glossary" | null>(null)
  const guideArea = panel ?? area
  return (
    <>
    {reading && (
      <Suspense fallback={null}>
        <GuideDialog
          guides={reading === "glossary" || !guideArea ? [GLOSSARY_GUIDE] : guidesFor(guideArea)}
          defaultOpen
          noTrigger
          onOpenChange={(o) => !o && setReading(null)}
        />
      </Suspense>
    )}
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
        {panel && (
          <DropdownMenuItem onSelect={() => window.dispatchEvent(new CustomEvent(START_TOUR, { detail: panel }))}>
            Take the tour of {TOURS[panel].name}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => window.dispatchEvent(new CustomEvent(START_TOUR, { detail: "workspace" }))}>
          Start here: the case home tour
        </DropdownMenuItem>
        {guideArea && (
          <DropdownMenuItem onSelect={() => setReading("area")}>Read the {GUIDES[AREA_GUIDE[guideArea]].title}</DropdownMenuItem>
        )}
        <DropdownMenuItem onSelect={() => setReading("glossary")}>Glossary of terms</DropdownMenuItem>
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
    </>
  )
}
