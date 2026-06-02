import { useState, useEffect, useRef } from 'react';

/**
 * Animates a number from 0 to `target` over `duration` ms.
 * Uses ease-out cubic for a premium deceleration feel.
 * Respects prefers-reduced-motion — jumps to final value immediately.
 */
export function useCountUp(target, duration = 800, delay = 0) {
  const [value, setValue] = useState(0);
  const frameRef = useRef(null);

  useEffect(() => {
    if (target == null) return;

    // Respect reduced motion preference
    const prefersReduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (prefersReduced) {
      setValue(target);
      return;
    }

    let startTime = null;

    const tick = (timestamp) => {
      if (!startTime) startTime = timestamp + delay;
      const elapsed = timestamp - startTime;

      if (elapsed < 0) {
        frameRef.current = requestAnimationFrame(tick);
        return;
      }

      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(target * eased);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      } else {
        setValue(target);
      }
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
    };
  }, [target, duration, delay]);

  return value;
}
