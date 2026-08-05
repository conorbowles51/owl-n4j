import {
  chartMonths,
  chartSource,
  chartTotal,
  evidenceFiles,
  folders,
  recording,
  type EvidenceFile,
} from "../../data/case"
import { Reveal } from "../primitives/Reveal"
import styles from "./TheCase.module.css"

/**
 * The demonstration case, introduced as a dossier: who, what's in the box, and
 * the question the rest of the page answers. Every fact and filename here is
 * from case.ts; the receipts teach the red-mono device before the product uses
 * it. Spec §4.2.
 */

interface CastMember {
  name: string
  /** Keys into the entity palette via data-entity in the stylesheet. */
  entity: "person" | "organisation"
  role: string
  detail: string
  source: string
}

const cast: CastMember[] = [
  {
    name: "Marcus Chen",
    entity: "person",
    role: "Procurement — GlobalTech Industries",
    detail: "Interviewed on the record. One side of the recorded call.",
    source: "06_interview_marcus_chen.pdf, p.1",
  },
  {
    name: "Victoria Blackwood",
    entity: "person",
    role: "CEO — Nexus Trading Ltd",
    detail: "Appointed 14 February 2022 — the day the company was incorporated.",
    source: "02_company_registry_nexus.pdf, p.1",
  },
  {
    name: "Nexus Trading Ltd",
    entity: "organisation",
    role: "BVI company — Craigmuir Chambers, Tortola",
    detail: "No office, no staff, no website. Registration BVI-2022-847291.",
    source: "02_company_registry_nexus.pdf, p.1",
  },
]

function FolderGroup({ folder, files }: { folder: string; files: EvidenceFile[] }) {
  return (
    <div>
      <h3 className={styles.folderName}>
        {folder} · {files.length} {files.length === 1 ? "file" : "files"}
      </h3>
      <ul className={styles.fileList}>
        {files.map((file) => (
          <li key={file.name}>
            <span className={styles.fileName}>{file.name}</span>
            {file.kind === "Audio" ? (
              <span className={styles.callNote}>
                The recorded call — Chen and Blackwood, {recording.date} · {recording.duration}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  )
}

export function TheCase() {
  const groups = folders.map((folder) => ({
    folder,
    files: evidenceFiles.filter((file) => file.folder === folder),
  }))

  // The disclosure tranche dwarfs the other folders, so it takes a column of
  // its own and the small folders stack beside it — the two columns land at
  // roughly equal height instead of one long ragged list.
  const main = groups.reduce((a, b) => (b.files.length > a.files.length ? b : a))
  const side = groups.filter((group) => group !== main)

  const payments = chartMonths.filter((m) => m.amount > 0).length
  const millions = `€${(chartTotal / 1_000_000).toFixed(3)} million`

  return (
    <section className={styles.section} id="case" aria-labelledby="case-title">
      <div className={styles.inner}>
        <Reveal>
          <header className={styles.head}>
            <div>
              <p className={styles.eyebrow}>The demonstration</p>
              <h2 id="case-title">Thirteen files. One question.</h2>
            </div>
            <p className={styles.lede}>
              A procurement manager. A vendor with no office, no staff, no website. And {millions}{" "}
              that left the account as fast as it arrived. This is the case the rest of this page
              works — twelve PDFs and one recorded call.
            </p>
          </header>
        </Reveal>

        <Reveal delay={80}>
          <div className={styles.block}>
            <p className={styles.blockLabel}>The cast</p>
            <div className={styles.cast}>
              {cast.map((member) => (
                <div className={styles.castCard} data-entity={member.entity} key={member.name}>
                  <h3 className={styles.castName}>
                    <span className={styles.dot} aria-hidden="true" />
                    {member.name}
                  </h3>
                  <p className={styles.castRole}>{member.role}</p>
                  <p className={styles.castDetail}>{member.detail}</p>
                  <p className={styles.castSource}>
                    <span className="receipt">{member.source}</span>
                  </p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>

        <Reveal delay={160}>
          <div className={styles.block}>
            <div className={styles.filesHead}>
              <p className={styles.blockLabel}>The files</p>
              <p className={styles.mix}>
                Twelve PDFs · one recorded call · 2.1 MB of audio that becomes {recording.turns}{" "}
                searchable turns
              </p>
            </div>
            <div className={styles.filesGrid}>
              <div className={styles.folderMain}>
                <FolderGroup folder={main.folder} files={main.files} />
              </div>
              <div className={styles.folderSide}>
                {side.map((group) => (
                  <FolderGroup folder={group.folder} files={group.files} key={group.folder} />
                ))}
              </div>
            </div>
          </div>
        </Reveal>

        <Reveal delay={240}>
          <div className={styles.block}>
            <p className={styles.blockLabel}>The question</p>
            <p className={styles.questionText}>Where did {millions} go, and who sent it?</p>
            <p className={styles.questionMeta}>
              €{chartTotal.toLocaleString("en-GB")} · {payments} payments, March to December 2023 ·{" "}
              <span className="receipt">{chartSource}</span>
            </p>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <p className={styles.caption}>Illustrative case data</p>
        </Reveal>
      </div>
    </section>
  )
}
