import { lazy, Suspense, useState } from "react"
import { ContactModal } from "./components/ContactModal"
import { FinalCta } from "./components/FinalCta"
import { Footer } from "./components/Footer"
import { Navigation } from "./components/Navigation"
import {
  AudienceSection,
  CapabilitySection,
  DifferenceSection,
  ProofSection,
} from "./components/NarrativeSections"
import { Hero } from "./components/sections/Hero"
import { Ingest } from "./components/sections/Ingest"
import { TheCase } from "./components/sections/TheCase"

// Below-fold sections with heavy compositions load on demand; the reader is
// several screens away when these chunks resolve.
const GraphReduce = lazy(() =>
  import("./components/sections/GraphReduce").then((m) => ({ default: m.GraphReduce }))
)
const AgentDialogue = lazy(() =>
  import("./components/sections/AgentDialogue").then((m) => ({ default: m.AgentDialogue }))
)
const Finding = lazy(() =>
  import("./components/sections/Finding").then((m) => ({ default: m.Finding }))
)
const Sourced = lazy(() =>
  import("./components/sections/Sourced").then((m) => ({ default: m.Sourced }))
)
const Surfaces = lazy(() =>
  import("./components/sections/Surfaces").then((m) => ({ default: m.Surfaces }))
)

export function App() {
  const [contactOpen, setContactOpen] = useState(false)

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navigation onContact={() => setContactOpen(true)} />

      <main id="main-content">
        {/* ---- Act I — what this is */}
        <Hero onContact={() => setContactOpen(true)} />

        {/* ---- Act II — one case, from files to finding.
            Spec: docs/superpowers/specs/2026-08-05-landing-rebuild-2.md §3 */}
        <TheCase />
        <Ingest />
        <Suspense fallback={null}>
          <GraphReduce />
          <AgentDialogue />
          <Finding />
          <Sourced />
          <Surfaces />
        </Suspense>

        {/* ---- Act III — the argument */}
        <DifferenceSection />
        <CapabilitySection />
        <ProofSection />
        <AudienceSection />
        <FinalCta onContact={() => setContactOpen(true)} />
      </main>

      <Footer onContact={() => setContactOpen(true)} />
      <ContactModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}
