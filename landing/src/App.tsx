import { useState } from 'react';
import { Nav } from './components/Nav';
import { Hero } from './components/Hero';
import { Problem } from './components/Problem';
import { HowItWorks } from './components/HowItWorks';
import { Capabilities } from './components/Capabilities';
import { Trust } from './components/Trust';
import { Audience } from './components/Audience';
import { FinalCta } from './components/FinalCta';
import { Footer } from './components/Footer';
import { DemoModal } from './components/DemoModal';

function App() {
  const [demoOpen, setDemoOpen] = useState(false);
  const openDemo = () => setDemoOpen(true);

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <Nav onBookDemo={openDemo} />
      <main id="main">
        <Hero onBookDemo={openDemo} />
        <Problem />
        <hr className="section-rule" />
        <HowItWorks />
        <hr className="section-rule" />
        <Capabilities />
        <hr className="section-rule" />
        <Trust />
        <hr className="section-rule" />
        <Audience />
        <FinalCta onBookDemo={openDemo} />
      </main>
      <Footer />
      {demoOpen && <DemoModal open={demoOpen} onClose={() => setDemoOpen(false)} />}
      <div className="grain" aria-hidden="true" />
    </>
  );
}

export default App;
