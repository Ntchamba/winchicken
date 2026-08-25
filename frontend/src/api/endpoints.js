import client from "./client";

export const farmApi = {
  exists: () => client.get("/farm/exists/"),
  create: (payload) => client.post("/farm/create/", payload),
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
};

export const onboardingApi = {
  submit: (payload) => client.post("/protocols/onboarding/", payload),
};

export const batchesApi = {
  list: (houseCode) => client.get("/batches/", { params: houseCode ? { house_code: houseCode } : {} }),
  create: (payload) => client.post("/batches/", payload),
  close: (batchCode) => client.patch(`/batches/${batchCode}/close/`),
  dailyLogs: (batchCode) => client.get(`/batches/${batchCode}/daily-logs/`),
  addDailyLog: (batchCode, payload) => client.post(`/batches/${batchCode}/daily-logs/`, payload),
  weeklyKpi: (batchCode) => client.get(`/batches/${batchCode}/kpi/weekly/`),
};

export const stockApi = {
  items: (farmId) => client.get(`/farms/${farmId}/stock-items/`),
  putItems: (farmId, items) => client.put(`/farms/${farmId}/stock-items/`, { items }),
  movements: () => client.get("/stock-movements/"),
  addMovement: (payload) => client.post("/stock-movements/", payload),
  vaccinations: () => client.get("/vaccinations/"),
  addVaccination: (payload) => client.post("/vaccinations/", payload),
};

export const maintenanceApi = {
  faults: () => client.get("/equipment-faults/"),
  addFault: (payload) => client.post("/equipment-faults/", payload),
  cases: () => client.get("/unusual-cases/"),
  addCase: (payload) => client.post("/unusual-cases/", payload),
};

export const financeApi = {
  summary: (range) => client.get("/finance/summary/", { params: { range } }),
  expenseCategories: (range) => client.get("/finance/expense-categories/", { params: { range } }),
  transactions: (page, type) => client.get("/finance/transactions/", { params: { page, type } }),
  expenses: () => client.get("/expenses/"),
  addExpense: (payload) => client.post("/expenses/", payload),
  sales: () => client.get("/sales/"),
  addSale: (payload) => client.post("/sales/", payload),
  purchaseOrders: () => client.get("/purchase-orders/"),
  addPurchaseOrder: (payload) => client.post("/purchase-orders/", payload),
  receivePurchaseOrder: (orderCode) => client.patch(`/purchase-orders/${orderCode}/`, { status: "RECEIVED" }),
};

export const alertsApi = {
  rules: () => client.get("/alert-rules/"),
  addRule: (payload) => client.post("/alert-rules/", payload),
  list: (batchCode) => client.get("/alerts/", { params: batchCode ? { batch_code: batchCode } : {} }),
  smsMessages: () => client.get("/sms-messages/"),
  notificationPreferences: () => client.get("/notification-preferences/"),
  setNotificationPreference: (payload) => client.post("/notification-preferences/", payload),
};
