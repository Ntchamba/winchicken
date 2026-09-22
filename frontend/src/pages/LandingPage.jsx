import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import { Play } from "lucide-react";
import { farmApi } from "../api/endpoints";
import AnimatedBackground from "../components/AnimatedBackground";
import FireflyField from "../components/FireflyField";
import DemoVideoModal from "../components/DemoVideoModal";
import useDocumentTitle from "../hooks/useDocumentTitle";
import "../styles/house-protocol-theme-light.css";
import "./landing.css";

const EASE_EXPO = [0.16, 1, 0.3, 1];

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: EASE_EXPO } },
};

// Headline/subtext get the same fade-up plus a blur-to-focus reveal — text looks
// like it's settling into focus rather than just appearing.
const blurReveal = {
  hidden: { opacity: 0, y: 20, filter: "blur(6px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.7, ease: EASE_EXPO } },
};

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.13, delayChildren: 0.05 } },
};

const PARALLAX_MAX = 10; // px — cursor-driven halo drift, capped small on purpose
const MAGNETIC_MAX = 5; // px — button pull toward cursor, capped small on purpose

// Small spring-backed x/y pair reused by the halo parallax and the two magnetic
// buttons — imperative .set() calls, no React re-renders, always eases back via spring.
function useSpringOffset() {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 150, damping: 18, mass: 0.4 });
  const springY = useSpring(y, { stiffness: 150, damping: 18, mass: 0.4 });
  return { x, y, springX, springY };
}

// Single welcome screen (landing page v2) — the only navigation is "Se connecter",
// routed by whether a farm already exists. Old marketing sections (nav, features,
// specs, contact, newsletter, footer) are gone, not hidden — see docs/deviations.md.
export default function LandingPage() {
  useDocumentTitle();
  const [farmExists, setFarmExists] = useState(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const navigate = useNavigate();
  const reduceMotion = useReducedMotion();
  const [fineCursor] = useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(pointer: fine)").matches
  );
  const parallaxEnabled = fineCursor && !reduceMotion;

  useEffect(() => {
    farmApi.exists().then(({ data }) => setFarmExists(data.exists)).catch(() => setFarmExists(false));
  }, []);

  const primaryPath = farmExists ? "/login" : "/create-farm";

  // Footer settles in last, after the rest of the stagger has finished — its own
  // variant (embedded transition takes precedence over a plain `transition` prop).
  const footerVariants = {
    hidden: fadeUp.hidden,
    show: { ...fadeUp.show, transition: { ...fadeUp.show.transition, delay: reduceMotion ? 0 : 0.9 } },
  };

  // Cursor-following halo (disabled on touch devices and under reduced motion). The
  // background image's own parallax lives inside <AnimatedBackground>.
  const halo = useSpringOffset();
  const handlePageMouseMove = (e) => {
    if (!parallaxEnabled) return;
    const nx = (e.clientX / window.innerWidth - 0.5) * 2;
    const ny = (e.clientY / window.innerHeight - 0.5) * 2;
    halo.x.set(nx * PARALLAX_MAX);
    halo.y.set(ny * PARALLAX_MAX);
  };
  const handlePageMouseLeave = () => {
    halo.x.set(0);
    halo.y.set(0);
  };

  // Magnetic buttons: shift a few px toward the cursor within their own bounds,
  // combined with (not replacing) the existing hover scale/shadow.
  const demoMagnet = useSpringOffset();
  const loginMagnet = useSpringOffset();
  const magneticHandlers = (magnet) => ({
    onMouseMove: (e) => {
      if (reduceMotion) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const relX = (e.clientX - rect.left) / rect.width - 0.5;
      const relY = (e.clientY - rect.top) / rect.height - 0.5;
      magnet.x.set(relX * 2 * MAGNETIC_MAX);
      magnet.y.set(relY * 2 * MAGNETIC_MAX);
    },
    onMouseLeave: () => {
      magnet.x.set(0);
      magnet.y.set(0);
    },
  });
  const demoHandlers = magneticHandlers(demoMagnet);
  const loginHandlers = magneticHandlers(loginMagnet);

  const resetAndOpenDemo = () => {
    demoMagnet.x.set(0);
    demoMagnet.y.set(0);
    setDemoOpen(true);
  };
  const resetAndNavigate = () => {
    loginMagnet.x.set(0);
    loginMagnet.y.set(0);
    navigate(primaryPath);
  };

  return (
    <div className="landing-welcome" onMouseMove={handlePageMouseMove} onMouseLeave={handlePageMouseLeave}>
      <AnimatedBackground src="/image22.png" />
      <FireflyField className="landing-fireflies" />

      <motion.div
        className="welcome-inner"
        initial={reduceMotion ? "show" : "hidden"}
        animate="show"
        variants={stagger}
      >
        <motion.div className="hero-mark-wrap" variants={fadeUp}>
          <motion.div
            className="hero-glow"
            aria-hidden="true"
            style={parallaxEnabled ? { x: halo.springX, y: halo.springY } : undefined}
            animate={reduceMotion ? undefined : { opacity: [0.5, 0.75, 0.5] }}
            transition={reduceMotion ? undefined : { duration: 22, repeat: Infinity, ease: "easeInOut" }}
          >
            <div className="hero-glow-mesh" />
          </motion.div>

          <div className="hero-mark-core">
            {!reduceMotion && (
              <>
                <motion.span
                  className="hero-radar-ring"
                  aria-hidden="true"
                  animate={{ scale: [1, 1.9], opacity: [0.32, 0] }}
                  transition={{ duration: 4.5, repeat: Infinity, ease: "easeOut" }}
                />
                <motion.span
                  className="hero-radar-ring"
                  aria-hidden="true"
                  animate={{ scale: [1, 1.9], opacity: [0.32, 0] }}
                  transition={{ duration: 4.5, repeat: Infinity, ease: "easeOut", delay: 2.25 }}
                />
              </>
            )}
            <span className="brand-mark hero-brand-mark">
              <img src="/logo-mark.png" alt="Winchicken" />
            </span>
          </div>
        </motion.div>

        <motion.h1 variants={blurReveal}>Bienvenue sur Winchicken</motion.h1>

        <motion.p className="welcome-subtext" variants={blurReveal}>
          Winchicken gère, selon votre paramétrage, le suivi complet de la ferme.
        </motion.p>

        <motion.div className="welcome-actions" variants={fadeUp}>
          <motion.button
            {...demoHandlers}
            style={{ x: demoMagnet.springX, y: demoMagnet.springY }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.18, ease: EASE_EXPO }}
            className="btn-pill outline lg" onClick={resetAndOpenDemo}
          >
            <Play size={16} /> Voir une démo
          </motion.button>
          <motion.button
            {...loginHandlers}
            style={{ x: loginMagnet.springX, y: loginMagnet.springY }}
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            transition={{ duration: 0.18, ease: EASE_EXPO }}
            className="btn-pill mint lg" onClick={resetAndNavigate}
          >
            Se connecter
          </motion.button>
        </motion.div>

        {farmExists === false && (
          <motion.p className="welcome-hint" variants={fadeUp}>
            Pas encore de compte ? La création se fait au premier lancement.
          </motion.p>
        )}
      </motion.div>

      <motion.footer
        className="welcome-footer"
        initial={reduceMotion ? "show" : "hidden"}
        animate="show"
        variants={footerVariants}
      >
        <span>© 2026 Winchicken</span>
        <a href="#" onClick={(e) => e.preventDefault()}>Mentions légales</a>
      </motion.footer>

      <DemoVideoModal open={demoOpen} onClose={() => setDemoOpen(false)} src="/demo.mp4" />
    </div>
  );
}
