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
          <p>Connected intelligence for complex work.</p>
        </div>
        <div className="footer-links">
          <div><span>Explore</span><a href="#platform">Platform</a><a href="#capabilities">Capabilities</a><a href="#approach">Approach</a></div>
          <div><span>Connect</span><button type="button" onClick={onContact}>Request a walkthrough</button><a href="#control">Control &amp; provenance</a></div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Loupe</span>
          <span>Designed to reveal what matters.</span>
        </div>
      </div>
    </footer>
  )
}
