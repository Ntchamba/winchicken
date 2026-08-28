import client from "./client";

export const farmApi = {
  exists: () => client.get("/farm/exists/"),
  create: (payload) => client.post("/farm/create/", payload),
  reset: (password) => client.post("/farm/reset/", { password }),
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
  milestones: (houseCode) => client.get(`/houses/${houseCode}/milestones/`),
};

export const tasksApi = {
  mine: () => client.get("/tasks/mine/"),
  upcoming: () => client.get("/tasks/upcoming/"),
  assignableUsers: () => client.get("/tasks/assignable-users/"),
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
  categories: (farmId) => client.get(`/farms/${farmId}/stock-categories/`),
  addCategory: (farmId, payload) => client.post(`/farms/${farmId}/stock-categories/`, payload),
  removeCategory: (categoryId) => client.delete(`/stock-categories/${categoryId}/`),
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

export const searchApi = {
  query: (q) => client.get("/search/", { params: { q } }),
};
