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
          <p>Connected intelligence. Every claim with its receipt.</p>
        </div>
        <div className="footer-links">
          <div>
            <span>Explore</span>
            <a href="#platform">Product</a>
            <a href="#capabilities">Why Loupe</a>
            <a href="#curation">Loupes</a>
            <a href="#agent">Agent</a>
          </div>
          <div>
            <span>Connect</span>
            <button type="button" onClick={onContact}>Request a walkthrough</button>
            <a href="#control">Security &amp; provenance</a>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Loupe</span>
          <span>The evidence layer for complex investigations.</span>
        </div>
      </div>
    </footer>
  )
}
