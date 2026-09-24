// Shared DRF error-response parsing (2026-08-26 — docs/deviations.md Part 13). A serializer
// field validation error comes back as `{field: [msg, ...]}`; a view-level rejection
// (permission denied, 409 conflict, bad login) as `{detail: msg}`; a request that never
// reached the server at all (backend down, CORS, timeout, offline) has no `err.response`.
// Every form in this app used to collapse all three into one hardcoded fallback string keyed
// off a single guessed field (`err.response?.data?.email?.[0] || "Vérifiez les champs."`) —
// which reads identically whether the user mistyped something or the whole API was
// unreachable. That ambiguity is what hid this project's real Part B incident (a crashed
// backend) behind a message that looked like a validation problem.

const isLineIndex = (key) => /^\d+$/.test(String(key));

/**
 * The first readable message anywhere in a DRF error value. A PUT of a list (the protocol lines)
 * answers per line — `{"0": {"non_field_errors": [...]}}` or `{lines: [{}, {what: [...]}]}` — and
 * String() of that printed "[object Object]" in the form. A message found inside a line is
 * prefixed "Ligne N :" so the user knows which one to fix.
 */
function firstMessage(value) {
  if (value == null) return null;
  if (typeof value === "string" || typeof value === "number") return String(value);
  const entries = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value);
  for (const [key, inner] of entries) {
    const message = firstMessage(inner);
    if (!message) continue;
    const isLine = isLineIndex(key) && inner !== null && typeof inner === "object" && !Array.isArray(inner);
    return isLine ? `Ligne ${Number(key) + 1} : ${message}` : message;
  }
  return null;
}

/** {field: firstMessage} for every field DRF returned an error on (excludes `detail`). */
export function getFieldErrors(err) {
  const data = err?.response?.data;
  if (!data || typeof data !== "object") return {};
  const fields = {};
  for (const [key, value] of Object.entries(data)) {
    if (key === "detail") continue;
    const message = firstMessage(isLineIndex(key) && value && typeof value === "object" ? { [key]: value } : value);
    if (message) fields[key] = message;
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
