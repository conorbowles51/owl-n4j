import { useState } from "react"
import { ContactModal } from "./components/ContactModal"
import { Footer } from "./components/Footer"
import { Navigation } from "./components/Navigation"
import { ProductStory } from "./components/sections/ProductStory"
import { Hero } from "./components/sections/Hero"

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
        <ProductStory onContact={() => setContactOpen(true)} />
      </main>

      <Footer onContact={() => setContactOpen(true)} />
      <ContactModal open={contactOpen} onClose={() => setContactOpen(false)} />
    </div>
  )
}
