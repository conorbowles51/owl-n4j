import { cn } from "@/lib/cn"

type LoupeLogoSize = "sidebar" | "login"

interface LoupeLogoProps {
  alt?: string
  className?: string
  size?: LoupeLogoSize
}

const sizeStyles: Record<LoupeLogoSize, { frame: string; image: string }> = {
  sidebar: {
    frame: "h-11 w-36",
    image: "absolute left-[-0.7rem] top-[-1.1rem] h-[5.1rem] w-[10.2rem] max-w-none",
  },
  login: {
    frame: "h-20 w-64",
    image: "absolute left-[-1.1rem] top-[-2rem] h-36 w-72 max-w-none",
  },
}

export function LoupeLogo({ alt = "Loupe", className, size = "sidebar" }: LoupeLogoProps) {
  const styles = sizeStyles[size]

  return (
    <span className={cn("relative block shrink-0 overflow-hidden", styles.frame, className)}>
      <img
        src="/loupe-red-light.png"
        alt={alt}
        decoding="async"
        className={cn("block dark:hidden", styles.image)}
      />
      <img
        src="/loupe-red-dark.png"
        alt={alt}
        decoding="async"
        className={cn("hidden dark:block", styles.image)}
      />
    </span>
  )
}
