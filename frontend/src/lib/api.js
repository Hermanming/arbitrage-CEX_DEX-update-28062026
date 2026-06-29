import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const http = axios.create({ baseURL: API, timeout: 15000 });

export const api = {
  prices: () => http.get("/prices").then((r) => r.data),
  opportunities: () => http.get("/opportunities").then((r) => r.data),
  stats: () => http.get("/stats").then((r) => r.data),
  trades: () => http.get("/trades").then((r) => r.data),
  profitSeries: () => http.get("/profit-series").then((r) => r.data),
  settings: () => http.get("/settings").then((r) => r.data),
  saveSettings: (body) => http.post("/settings", body).then((r) => r.data),
  execute: (opportunity_id) =>
    http.post("/execute", { opportunity_id }).then((r) => r.data),
  testTelegram: () => http.post("/test-telegram").then((r) => r.data),
  testBalanceTelegram: () => http.post("/test-balance-telegram").then((r) => r.data),
  testDailySummary: (date) =>
    http.post("/test-daily-summary", null, { params: date ? { date } : {} }).then((r) => r.data),
  dailySummary: (date) =>
    http.get("/daily-summary", { params: date ? { date } : {} }).then((r) => r.data),
  exportTradesCsvUrl: () => `${API}/export-trades-csv`,
  opportunityLogStats: () => http.get("/opportunity-log-stats").then((r) => r.data),
  clearOpportunityLog: () => http.post("/clear-opportunity-log").then((r) => r.data),
  backtestStrategies: (configs, from_date, to_date) =>
    http.post("/backtest-strategies", { configs, from_date, to_date }).then((r) => r.data),
  inventoryDrift: () => http.get("/inventory-drift").then((r) => r.data),
  resetInventoryBaseline: () => http.post("/inventory-baseline/reset").then((r) => r.data),
  resetStats: () => http.post("/reset-stats").then((r) => r.data),
  coins: () => http.get("/coins").then((r) => r.data),
};
