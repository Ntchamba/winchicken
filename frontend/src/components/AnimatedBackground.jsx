import { useEffect } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import "./AnimatedBackground.css";

const PARALLAX_MAX = 13; // px — cursor-driven drift, capped small on purpose

// Sparse drifting motes — positions/timings fixed (not re-randomized per render),
// independent-feeling only via varied duration/delay.
const MOTES = [
  { left: "8%", top: "18%", size: 3, duration: 22, delay: 0 },
  { left: "82%", top: "12%", size: 2, duration: 26, delay: 3 },
  { left: "18%", top: "72%", size: 4, duration: 30, delay: 1.5 },
  { left: "65%", top: "80%", size: 2, duration: 24, delay: 5 },
  { left: "40%", top: "30%", size: 3, duration: 28, delay: 2 },
  { left: "92%", top: "55%", size: 2, duration: 21, delay: 4 },
  { left: "25%", top: "48%", size: 3, duration: 27, delay: 6 },
  { left: "55%", top: "15%", size: 2, duration: 23, delay: 1 },
  { left: "10%", top: "85%", size: 3, duration: 29, delay: 3.5 },
  { left: "75%", top: "35%", size: 2, duration: 25, delay: 2.5 },
];

/**
 * Shared full-bleed animated hero background — Ken Burns pan/zoom, animated mint
 * gradient wash, cursor parallax, sparse particle drift, dark scrim for text contrast.
 * Renders behind whatever content the caller layers on top (absolutely positioned,
 * z-index 0) — the caller is responsible for `position:relative` on its own container
 * and for giving its foreground content `z-index:1`+.
 *
 * All effects are GPU-friendly (transform/opacity only) and fully respect
 * prefers-reduced-motion (frozen, not just slowed — parallax listener isn't even
 * attached, Ken Burns doesn't animate, particles aren't rendered).
 *
 * @param {string} src - Background image URL (e.g. "/welcome-bg.jpg").
 */
export default function AnimatedBackground({ src }) {
  const reduceMotion = useReducedMotion();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 150, damping: 18, mass: 0.4 });
  const springY = useSpring(y, { stiffness: 150, damping: 18, mass: 0.4 });

  useEffect(() => {
    const fineCursor = typeof window !== "undefined" && window.matchMedia?.("(pointer: fine)").matches;
    if (!fineCursor || reduceMotion) return;
    const onMove = (e) => {
      const nx = (e.clientX / window.innerWidth - 0.5) * 2;
      const ny = (e.clientY / window.innerHeight - 0.5) * 2;
      x.set(nx * PARALLAX_MAX);
      y.set(ny * PARALLAX_MAX);
    };
    const onLeave = () => { x.set(0); y.set(0); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseleave", onLeave);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseleave", onLeave);
    };
  }, [reduceMotion, x, y]);

  return (
    <div className="animated-bg" aria-hidden="true">
      <motion.div className="animated-bg-parallax" style={{ x: springX, y: springY }}>
        <motion.div
          className="animated-bg-image"
          style={{ backgroundImage: `url('${src}')` }}
          animate={reduceMotion ? undefined : { scale: [1, 1.08], x: ["0%", "-2%"], y: ["0%", "1.2%"] }}
          transition={reduceMotion ? undefined : { duration: 40, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
        />
      </motion.div>
      <div className="animated-bg-wash" />
      <div className="animated-bg-scrim" />
      {!reduceMotion && (
        <div className="animated-bg-particles">
          {MOTES.map((m, i) => (
            <span
              key={i}
              className="animated-bg-mote"
              style={{
                left: m.left, top: m.top, width: m.size, height: m.size,
                animationDuration: `${m.duration}s`, animationDelay: `${m.delay}s`,
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
