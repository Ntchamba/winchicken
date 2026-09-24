import { useEffect, useState } from "react";
import { stockApi } from "../api/endpoints";

const NONE = [];

/** A stock item as the protocol form's Consommation selector needs it. */
export const toStockItemOption = (item) => ({ item_code: item.item_code, name: item.name, unit: item.unit });

/**
 * The farm's stock items for the protocol form's Consommation selector.
 *
 * The onboarding and full-page protocol screens rendered the form without them, so after a page
 * reload the selector knew no article and offered "Créer « Provende »" for one the farm already
 * had — which created a second "Provende" (campaign 3, found in the browser). Same shape the
 * "Modifier le protocole" modal builds with `toStockItemOption`.
 */
/**
 * @param {?number} farmId
 * @param {*} [refreshKey] - reloads when it changes: the Excel onboarding path creates articles
 *   after the page mounted, and the review form showed their rows as consuming nothing.
 */
export default function useStockItemOptions(farmId, refreshKey) {
  const [items, setItems] = useState(NONE);
  useEffect(() => {
    if (!farmId) return undefined;
    let cancelled = false;
    stockApi
      .items(farmId)
      .then(({ data }) => { if (!cancelled) setItems((data.items || []).map(toStockItemOption)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [farmId, refreshKey]);
  return items;
}
