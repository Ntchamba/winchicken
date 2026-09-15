import client, { API_URL } from "./client";

// Protocol rows Excel import (docs/excel-import.md). `parse` uploads an .xlsx and gets back
// the parsed rows + per-row skip report — the frontend merges them into HouseProtocolForm.
// `templateUrl` is a plain link target (the endpoint is AllowAny, static content).
export const protocolImportApi = {
  // `preview` asks the server to return the column-mapping report even when a required column
  // couldn't be resolved, instead of a 400 — the batch-creation screen shows which column needs
  // attention and keeps its confirm button disabled.
  parse: (file, { preview = false } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (preview) fd.append("preview", "1");
    return client.post("/protocols/import-xlsx/", fd);
  },
  templateUrl: `${API_URL}/protocols/import-template.xlsx`,
};

export const farmApi = {
  exists: () => client.get("/farm/exists/"),
  // "Bilan global" tree — core status + santé/finances/stock branches, all computed
  // server-side from the thresholds in apps/core/overview.py.
  overview: () => client.get("/farm/overview/"),
  create: (payload) => client.post("/farm/create/", payload),
  reset: (password) => client.post("/farm/reset/", { password }),
  // Unauthenticated two-step reset reachable from /login (no session): verify admin
  // credentials → get a 5-min token, then confirm with the token + exact farm name.
  resetRequest: (email, password) => client.post("/farm/reset/request/", { email, password }),
  resetConfirm: (token, farmName) => client.post("/farm/reset/confirm/", { token, farm_name: farmName }),
};

export const authApi = {
  login: (email, password) => client.post("/auth/login/", { email, password }),
  me: () => client.get("/auth/me/"),
};

export const employeesApi = {
  list: () => client.get("/employees/"),
  create: (payload) => client.post("/employees/", payload),
  update: (id, payload) => client.put(`/employees/${id}/`, payload),
  remove: (id) => client.delete(`/employees/${id}/`),
  setHourlyRate: (id, hourlyRate) => client.patch(`/employees/${id}/hourly-rate/`, { hourly_rate: hourlyRate }),
  payrollList: () => client.get("/employees/payroll/"),
  // Excel import — update-or-create by Email (never deletes, never resets an existing
  // password; new accounts get a temp password returned in `newAccounts`).
  importXlsx: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return client.post("/employees/import-xlsx/", fd);
  },
  importTemplateUrl: `${API_URL}/employees/import-template.xlsx`,
};

export const housesApi = {
  list: () => client.get("/houses/"),
  create: (payload) => client.post("/houses/", payload),
  detail: (houseCode) => client.get(`/houses/${houseCode}/`),
  update: (houseCode, payload) => client.patch(`/houses/${houseCode}/`, payload),
  remove: (houseCode) => client.delete(`/houses/${houseCode}/`),
  getProtocol: (houseCode) => client.get(`/houses/${houseCode}/protocol/`),
  putProtocol: (houseCode, lines) => client.put(`/houses/${houseCode}/protocol/`, { lines }),
  listProtocolCategories: (houseCode) => client.get(`/houses/${houseCode}/protocol-categories/`),
  addProtocolCategory: (houseCode, payload) => client.post(`/houses/${houseCode}/protocol-categories/`, payload),
  removeProtocolCategory: (houseCode, categoryId) => client.delete(`/houses/${houseCode}/protocol-categories/${categoryId}/`),
  tasksNow: (houseCode) => client.get(`/houses/${houseCode}/tasks-now/`),
  assignTask: (houseCode, taskId, userId) =>
    client.patch(`/houses/${houseCode}/tasks-now/${taskId}/assign/`, { assigned_to: userId }),
  // Every assignment the house carries, due today or not (FIX 4) — tasksNow only lists what is
  // due now, which is what made an assignment invisible the day after its task ran.
  assignments: (houseCode) => client.get(`/houses/${houseCode}/assignments/`),
  milestones: (houseCode) => client.get(`/houses/${houseCode}/milestones/`),
};

