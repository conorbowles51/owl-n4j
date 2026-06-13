interface MarkProps {
  size?: number;
}

/**
 * The Arclight mark: an arc of light over a node of evidence.
 * Pure SVG so a rebrand costs nothing.
 */
export function Mark({ size = 26 }: MarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className="brand-mark"
    >
      <path
        d="M 6.6 16.6 A 10 10 0 0 1 25.4 16.6"
        stroke="var(--arc)"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="16" cy="21" r="3.2" fill="var(--arc-bright)" />
      <circle cx="27.4" cy="20.4" r="1.3" fill="var(--arc)" />
    </svg>
  );
}
