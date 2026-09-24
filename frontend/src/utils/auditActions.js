/**
 * French label for every `record_audit_log` action code — the code is never shown raw.
 * utils/__tests__/auditActions.test.js reads the backend and fails on a code with no label: this
 * was "kept in sync by hand" and had already drifted ("salary_payment.paid" and
 * "stock.item_created" showed raw in the journal, found by campaign 3).
 */
export const ACTION_LABELS = {
  "batch.created": "Bande créée",
  "batch.updated": "Bande modifiée",
  "batch.deleted": "Bande supprimée",
  "batch.closed": "Bande clôturée",
  "protocol.updated": "Protocole modifié",
  "employee.created": "Employé créé",
  "employee.updated": "Employé modifié",
  "employee.deleted": "Employé supprimé",
  "stock.updated": "Stock mis à jour",
  "expense.created": "Dépense enregistrée",
  "sale.created": "Vente enregistrée",
  "purchase_order.created": "Commande fournisseur créée",
  "purchase_order.received": "Commande fournisseur reçue",
  "purchase_order.cancelled": "Commande fournisseur annulée",
  "farm.reset": "Réinitialisation de la ferme",
  "unusual_case.resolved": "Cas particulier résolu",
  "equipment_fault.resolved": "Panne d'équipement résolue",
  "salary_payment.paid": "Salaire payé",
  "stock.item_created": "Article de stock créé",
  "stock.imported": "Stock importé (Excel)",
  "employee.imported": "Employés importés (Excel)",
};
