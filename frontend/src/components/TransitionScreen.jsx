import { useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";
import AnimatedBackground from "./AnimatedBackground";
import "./TransitionScreen.css";

const EASE_EXPO = [0.16, 1, 0.3, 1];

/**
 * Full-screen wait message shown between a completed save and the next navigation
 * (farm creation → onboarding, onboarding finish/skip → dashboard). Reuses
 * `AnimatedBackground` as-is (no duplicated Ken Burns/wash/parallax/particle logic) —
 * blurred here specifically, since the message text sits directly on it with no
 * opaque card in between, unlike `/login`/`/create-farm`.
 *
 * Purely presentational: does not navigate itself. The caller renders this in place
 * of its normal content once the actual save has already succeeded, and supplies
 * `onComplete` to perform the (unchanged) navigation after `durationMs`.
 *
 * @param {string} message - Centered headline text.
 * @param {number} durationMs - How long to display before calling `onComplete`
 *   (always honored exactly, including under prefers-reduced-motion — this is a
 *   deliberate wait, not decorative motion).
 * @param {() => void} onComplete - Called once, after `durationMs`.
 */
export default function TransitionScreen({ message, durationMs, onComplete }) {
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const timer = setTimeout(() => onComplete?.(), durationMs);
    return () => clearTimeout(timer);
  }, [durationMs, onComplete]);

  return (
    <div className="transition-screen" role="status" aria-live="polite">
      <div className="transition-bg-blur">
        <AnimatedBackground src="/welcome-bg.jpg" />
      </div>
      <div className="transition-scrim" />

      <motion.div
        className="transition-content"
        initial={reduceMotion ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.7, ease: EASE_EXPO }}
      >
        <p className="transition-message">{message}</p>
        <div className="transition-progress-track">
          <motion.div
            className="transition-progress-fill"
            initial={{ width: "0%" }}
            animate={{ width: "100%" }}
            transition={{ duration: durationMs / 1000, ease: "linear" }}
          />
        </div>
      </motion.div>
    </div>
  );
}
