import { useEffect } from "react";

/**
 * Sets the browser tab title for the current screen (2026-08-25) — "Winchicken" alone when
 * called with no argument/an empty string (the landing page), "Winchicken — {suffix}"
 * otherwise. No cleanup/restore on unmount: React Router only ever has one top-level route
 * component mounted at a time, and navigating to a new route mounts a component that sets its
 * own title anyway, so there is nothing to restore.
 *
 * @param {string} [suffix] - The screen-specific part of the title (e.g. "Connexion").
 */
export default function useDocumentTitle(suffix) {
  useEffect(() => {
    document.title = suffix ? `Winchicken — ${suffix}` : "Winchicken";
  }, [suffix]);
}
