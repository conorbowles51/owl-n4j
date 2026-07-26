interface BrandLogoProps {
  className?: string
}

export function BrandLogo({ className = "" }: BrandLogoProps) {
  return (
    <span className={`brand-logo ${className}`}>
      <img
        className="brand-logo-on-dark"
        src="/loupe-red-dark.png"
        alt="Loupe"
        decoding="async"
      />
      <img
        className="brand-logo-on-light"
        src="/loupe-red-light.png"
        alt="Loupe"
        decoding="async"
      />
    </span>
  )
}
