import { useEffect, useState } from "react"
import { CapabilityMatrix } from "./components/CapabilityMatrix"
import { ContactModal } from "./components/ContactModal"
import { FinalCta } from "./components/FinalCta"
import { FlowSection } from "./components/FlowSection"
import { Footer } from "./components/Footer"
import { Hero } from "./components/Hero"
import { Navigation } from "./components/Navigation"
import { ProductStage } from "./components/ProductStage"
import { TrustSection } from "./components/TrustSection"

export function App() {
  const [contactOpen, setContactOpen] = useState(false)

  useEffect(() => {
    const updateProgress = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight
      const progress = max > 0 ? window.scrollY / max : 0
      document.documentElement.style.setProperty("--page-progress", String(progress))
    }

    updateProgress()
    window.addEventListener("scroll", updateProgress, { passive: true })
    window.addEventListener("resize", updateProgress)
    return () => {
      window.removeEventListener("scroll", updateProgress)
      window.removeEventListener("resize", updateProgress)
    }
  }, [])

  return (
    <div className="site-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className="page-progress" aria-hidden="true" />
      <Navigation onContact={() => setContactOpen(true)} />
      <main id="main-content">
        <Hero onContact={() => setContactOpen(true)} />
        <ProductStage />
        <CapabilityMatrix />
        <FlowSection />
        <TrustSection />
        <FinalCta onContact={() => setContactOpen(true)} />
      </main>
      <Footer onContact={() => setContactOpen(true)} />
      <ContactModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}
