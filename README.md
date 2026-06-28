# Arbitrage Terminal — CEX × DEX Bot

> Bloomberg-style terminal untuk arbitrage **Binance Spot (CEX)** × **Jupiter Aggregator (DEX, Solana)** dengan paper trading, live trading, dan notifikasi Telegram.

![Stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20React%20%2B%20MongoDB-00FF66?style=flat-square)
![Mode](https://img.shields.io/badge/modes-PAPER%20%7C%20LIVE-00D1FF?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-94A3B8?style=flat-square)

---

## ✨ Fitur Utama

- **Realtime Scanner** — WebSocket Binance (`data-stream.binance.vision`) untuk update sub-detik + REST polling Jupiter setiap 15s.
- **Arbitrage Detection** — 12 token Solana (BONK, ORCA, PYTH, JTO, RAY, WIF, SOL, JUP, RENDER, POPCAT, MEW, IO) dengan spread, net profit setelah fee, dan opportunity sorting.
- **Paper Trading** — simulasi penuh tanpa API key, profit/loss dicatat ke MongoDB.
- **Live Trading** — eksekusi paralel (pre-positioned balances). Binance leg via `python-binance`, Jupiter swap via `solders`.
- **Risk Caps** — `daily_loss_limit_usd` + `max_daily_trades`, di-enforce per-trade (auto & manual).
- **Telegram Notifikasi** — setiap trade + snapshot saldo CEX/DEX tiap 15 menit.
- **Dashboard** — Total Profit, Total Trade, Winrate, Live Opportunities, cumulative profit chart (recharts), trade history.
- **Encrypted Credentials** — API keys & private keys di-enkripsi Fernet sebelum disimpan di MongoDB.
- **Mode toggle** — PAPER/LIVE & AUTO/MANUAL dari header.

---

## 🏗️ Arsitektur

```
┌───────────────────────┐         ┌─────────────────┐
│  React (CRA)          │ ←REST→  │  FastAPI        │
│  - Dashboard          │         │  - /api/prices  │
│  - Settings           │         │  - /api/execute │
│  - Recharts           │         │  - WS task      │
└───────────────────────┘         │  - Auto-exec    │
                                  └────┬────────────┘
                                       │
                  ┌────────────────────┼────────────────────┐
                  ▼                    ▼                    ▼
        ┌──────────────────┐  ┌─────────────────┐  ┌────────────────┐
        │ Binance          │  │ Jupiter (Solana)│  │ MongoDB        │
        │ - data-stream WS │  │ - price/v3      │  │ - settings     │
        │ - api.binance.com│  │ - swap/v1       │  │ - trades       │
        │   (live order)   │  │                 │  │                │
        └──────────────────┘  └─────────────────┘  └────────────────┘
```

---

## 🚀 Quick Start (Local Dev)

### Prasyarat
- **Python 3.11+**
- **Node.js 20+** & **Yarn**
- **MongoDB Community** (local) atau **MongoDB Atlas** (cloud, free tier OK)

### 1. Clone & Setup
```bash
git clone https://github.com/<your-username>/<this-repo>.git
cd <this-repo>
```

### 2. Backend
```bash
cd backend
python -m venv venv
# Linux/Mac:
source venv/bin/activate
# Windows:
.\venv\Scripts\activate

pip install -r requirements.txt

# Copy env template & isi nilai
cp env.example.txt .env
# Edit .env:
# - MONGO_URL (default mongodb://localhost:27017 untuk local)
# - FERNET_KEY (generate sekali, simpan di password manager)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Copy output ke FERNET_KEY di .env

# Jalankan backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Frontend
```bash
cd ../frontend
yarn install
cp env.example.txt .env
# Edit .env -> REACT_APP_BACKEND_URL=http://localhost:8001

yarn start          # dev mode (port 3000)
# atau
yarn build          # produksi
```

### 4. Akses
- Frontend: http://localhost:3000
- Backend docs: http://localhost:8001/docs

---

## 🪟 Deploy ke Windows VPS (Singapore)

Khusus untuk pengguna VPS Windows (Digitalku, dll) di region yang **tidak diblokir Binance** (Singapore, Tokyo, Frankfurt).

### Lihat panduan lengkap: [`scripts/setup-windows-vps.md`](scripts/setup-windows-vps.md)

Ringkasan:
1. Install Python 3.11, Node 20, Yarn, MongoDB Community, Git
2. `git clone` repo ini
3. Copy `.env.example` → `.env`, isi values
4. Install dependencies (backend pip install, frontend yarn install)
5. Build frontend: `yarn build`
6. Jalankan dengan **NSSM** sebagai Windows service supaya auto-restart saat reboot
7. Helper scripts tersedia di [`scripts/`](scripts/):
   - `start-backend.bat` — jalankan FastAPI
   - `start-frontend.bat` — serve frontend production build
   - `install-services.bat` — register sebagai Windows service via NSSM

---

## 🔐 Konfigurasi Keys (Settings UI)

Semua key di-input via UI Settings, **terenkripsi Fernet** sebelum disimpan di MongoDB.

| Field | Sumber | Wajib untuk |
|---|---|---|
| Binance API Key + Secret | binance.com → API Management | Live trading |
| Phantom Private Key (Base58) | Phantom Wallet → Settings → Show Private Key | Live DEX swap |
| Telegram Bot Token | [@BotFather](https://t.me/BotFather) → `/newbot` | Notifikasi |
| Telegram Chat ID | [@userinfobot](https://t.me/userinfobot) → `/start` | Notifikasi |

**Untuk paper mode: tidak perlu satupun.**

---

## ⚙️ Parameter Trading

| Parameter | Default | Penjelasan |
|---|---|---|
| `trade_modal_usd` | 100 | Modal per trade dalam USD |
| `threshold_pct` | 0.5 | Net profit % minimum agar opportunity dianggap actionable |
| `slippage_pct` | 0.3 | Slippage DEX yang dihitung ke total fee |
| `enabled_coins` | semua 12 | Koin yang di-scan |
| `daily_loss_limit_usd` | 0 (off) | Halt auto-exec saat daily PnL ≤ -limit |
| `max_daily_trades` | 0 (off) | Halt auto-exec setelah N trade |

**Fee yang sudah dihitung otomatis:**
- Binance taker: **0.10%**
- Jupiter swap rata-rata: **0.25%**
- User slippage: dari setting

---

## 📡 API Endpoints

| Method | Path | Deskripsi |
|---|---|---|
| GET | `/api/` | Service health |
| GET | `/api/prices` | Harga real-time CEX + DEX |
| GET | `/api/opportunities` | Opportunity terurut |
| GET | `/api/stats` | Stats agregat + WS status |
| GET | `/api/trades` | Trade history |
| GET | `/api/profit-series` | Cumulative profit time series |
| GET | `/api/settings` | Settings (credentials masked) |
| POST | `/api/settings` | Update partial settings |
| POST | `/api/execute` | Eksekusi manual (`opportunity_id`) |
| POST | `/api/test-telegram` | Kirim test notifikasi |
| GET | `/api/coins` | Daftar koin |

Detail Swagger: `http://<backend>/docs`

---

## 🧪 Testing

Backend test coverage: **34/34 pass** (lihat `test_reports/iteration_*.json`).

```bash
cd backend
python -m pytest tests/ -v
```

---

## ⚠️ Disclaimer

- **Bukan financial advice**. Cryptocurrency trading punya risiko kehilangan modal.
- **Paper mode dulu** sebelum live — validasi strategi minimal 1 minggu.
- **Live mode hanya jalan di region yang tidak diblokir Binance** (Singapore, Tokyo, EU). Region Indonesia/restricted akan dapat HTTP 451.
- **Pre-position balance**: live mode eksekusi paralel, saldo koin & USDT/USDC harus sudah ada di Binance + Phantom sebelum start.
- **Akun & funds adalah tanggung jawab Anda**. Author tidak bertanggung jawab atas loss.

---

## 📜 License

MIT — bebas pakai, modifikasi, distribusi untuk tujuan apapun.

---

## 🤝 Built With

Built dengan ❤️ on [Emergent](https://emergent.sh) — agentic full-stack app builder.
