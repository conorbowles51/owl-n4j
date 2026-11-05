import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "@/styles/globals.css"
import App from "@/app/App"
import { appRouteTree } from "@/app/route-table"
import { startBuildVersionGuard } from "@/lib/build-version"
import { registerRouteTree } from "@/lib/route-preload"
import { applySwitchesAtStart } from "@/lib/ui-switches"

// Before routing: a redirect (e.g. /cases/:id to its workspace) drops the query, so ?phone-prototype=on is read here.
applySwitchesAtStart()

// Links start a page's code when pointed at (lib/route-preload.ts).
registerRouteTree(appRouteTree)

startBuildVersionGuard()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
