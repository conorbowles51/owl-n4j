import { useEffect, useState } from 'react';
import { Wordmark } from './brand/Wordmark';

interface NavProps {
  onBookDemo: () => void;
}

const LINKS = [
  { href: '#how-it-works', label: 'How it works' },
  { href: '#capabilities', label: 'Capabilities' },
  { href: '#security', label: 'Security' },
  { href: '#who-its-for', label: 'Who it’s for' },
];

export function Nav({ onBookDemo }: NavProps) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header className={`nav ${scrolled ? 'nav-scrolled' : ''}`}>
      <nav className="container nav-inner" aria-label="Main">
        <a href="#top" className="nav-brand" aria-label="Arclight home">
          <Wordmark />
        </a>
        <div className="nav-links">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} className="nav-link">
              {link.label}
            </a>
          ))}
        </div>
        <button type="button" className="btn btn-primary nav-cta" onClick={onBookDemo}>
          Book a demo
        </button>
      </nav>
    </header>
  );
}
