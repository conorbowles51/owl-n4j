import { useState } from "react"
import { ContactModal } from "./components/ContactModal"
import { FinalCta } from "./components/FinalCta"
import { Footer } from "./components/Footer"
import { Hero } from "./components/Hero"
import {
  AudienceSection,
  CapabilitySection,
  CaseModelStory,
  DifferenceSection,
  LoupeWorkflowSection,
  ProblemSection,
  ProofSection,
} from "./components/NarrativeSections"
import { Navigation } from "./components/Navigation"
import { ProductExplorer } from "./components/ProductExplorer"

export function App() {
  const [contactOpen, setContactOpen] = useState(false)

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navigation onContact={() => setContactOpen(true)} />
      <main id="main-content">
        <Hero onContact={() => setContactOpen(true)} />
        <ProblemSection />
        <CaseModelStory />
        <ProofSection />
        <ProductExplorer />
        <LoupeWorkflowSection />
        <DifferenceSection />
        <CapabilitySection />
        <AudienceSection />
        <FinalCta onContact={() => setContactOpen(true)} />
      </main>
      <Footer onContact={() => setContactOpen(true)} />
      <ContactModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}
