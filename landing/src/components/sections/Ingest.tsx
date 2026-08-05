import { Fragment } from "react"
import { evidenceFiles, evidenceTotalEntities, graphCounts } from "../../data/case"
import { Reveal } from "../primitives/Reveal"
import styles from "./Ingest.module.css"

/** Intake formats the product accepts — the chips the spec names, not the demo folder's mix. */
const formats = ["PDF", "MP3", "UFDR", "XLSX"] as const

/** Chip centres on the connector's 0–100 grid: four equal rows. */
const pathStarts = [12.5, 37.5, 62.5, 87.5]

/** Folder in → model out, every figure from the demonstration case. */
const stats = [
  { figure: String(evidenceFiles.length), label: "files" },
  { figure: String(evidenceTotalEntities), label: "sourced facts" },
  {
    figure: `${graphCounts.all.nodes} · ${graphCounts.all.edges}`,
    label: "entities · relationships",
  },
]

export function Ingest() {
  return (
    <section className={styles.ingest} id="ingest">
      <div className={styles.inner}>
        <Reveal>
          <div className={styles.top}>
            <header>
              <p className={styles.eyebrow}>Intake</p>
              <h2 className={styles.title}>Drop the folder in. Come back to a model.</h2>
              <p className={styles.lede}>
                Loupe reads every page, finds the people, companies, accounts and
                transactions, works out which mentions are the same thing, and ties every
                fact to the page it came from.
              </p>
            </header>

            {/* Drawn, not captured. The hero already spent the page's one aesthetic
                risk, so intake stays diagrammatic: formats converging on one node.
                Decorative — the headline says the same thing in words. */}
            <div className={styles.flow} aria-hidden="true">
              <ul className={styles.chips}>
                {formats.map((format) => (
                  <li key={format} className={styles.chip}>
                    {format}
                  </li>
                ))}
              </ul>

              <svg className={styles.paths} viewBox="0 0 100 100" preserveAspectRatio="none">
                {pathStarts.map((y) => (
                  <path
                    key={y}
                    d={`M 0 ${y} C 52 ${y}, 48 50, 100 50`}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              </svg>

              <div className={styles.model}>
                <span className={styles.orb} />
                <span className={styles.modelLabel}>Case model</span>
              </div>
            </div>
          </div>
        </Reveal>

        <Reveal delay={140}>
          <div className={styles.tally}>
            <ul className={styles.stats}>
              {stats.map((stat, i) => (
                <Fragment key={stat.label}>
                  {i > 0 ? (
                    <li className={styles.arrow} aria-hidden="true">
                      →
                    </li>
                  ) : null}
                  <li className={styles.stat}>
                    <span className={styles.figure}>{stat.figure}</span>
                    <span className={styles.label}>{stat.label}</span>
                  </li>
                </Fragment>
              ))}
            </ul>

            <div className={styles.foot}>
              {/* Verbatim from spec §4.3; the figure is claims.ts `ingestWindowHours`. */}
              <p className={styles.window}>
                A few hundred documents takes twelve to twenty-four hours. It runs
                unattended overnight.
              </p>
              <p className={styles.caption}>Illustrative case data</p>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
