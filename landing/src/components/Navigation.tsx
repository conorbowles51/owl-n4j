import { useEffect, useState, type CSSProperties } from "react"
import { BrandLogo } from "./BrandLogo"

interface NavigationProps {
  onContact: () => void
}

const links = [
  { href: "#platform", label: "Platform" },
  { href: "#capabilities", label: "Capabilities" },
  { href: "#approach", label: "Approach" },
  { href: "#control", label: "Control" },
]

export function Navigation({ onContact }: NavigationProps) {
  const [scrolled, setScrolled] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 28)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false)
    }
    onScroll()
    window.addEventListener("scroll", onScroll, { passive: true })
    document.addEventListener("keydown", onKeyDown)
    return () => {
      window.removeEventListener("scroll", onScroll)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [])

  useEffect(() => {
    document.body.classList.toggle("menu-open", menuOpen)
    return () => document.body.classList.remove("menu-open")
  }, [menuOpen])

  return (
    <header
      className={`navigation ${scrolled ? "navigation-scrolled" : ""} ${menuOpen ? "navigation-menu-open" : ""}`}
    >
      <nav className="nav-inner container" aria-label="Primary navigation">
        <a href="#top" className="nav-brand" aria-label="Loupe home">
          <BrandLogo />
        </a>
        <div className="nav-links">
          {links.map((link) => (
            <a href={link.href} key={link.href}>
              {link.label}
            </a>
          ))}
        </div>
        <div className="nav-actions">
          <button className="button button-quiet nav-contact" type="button" onClick={onContact}>
            Request a walkthrough
            <span aria-hidden="true">↗</span>
          </button>
          <button
            className={`menu-toggle ${menuOpen ? "is-open" : ""}`}
            type="button"
            aria-label="Toggle navigation"
            aria-expanded={menuOpen}
            aria-controls="mobile-navigation"
            onClick={() => setMenuOpen((value) => !value)}
          >
            <span />
            <span />
          </button>
        </div>
      </nav>
      <div id="mobile-navigation" className={`mobile-navigation ${menuOpen ? "is-open" : ""}`}>
        {links.map((link, index) => (
          <a
            href={link.href}
            key={link.href}
            style={{ "--menu-index": index } as CSSProperties}
            onClick={() => setMenuOpen(false)}
          >
            <span>0{index + 1}</span>
            {link.label}
          </a>
        ))}
        <button
          className="button button-primary"
          type="button"
          onClick={() => {
            setMenuOpen(false)
            onContact()
          }}
        >
          Request a walkthrough
        </button>
      </div>
    </header>
  )
}
