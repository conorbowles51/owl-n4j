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
            <span>The argument</span>
            <a href="#origin">Why Loupe exists</a>
            <a href="#field">The field</a>
            <a href="#economics">What it replaces</a>
            <a href="#audience">Who it’s for</a>
          </div>
          <div>
            <span>The product</span>
            <a href="#platform">The case model</a>
            <a href="#workspace">Perspectives</a>
            <a href="#workflow">Loupes</a>
            <a href="#proof">How it’s built</a>
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
