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

// French names of the fields the API validates, for a banner that shows one field's error:
// DRF's own messages ("Ce champ est obligatoire.", "Un nombre valide est requis.") never say
// which field they are about, and a farmer cannot act on "Ce champ est obligatoire." alone.
const FIELD_LABELS = {
  name: "Nom", email: "Email", password: "Mot de passe", role: "Rôle", phone: "Téléphone",
  civility: "Civilité", hourly_rate: "Taux horaire", hours_worked: "Heures", user: "Employé",
  date: "Date", log_date: "Date", sale_date: "Date de la vente", expense_date: "Date de la dépense",
  movement_date: "Date", order_date: "Date de la commande", start_date: "Date de début",
  planned_end_date: "Date de fin prévue", quantity: "Quantité", unit_price: "Prix unitaire",
  amount: "Montant", product_type: "Produit", customer: "Client", category: "Catégorie",
  supplier: "Fournisseur", item: "Article", unit: "Unité", alert_threshold: "Seuil d'alerte",
  mortality: "Mortalité", eggs_collected: "Œufs collectés", avg_sample_weight: "Poids moyen",
  feed_consumed_kg: "Aliment consommé", water_consumed_l: "Eau consommée",
  case_description: "Description", batch: "Bande", house: "Bâtiment", max_capacity: "Capacité",
  initial_count: "Poussins mis en place", what: "Action", from_value: "De", to_value: "À",
  start_time: "Heure de début", end_time: "Heure de fin", note: "Note", ingredients: "Ingrédients",
};

// DRF / Django's generic messages — the ones that never say which field they are about. A
// message the backend wrote itself ("Ce fournisseur existe déjà.") already does, and is left alone.
const GENERIC_MESSAGE = /^(ce champ|cette valeur|cette liste|assurez-vous|un nombre|un entier|une valeur|saisissez un nombre|la date a un format|le format|format de|« .* » n'est pas un choix|nombre de caractères)/i;

/** `"Mortalité : Ce champ est obligatoire."` — for a generic message only. */
function withFieldLabel(key, message) {
  const label = FIELD_LABELS[key];
  if (!label || !GENERIC_MESSAGE.test(message.trim())) return message;
  return `${label} : ${message}`;
}

// Appended to what went wrong, so every message also says what to do next.
const RETRY_LATER = "Réessayez dans un instant ; si cela continue, prévenez l'administrateur de la ferme.";
const ASK_ADMIN = "Demandez à l'administrateur de la ferme si vous devez pouvoir le faire.";

/**
 * One human-readable line for a top-level banner: the request never reached the server, a
 * `detail` message, the first field error (named), or `fallback` — in that order. A server
 * error (5xx) or a refusal (403) also says what to do next (phone usability audit, 2026-09-25:
 * "Impossible d'enregistrer." said what failed, never what to do about it).
 */
export function getServerErrorMessage(err, fallback = "Une erreur est survenue. Réessayez.") {
  if (!err?.response) {
    // Only a request that went out and got nothing back is "unreachable" (axios: `request` set,
    // no `response` — offline, timeout, CORS). A bug in the page itself, e.g. a TypeError while
    // building the payload, used to be reported as "server unreachable" too, and sent a farmer
    // chasing their connection for an error no connection could fix (campaign 9, finding B18).
    if (err?.isAxiosError || err?.request != null || ["ERR_NETWORK", "ECONNABORTED", "ETIMEDOUT"].includes(err?.code)) {
      return "Le serveur est inaccessible. Vérifiez votre connexion et réessayez.";
    }
    if (err) console.error(err);
    return fallback;
  }
  const { status } = err.response;
  const data = err.response.data;
  if (status >= 500) {
    const base = fallback.replace(/\s*Réessayez\.?$/, "");
    return `${base} Le serveur a rencontré un problème. ${RETRY_LATER}`;
  }
  if (data?.detail) return status === 403 ? `${data.detail} ${ASK_ADMIN}` : data.detail;
  const [key, message] = Object.entries(getFieldErrors(err))[0] || [];
  if (message) return withFieldLabel(key, message);
  return fallback;
}
