import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "@/styles/globals.css"
import App from "@/app/App"
import { preloadCurrentRoute } from "@/app/route-table"
import { startBuildVersionGuard } from "@/lib/build-version"
import { applySwitchesAtStart } from "@/lib/ui-switches"

// First, before anything else runs: the page being opened starts downloading its code now, alongside the shell's
// own start-up and the sign-in check, instead of after them (lib/route-preload.ts).
preloadCurrentRoute()

startBuildVersionGuard()

// Before routing: a redirect (e.g. /cases/:id to its workspace) drops the query, so ?phone-prototype=on is read here.
applySwitchesAtStart()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
