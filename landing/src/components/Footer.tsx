import { BrandLogo } from "./BrandLogo"

interface FooterProps {
  onContact: () => void
}

export function Footer({ onContact }: FooterProps) {
  return (
    <footer className="footer">
      <div className="container footer-inner">
        <div className="footer-brand">
          <BrandLogo />
          <p>Find the signal in everything. Keep the proof with the case.</p>
        </div>
        <div className="footer-links">
          <div>
            <span>Explore</span>
            <a href="#platform">Platform</a>
            <a href="#workflow">How it works</a>
            <a href="#why-loupe">Why Loupe</a>
            <a href="#proof">Trust</a>
          </div>
          <div>
            <span>Contact</span>
            <button type="button" onClick={onContact}>Request a walkthrough</button>
            <a href="mailto:sales@loupe.ie">sales@loupe.ie</a>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Loupe</span>
          <span>Dublin, Ireland · Built for complex investigations.</span>
        </div>
      </div>
    </footer>
  )
}
