// Shared DRF error-response parsing (2026-08-26 — docs/deviations.md Part 13). A serializer
// field validation error comes back as `{field: [msg, ...]}`; a view-level rejection
// (permission denied, 409 conflict, bad login) as `{detail: msg}`; a request that never
// reached the server at all (backend down, CORS, timeout, offline) has no `err.response`.
// Every form in this app used to collapse all three into one hardcoded fallback string keyed
// off a single guessed field (`err.response?.data?.email?.[0] || "Vérifiez les champs."`) —
// which reads identically whether the user mistyped something or the whole API was
// unreachable. That ambiguity is what hid this project's real Part B incident (a crashed
// backend) behind a message that looked like a validation problem.

/** {field: firstMessage} for every field DRF returned an error on (excludes `detail`). */
export function getFieldErrors(err) {
  const data = err?.response?.data;
  if (!data || typeof data !== "object") return {};
  const fields = {};
  for (const [key, value] of Object.entries(data)) {
    if (key === "detail") continue;
    fields[key] = Array.isArray(value) ? String(value[0]) : String(value);
  }
  return fields;
}

/**
 * One human-readable line for a top-level banner: the request never reached the server, a
 * `detail` message, the first field error, or `fallback` — in that order.
 */
export function getServerErrorMessage(err, fallback = "Une erreur est survenue. Réessayez.") {
  if (!err?.response) {
    return "Le serveur est inaccessible. Vérifiez votre connexion et réessayez.";
  }
  const data = err.response.data;
  if (data?.detail) return data.detail;
  const firstFieldError = Object.values(getFieldErrors(err))[0];
  return firstFieldError || fallback;
}
