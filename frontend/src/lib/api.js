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
  coins: () => http.get("/coins").then((r) => r.data),
};
