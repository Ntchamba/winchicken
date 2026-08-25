// Example data for the client-side-only /demo route. Never sent over the network,
// never written to the database (cahier des charges 5.4) — this is the ONLY place
// example data is allowed to appear.

export const DEMO_HOUSE_HEADER = { buildingName: "Bâtiment A", chicksPlaced: 500, growthCycle: 56, growthCycleUnit: "Day" };

export const DEMO_SCHEDULES = {
  feeding: [
    { id: 1, fromValue: 1, fromUnit: "Day", toValue: 15, toUnit: "Day", untilEnd: false, what: "Aliment démarrage", details: "3000 kcal, 22,5% de protéines" },
    { id: 2, fromValue: 15, fromUnit: "Day", toValue: 30, toUnit: "Day", untilEnd: false, what: "Aliment croissance", details: "3150 kcal, 21,5% de protéines" },
  ],
  temperature: [
    { id: 3, fromValue: 1, fromUnit: "Day", toValue: 3, toUnit: "Day", untilEnd: false, what: "Démarrage (éleveuse)", details: "Éleveuse 38°C, salle > 28°C" },
  ],
  health: [
    { id: 4, fromValue: 2, fromUnit: "Day", toValue: 4, toUnit: "Day", untilEnd: false, what: "Anti-infectieux + vitamines", details: "Dans l'eau de boisson" },
  ],
  vaccination: [
    { id: 5, fromValue: 1, fromUnit: "Day", toValue: 1, toUnit: "Day", untilEnd: false, what: "Maladie de Newcastle", details: "Hitchner B1, goutte oculaire" },
  ],
  cleaning: [
    { id: 6, fromValue: 1, fromUnit: "Week", toValue: 1, toUnit: "Week", untilEnd: true, what: "Ajout de litière", details: "+40kg au jour 7" },
  ],
};

// `detail` values must match HouseProtocolForm/StockParametersForm's option values
// exactly (English for `feed`, per the FeedStage backend enum; French elsewhere,
// since those aren't sent to any backend enum) — never the raw display label.
export const DEMO_STOCK = {
  feed: [{ id: 1, item: "Aliment démarrage", detail: "Starter", threshold: 200, unit: "kg", price: 450 }],
  veterinary: [{ id: 2, item: "Newcastle (HB1)", detail: "Chaîne du froid : Oui", threshold: 20, unit: "dose", price: 15 }],
  equipment: [{ id: 3, item: "Abreuvoirs cloche", detail: "Pour 15 volailles", threshold: 5, unit: "unité", price: 3000 }],
  bedding: [{ id: 4, item: "Copeaux de bois", detail: "Bois tendre", threshold: 50, unit: "sac", price: 2000 }],
};

// `type` stays English ("Broiler"/"Layer") — matches HomeDashboard's HOUSE_TYPE_LABELS
// map key exactly, translated only at that one display point.
export const DEMO_HOUSES = [
  { houseCode: "H-DEMO-001", name: "Bâtiment A", type: "Broiler", status: "active", day: 24, cycle: 56, count: 480, capacity: 500 },
  { houseCode: "H-DEMO-002", name: "Bâtiment B", type: "Layer", status: "active", day: 140, cycle: null, count: 950, capacity: 1000 },
  { houseCode: "H-DEMO-003", name: "Bâtiment D", type: "Broiler", status: "void", day: null, cycle: null, count: 0, capacity: 500 },
];

export const DEMO_ALERTS = [
  { id: 1, severity: "danger", ruleType: "LOW_STOCK", message: "Aliment démarrage sous le seuil — Bâtiment A", triggeredAt: new Date(Date.now() - 12 * 60000).toISOString() },
  { id: 2, severity: "warning", ruleType: "VACCINE_DUE", message: "Vaccin Newcastle (HB1) à faire demain — Bâtiment A", triggeredAt: new Date(Date.now() - 3600000).toISOString() },
  { id: 3, severity: "info", ruleType: "SANITARY_VOID_END", message: "Fin du vide sanitaire dans 2 jours — Bâtiment D", triggeredAt: new Date(Date.now() - 7200000).toISOString() },
];
