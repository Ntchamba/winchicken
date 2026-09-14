import { useMemo } from "react";
import { useReducedMotion } from "framer-motion";
import "./FireflyField.css";

const DEFAULT_COUNT = 200;
const rand = (min, max) => min + Math.random() * (max - min);

// Generated once per mount (not per render, not hand-authored): each firefly is a bare
// <span> carrying only inline CSS custom properties. A single shared class + one @keyframes
// in FireflyField.css does all the animation — 200 elements, one rule.
function makeFireflies(count) {
  return Array.from({ length: count }, () => ({
    x: rand(0, 100),        // % of container width
    y: rand(0, 100),        // % of container height
    size: rand(5, 8),       // px — randomized variance kept so the 200 don't look identical
    dur: rand(6, 14),       // s — shortened so the drift reads as motion at a glance
    delay: -rand(0, 18),    // s — negative so they start mid-cycle and never sync
    tx: rand(-60, 60),      // px drift (transform only) — larger travel = clearly perceptible motion
    ty: rand(-60, 60),
    op: rand(0.6, 0.7),     // peak opacity — bright, distinct points (scaled down on /login,/create-farm via --op-scale)
  }));
}

/**
 * Pure-CSS firefly field — ~200 softly glowing points drifting over whatever is behind it.
 * Independent of `AnimatedBackground` so it can be mounted with the image hero (welcome /
 * login / create-farm) or over a flat colour (the dashboard sidebar's navy).
 *
 * Performance shape: the keyframes touch only `transform` (translate3d + slight scale) and
 * `opacity` — never layout/paint properties. Each dot's glow is a `radial-gradient`
 * background (painted once into its layer), not a per-element `filter: blur()`. `will-change`
 * lives on the container, not the 200 children, to keep the compositor to one extra layer.
 *
 * `prefers-reduced-motion`: nothing is rendered at all (the CSS also hard-hides the layer as
 * a defence-in-depth fallback).
 *
 * @param {string} [className] - extra class on the container (positioning / z-index per host).
 * @param {number} [count=200]
 */
export default function FireflyField({ className = "", count = DEFAULT_COUNT }) {
  const reduceMotion = useReducedMotion();
  const fireflies = useMemo(() => makeFireflies(count), [count]);

  if (reduceMotion) return null;

  return (
    <div className={`firefly-field ${className}`.trim()} aria-hidden="true">
      {fireflies.map((f, i) => (
        <span
          key={i}
          className="firefly"
          style={{
            "--x": `${f.x}%`,
            "--y": `${f.y}%`,
            "--size": `${f.size}px`,
            "--dur": `${f.dur}s`,
            "--delay": `${f.delay}s`,
            "--tx": `${f.tx}px`,
            "--ty": `${f.ty}px`,
            "--op": f.op,
          }}
        />
      ))}
    </div>
  );
}
