import { useEffect } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import "./AnimatedBackground.css";

const PARALLAX_MAX = 13; // px — cursor-driven drift, capped small on purpose

/**
 * Shared full-bleed animated hero background: base image + slow Ken Burns pan/zoom +
 * independent mint gradient wash + cursor parallax + a dark scrim for text contrast.
 * The firefly field is a separate, composable layer (`FireflyField`) — mount it as a
 * child here, or on its own elsewhere.
 *
 * Layering: the image / wash / scrim sit at z-index 0; `children` render in a
 * `.animated-bg-content` wrapper at z-index 1, unaffected by the background's transforms.
 * Callers that prefer to keep foreground content as a sibling (with their own z-index) can
 * still do that and pass no children.
 *
 * All motion is GPU-friendly (transform/opacity only). Under `prefers-reduced-motion` the
 * Ken Burns pan and parallax are frozen and the parallax listener isn't attached; the
 * gradient wash is left as a near-static layer.
 *
 * @param {string} src - Background image URL (e.g. "/image22.png").
 * @param {boolean} [blur] - Blur the image layer only (login / create-farm: a sharp card
 *   sits on top). Wash/scrim/children are unaffected. Also freezes Ken Burns on that layer
 *   (invisible through the blur, and animating a filter's input every frame is costly).
 * @param {string} [className] - extra class on the root.
 * @param {React.ReactNode} [children] - foreground content, rendered on top at z-index 1.
 */
export default function AnimatedBackground({ src, blur = false, className = "", children }) {
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
    <div className={`animated-bg ${className}`.trim()} aria-hidden={children ? undefined : "true"}>
      <motion.div
        className={`animated-bg-parallax ${blur ? "is-blurred" : ""}`.trim()}
        style={{ x: springX, y: springY }}
      >
        {/* Ken Burns is skipped when `blur` is set (login / create-farm): an 8% zoom is
            imperceptible through the 9px blur + opaque card on top, and animating the blur
            filter's input every frame is its single biggest raster cost. Parallax (a small
            composited translate on the parent) still applies. */}
        <motion.div
          className="animated-bg-image"
          style={{ backgroundImage: `url('${src}')` }}
          animate={reduceMotion || blur ? undefined : { scale: [1, 1.08], x: ["0%", "-2%"], y: ["0%", "1.2%"] }}
          transition={reduceMotion || blur ? undefined : { duration: 40, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
        />
      </motion.div>
      <div className="animated-bg-wash" />
      <div className="animated-bg-scrim" />
      {children && <div className="animated-bg-content">{children}</div>}
    </div>
  );
}
