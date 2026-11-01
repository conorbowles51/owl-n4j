import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "@/styles/globals.css"
import App from "@/app/App"
import { startBuildVersionGuard } from "@/lib/build-version"
import { applySwitchesAtStart } from "@/lib/ui-switches"

startBuildVersionGuard()

// Before routing: a redirect (e.g. /cases/:id to its workspace) drops the query, so ?phone-prototype=on is read here.
applySwitchesAtStart()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
