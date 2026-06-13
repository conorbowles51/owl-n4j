import { useEffect, useRef } from 'react';
import { RevealScene } from './scene';

/**
 * React wrapper for the canvas engine. Owns lifecycle only:
 * mount/unmount, resize, visibility-based pause, pointer parallax.
 */
export function HeroScene() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const scene = new RevealScene(canvas, { reducedMotion });

    if (import.meta.env.DEV) {
      // QA handle: freeze/inspect the scene from the console in dev builds.
      (window as unknown as { __arclightScene?: RevealScene }).__arclightScene = scene;
    }

    let inView = true;
    const syncRunning = () => {
      if (inView && !document.hidden) scene.start();
      else scene.stop();
    };

    const resizeObserver = new ResizeObserver(() => scene.resize());
    if (canvas.parentElement) resizeObserver.observe(canvas.parentElement);

    const intersectionObserver = new IntersectionObserver(
      (entries) => {
        inView = entries[0]?.isIntersecting ?? true;
        syncRunning();
      },
      { threshold: 0 },
    );
    intersectionObserver.observe(canvas);

    const onVisibility = () => syncRunning();
    document.addEventListener('visibilitychange', onVisibility);

    const onPointerMove = (e: PointerEvent) => {
      scene.setPointer(
        (e.clientX / window.innerWidth) * 2 - 1,
        (e.clientY / window.innerHeight) * 2 - 1,
      );
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    syncRunning();

    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('visibilitychange', onVisibility);
      intersectionObserver.disconnect();
      resizeObserver.disconnect();
      scene.destroy();
    };
  }, []);

  return <canvas ref={canvasRef} className="hero-canvas" aria-hidden="true" />;
}