export const tasksApi = {
  mine: () => client.get("/tasks/mine/"),
  upcoming: () => client.get("/tasks/upcoming/"),
  assignableUsers: () => client.get("/tasks/assignable-users/"),
  // "Marquer comme fait" — records the completion and, when the protocol line links a
  // resource, deducts it. Without `force`, an insufficient stock level comes back as
  // {status: 'insufficient_stock', shortfall} and nothing is written; the caller confirms and
  // re-posts with force. See apps/stock/consumption.py.
  // `timeSlotId` identifies which occurrence of a multi-slot line this is (a twice-daily
  // feeding line is two tasks a day). Null/undefined for an untimed line, which is what the
  // endpoints already treat as "the one occurrence of the day".
  complete: (houseCode, taskId, { force = false, timeSlotId = null } = {}) =>
    client.post(`/houses/${houseCode}/tasks-now/${taskId}/complete/`, {
      ...(force ? { force: true } : {}),
      ...(timeSlotId ? { time_slot_id: timeSlotId } : {}),
    }),
  uncomplete: (houseCode, taskId, { timeSlotId = null } = {}) =>
    client.post(`/houses/${houseCode}/tasks-now/${taskId}/uncomplete/`,
      timeSlotId ? { time_slot_id: timeSlotId } : {}),
};

export const auditLogApi = {
  list: (params) => client.get("/audit-log/", { params }),
};

export const scheduleApi = {
  month: (month) => client.get("/protocols/schedule/", { params: { month } }),
};

export const onboardingApi = {
  submit: (payload) => client.post("/protocols/onboarding/", payload),
};

export const batchesApi = {
  list: (houseCode) => client.get("/batches/", { params: houseCode ? { house_code: houseCode } : {} }),
  create: (payload) => client.post("/batches/", payload),
  updateName: (batchCode, name) => client.patch(`/batches/${batchCode}/`, { name }),
  quickEdit: (batchCode, fields) => client.patch(`/batches/${batchCode}/`, fields),
  remove: (batchCode) => client.delete(`/batches/${batchCode}/`),
  close: (batchCode) => client.patch(`/batches/${batchCode}/close/`),
  dailyLogs: (batchCode) => client.get(`/batches/${batchCode}/daily-logs/`),
  addDailyLog: (batchCode, payload) => client.post(`/batches/${batchCode}/daily-logs/`, payload),
  quickEntry: (batchCode, payload) => client.put(`/batches/${batchCode}/daily-logs/quick-entry/`, payload),
  weeklyKpi: (batchCode) => client.get(`/batches/${batchCode}/kpi/weekly/`),
  growthCurves: (params) => client.get("/batches/growth-curves/", { params }),
  healthScore: () => client.get("/batches/health-score/"),
};

export const stockApi = {
  items: (farmId) => client.get(`/farms/${farmId}/stock-items/`),
  putItems: (farmId, items) => client.put(`/farms/${farmId}/stock-items/`, { items }),
  addItem: (farmId, payload) => client.post(`/farms/${farmId}/stock-items/`, payload),
  updateItem: (itemCode, payload) => client.patch(`/stock-items/${itemCode}/`, payload),
  compositions: (farmId) => client.get(`/farms/${farmId}/stock-compositions/`),
  addComposition: (farmId, payload) => client.post(`/farms/${farmId}/stock-compositions/`, payload),
  updateComposition: (id, payload) => client.patch(`/stock-compositions/${id}/`, payload),
  removeComposition: (id) => client.delete(`/stock-compositions/${id}/`),
  executeComposition: (id, payload) => client.post(`/stock-compositions/${id}/execute/`, payload),
  categories: (farmId) => client.get(`/farms/${farmId}/stock-categories/`),
  addCategory: (farmId, payload) => client.post(`/farms/${farmId}/stock-categories/`, payload),
  removeCategory: (categoryId) => client.delete(`/stock-categories/${categoryId}/`),
  // Excel import — update-or-create StockItem params by Article name (never deletes, no
  // movement/quantity change). `importTemplateUrl` is a plain download link (AllowAny).
  // `dryRun` returns the column mapping and what *would* change without writing anything —
  // the batch-creation screen previews that, then re-posts without the flag to commit.
  importXlsx: (farmId, file, { dryRun = false } = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (dryRun) fd.append("dry_run", "1");
    return client.post(`/farms/${farmId}/stock-items/import-xlsx/`, fd);
  },
  importTemplateUrl: `${API_URL}/stock-items/import-template.xlsx`,
  suppliers: (farmId) => client.get(`/farms/${farmId}/suppliers/`),
  addSupplier: (farmId, payload) => client.post(`/farms/${farmId}/suppliers/`, payload),
  updateSupplier: (id, payload) => client.put(`/suppliers/${id}/`, payload),
  removeSupplier: (id) => client.delete(`/suppliers/${id}/`),
  evolution: (farmId) => client.get(`/farms/${farmId}/stock-evolution/`),
  coverage: (itemCode, params) => client.get(`/stock-items/${itemCode}/coverage/`, { params }),
  movements: () => client.get("/stock-movements/"),
  addMovement: (payload) => client.post("/stock-movements/", payload),
  vaccinations: () => client.get("/vaccinations/"),
  addVaccination: (payload) => client.post("/vaccinations/", payload),
  lowCount: () => client.get("/stock-items/low-count/"),
};

