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
          <p>Connected evidence. Cited answers. Defensible findings.</p>
        </div>
        <nav className="footer-links" aria-label="Footer navigation">
          <div>
            <span>Platform</span>
            <a href="#film">Product film</a>
            <a href="#evidence">Evidence</a>
            <a href="#views">Case views</a>
            <a href="#ai">AI workspace</a>
          </div>
          <div>
            <span>Contact</span>
            <button type="button" onClick={onContact}>
              Request a walkthrough
            </button>
            <a href="mailto:sales@loupe.ie">sales@loupe.ie</a>
          </div>
        </nav>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Loupe</span>
          <span>Dublin, Ireland · Investigation software for serious casework.</span>
        </div>
      </div>
    </footer>
  )
}
