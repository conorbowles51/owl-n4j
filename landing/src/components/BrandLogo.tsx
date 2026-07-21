interface BrandLogoProps {
  light?: boolean
  className?: string
}
export function BrandLogo({ light = true, className = "" }: BrandLogoProps) {
  return (
    <span className={`brand-logo ${light ? "brand-logo-light" : ""} ${className}`}>
      <img src="/loupe-logo-transparent.png" alt="Loupe" />
    </span>
  )
}
