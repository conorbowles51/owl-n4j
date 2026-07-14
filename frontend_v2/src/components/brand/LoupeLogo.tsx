import { cn } from "@/lib/cn"

type LoupeLogoSize = "sidebar" | "login"

interface LoupeLogoProps {
  alt?: string
  className?: string
  size?: LoupeLogoSize
}

const sizeStyles: Record<LoupeLogoSize, { frame: string; image: string; src: string }> = {
  sidebar: {
    frame: "h-11 w-36",
    image: "left-[-1.38rem] top-[-4rem] h-[10.8rem] w-[10.8rem] dark:brightness-0 dark:invert",
    src: "/loupe-logo-transparent.png",
  },
  login: {
    frame: "h-[3.75rem] w-44",
    image: "left-[-1.72rem] top-[-5rem] h-[13.5rem] w-[13.5rem] dark:brightness-0 dark:invert",
    src: "/loupe-logo-transparent.png",
  },
}

export function LoupeLogo({ alt = "Loupe", className, size = "sidebar" }: LoupeLogoProps) {
  const styles = sizeStyles[size]

  return (
    <span className={cn("relative block shrink-0 overflow-hidden", styles.frame, className)}>
      <img
        src={styles.src}
        alt={alt}
        className={cn("absolute max-w-none", styles.image)}
      />
    </span>
  )
}
