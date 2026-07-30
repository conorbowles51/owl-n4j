interface HeroProps {
  onContact: () => void
}

export function Hero({ onContact }: HeroProps) {
  return (
    <section className="hero" id="top">
      <div className="container">
        <div className="hero-copy">
          <p className="eyebrow hero-enter hero-enter-1">
            Investigation platform · Fraud and criminal casework
          </p>
          <h1 className="hero-enter hero-enter-2">Query the whole case.</h1>
          <p className="hero-lede hero-enter hero-enter-3">
            Loupe resolves phone extractions, documents, financial records and audio into one
            connected model of the case — so a question reaches all of it at once, and every answer
            carries the file, page and passage behind it.
          </p>
          <div className="hero-actions hero-enter hero-enter-4">
            <button className="button button-primary" type="button" onClick={onContact}>
              Request a walkthrough
            </button>
            <a className="button button-ghost" href="#platform">
              See the platform
            </a>
          </div>
        </div>

        <figure className="hero-shot hero-enter hero-enter-5">
          <img
            src="/product/loupe-graph-demo.png"
            alt="A Loupe case graph connecting people, organisations, transactions and communications, with an entity panel open beside it"
            decoding="async"
            fetchPriority="high"
          />
        </figure>

        <p className="hero-proof hero-enter hero-enter-5">
          In production on federal fraud and criminal matters — multi-gigabyte phone extractions,
          tens of thousands of curated transactions, full document corpora.
        </p>
      </div>
    </section>
  )
}
