import { useState } from "react"
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
import { AgentExchange } from "./components/sections/AgentExchange"
import { Convergence } from "./components/sections/Convergence"
import { GraphReduce } from "./components/sections/GraphReduce"
import { Hero } from "./components/sections/Hero"
import { IntakeStream } from "./components/sections/IntakeStream"
import { Lenses } from "./components/sections/Lenses"
import { ModelResolve } from "./components/sections/ModelResolve"
import { ProblemScene } from "./components/sections/ProblemScene"
import { WorkProduct } from "./components/sections/WorkProduct"

export function App() {
  const [contactOpen, setContactOpen] = useState(false)

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navigation onContact={() => setContactOpen(true)} />

      <main id="main-content">
        {/* ---- Act I — setup */}
        <Hero onContact={() => setContactOpen(true)} />
        <ProblemScene />

        {/* ---- Act II — demonstration, one case from intake to finding */}
        <IntakeStream />
        <ModelResolve />
        <GraphReduce />
        <Lenses />
        <Convergence />
        <AgentExchange />
        <WorkProduct />

        {/* ---- Act III — argument */}
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
