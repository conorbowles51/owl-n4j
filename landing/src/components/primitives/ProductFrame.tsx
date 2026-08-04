import { Callout, type CalloutSpec } from "./Callout"
import styles from "./ProductFrame.module.css"

interface ProductFrameProps {
  /** Basename under /product, without extension or theme suffix. */
  slug: string
  alt: string
  callouts?: CalloutSpec[]
  /** Bleed past the container to the viewport edge. */
  bleed?: boolean
  /** Eager-load — use only for the hero. */
  priority?: boolean
  /** Which capture variant to use. Dark sits on obsidian grounds, light on paper. */
  theme?: "light" | "dark"
}

export function ProductFrame({
  slug,
  alt,
  callouts = [],
  bleed = false,
  priority = false,
  theme = "light",
}: ProductFrameProps) {
  const base = `/product/${slug}-${theme}`

  return (
    <figure className={bleed ? `${styles.frame} ${styles.bleed}` : styles.frame}>
      <div className={styles.shot}>
        <img
          src={`${base}.webp`}
          srcSet={`${base}@1280.webp 1280w, ${base}.webp 2560w`}
          sizes="(max-width: 900px) 100vw, 90vw"
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          decoding="async"
          width={2560}
          height={1440}
        />
        {callouts.map((c) => (
          <Callout key={c.text} {...c} />
        ))}
      </div>
      <figcaption className={styles.caption}>Illustrative case data</figcaption>
    </figure>
  )
}
