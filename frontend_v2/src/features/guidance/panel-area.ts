import { useEffect, useState } from "react"
import { panelAreas, type TourArea } from "./tours"

/** The panel tour whose panel is on screen, looked for once a second (panels open and close without a new address). */
export function usePanelArea(pathname: string): TourArea | null {
  const [area, setArea] = useState<TourArea | null>(null)
  useEffect(() => {
    const look = () => setArea(panelAreas()[0] ?? null)
    look()
    const t = window.setInterval(look, 1000)
    return () => window.clearInterval(t)
  }, [pathname])
  return area
}
