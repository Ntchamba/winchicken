import { useEffect } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";

const EASE_EXPO = [0.16, 1, 0.3, 1];

// Controlled modal video player for the landing page's "Voir une démo" button.
// `src` is a placeholder path (see README) — no real product video is committed yet.
export default function DemoVideoModal({ open, onClose, src }) {
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  const backdropTransition = { duration: reduceMotion ? 0 : 0.35, ease: EASE_EXPO };
  const panelTransition = { duration: reduceMotion ? 0 : 0.38, ease: EASE_EXPO };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="demo-modal-backdrop"
          initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
          animate={{ opacity: 1, backdropFilter: "blur(8px)" }}
          exit={{ opacity: 0, backdropFilter: "blur(0px)" }}
          transition={backdropTransition}
          onClick={onClose}
        >
          <motion.div
            className="demo-modal-panel"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={panelTransition}
            onClick={(e) => e.stopPropagation()}
          >
            <button className="demo-modal-close" onClick={onClose} aria-label="Fermer la vidéo">
              <X size={18} strokeWidth={2} />
            </button>
            <video src={src} controls autoPlay playsInline style={{ width: "100%", display: "block", borderRadius: 16 }} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
