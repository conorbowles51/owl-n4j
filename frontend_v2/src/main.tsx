import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "@/styles/globals.css"
import App from "@/app/App"
import { preloadCurrentRoute } from "@/app/route-table"
import { startSignInCheck } from "@/features/auth/sign-in-check"
import { startBuildVersionGuard } from "@/lib/build-version"
import { applySwitchesAtStart } from "@/lib/ui-switches"

// First, before anything else runs: the sign-in check is sent, and the page being opened starts its first data and
// its code as soon as it answers, instead of after the shell has rendered and the page's code has mounted
// (features/auth/sign-in-check.ts, app/route-table.ts).
preloadCurrentRoute(window.location.pathname, window.location.search, startSignInCheck())

startBuildVersionGuard()

// Before routing: a redirect (e.g. /cases/:id to its workspace) drops the query, so ?phone-prototype=on is read here.
applySwitchesAtStart()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