export const maintenanceApi = {
  faults: (params) => client.get("/equipment-faults/", { params }),
  addFault: (payload) => client.post("/equipment-faults/", payload),
  resolveFault: (faultCode) => client.post(`/equipment-faults/${faultCode}/resolve/`),
  cases: (params) => client.get("/unusual-cases/", { params }),
  addCase: (payload) => client.post("/unusual-cases/", payload),
  resolveCase: (caseCode) => client.post(`/unusual-cases/${caseCode}/resolve/`),
};

export const financeApi = {
  summary: (range) => client.get("/finance/summary/", { params: { range } }),
  expenseCategories: (range) => client.get("/finance/expense-categories/", { params: { range } }),
  transactions: (page, type) => client.get("/finance/transactions/", { params: { page, type } }),
  expenses: () => client.get("/expenses/"),
  addExpense: (payload) => client.post("/expenses/", payload),
  sales: () => client.get("/sales/"),
  addSale: (payload) => client.post("/sales/", payload),
  purchaseOrders: (params) => client.get("/purchase-orders/", { params }),
  addPurchaseOrder: (payload) => client.post("/purchase-orders/", payload),
  receivePurchaseOrder: (orderCode, supplierBatchNumber) =>
    client.patch(`/purchase-orders/${orderCode}/`, { status: "RECEIVED", supplierBatchNumber: supplierBatchNumber || "" }),
  cancelPurchaseOrder: (orderCode) => client.patch(`/purchase-orders/${orderCode}/`, { status: "CANCELLED" }),
  pendingPayablesCount: () => client.get("/purchase-orders/pending-count/"),
  salesEvolution: (period) => client.get("/finance/sales-evolution/", { params: { period } }),
  purchasesEvolution: (period) => client.get("/finance/purchases-evolution/", { params: { period } }),
};

export const payrollApi = {
  workHours: (params) => client.get("/work-hours/", { params }),
  logHours: (payload) => client.post("/work-hours/", payload),
  salaryPayments: () => client.get("/salary-payments/"),
  calculateSalaries: (month, year) => client.post("/salary-payments/calculate/", { month, year }),
  markPaid: (id) => client.post(`/salary-payments/${id}/pay/`),
};

export const alertsApi = {
  rules: () => client.get("/alert-rules/"),
  addRule: (payload) => client.post("/alert-rules/", payload),
  list: (batchCode) => client.get("/alerts/", { params: batchCode ? { batch_code: batchCode } : {} }),
  unreadCount: () => client.get("/alerts/unread-count/"),
  markRead: (id) => client.post(`/alerts/${id}/mark-read/`),
  markAllRead: () => client.post("/alerts/mark-all-read/"),
  smsMessages: () => client.get("/sms-messages/"),
  notificationPreferences: () => client.get("/notification-preferences/"),
  setNotificationPreference: (payload) => client.post("/notification-preferences/", payload),
};

export const pushApi = {
  publicKey: () => client.get("/push-public-key/"),
  subscribe: (subscription) => client.post("/push-subscriptions/", subscription),
  unsubscribe: (endpoint) => client.delete("/push-subscriptions/", { data: { endpoint } }),
};

export const searchApi = {
  query: (q) => client.get("/search/", { params: { q } }),
};
