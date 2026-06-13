import { Wordmark } from './brand/Wordmark';

export function Footer() {
  return (
    <footer className="footer">
      <div className="container footer-inner">
        <div className="footer-brand">
          <Wordmark markSize={22} />
          <p className="footer-tagline">Investigation intelligence.</p>
        </div>
        <nav className="footer-links" aria-label="Footer">
          <a href="#how-it-works">How it works</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#security">Security</a>
          <a href="#who-its-for">Who it’s for</a>
        </nav>
        <p className="micro footer-legal">© 2026 Arclight. All rights reserved.</p>
      </div>
    </footer>
  );
}
