import { useEffect, useRef, type ReactNode, type CSSProperties } from 'react';

interface RevealProps {
  children: ReactNode;
  /** Stagger delay in seconds. */
  delay?: number;
  className?: string;
  as?: 'div' | 'section' | 'span' | 'li';
}

/**
 * Scroll-triggered reveal. Adds .is-visible once when ~20% enters the
 * viewport; CSS does the rest. Respects prefers-reduced-motion via CSS.
 */
export function Reveal({ children, delay = 0, className = '', as = 'div' }: RevealProps) {
  // Render as a generic element; the 'div' cast keeps the polymorphic
  // ref simple — all allowed tags share the HTMLElement interface we use.
  const Tag = as as 'div';
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          el.classList.add('is-visible');
          observer.disconnect();
        }
      },
      { threshold: 0.2, rootMargin: '0px 0px -40px 0px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const style = delay > 0 ? ({ '--reveal-delay': `${delay}s` } as CSSProperties) : undefined;

  return (
    <Tag ref={ref} className={`reveal ${className}`.trim()} style={style}>
      {children}
    </Tag>
  );
}
