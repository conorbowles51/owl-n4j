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
          <p>An investigation platform for fraud and criminal casework.</p>
        </div>
        <div className="footer-links">
          <div>
            <span>Platform</span>
            <a href="#platform">The case model</a>
            <a href="#workspace">Perspectives</a>
            <a href="#findings">Findings</a>
            <a href="#capability">Capability</a>
          </div>
          <div>
            <span>Detail</span>
            <a href="#economics">What it replaces</a>
            <a href="#audience">Who it’s for</a>
            <a href="#trust">Deployment</a>
          </div>
          <div>
            <span>Contact</span>
            <button type="button" onClick={onContact}>
              Request a walkthrough
            </button>
            <a href="mailto:sales@loupe.ie">sales@loupe.ie</a>
          </div>
        </div>
        <div className="footer-bottom">
          <span>© {new Date().getFullYear()} Loupe</span>
          <span>Dublin, Ireland · An investigation platform for fraud and criminal casework.</span>
        </div>
      </div>
    </footer>
  )
}
