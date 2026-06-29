# VPS Production Snapshot

## 📍 Current VPS State (USER'S LIVE PRODUCTION)

**Location:** Windows VPS Singapore (NSSM-managed services)
**Last Deploy:** Today (Feb 28, 2026) ~13:52 WIB / 06:52 UTC
**Git commit on VPS:** `f9929fe` (pulled from `fa8dd76..f9929fe`)
**Mode running:** PAPER trading, AUTO execution, ON
**Services:** `ArbitrageBackend` + `ArbitrageFrontend` via NSSM

## ✅ Features ACTIVE on VPS (commit f9929fe)

1. **Real-time price stream** — Binance WS (`data-stream.binance.vision`) + Jupiter API for 12 coins (BONK, ORCA, PYTH, JTO, RAY, WIF, SOL, JUP, RENDER, POPCAT, MEW, IO)
2. **Paper trading simulator** — records profit_usd to MongoDB Atlas
3. **Live trading capability** — Binance market order (python-binance) + Jupiter v1 swap (solders) [credentials must be set]
4. **Bloomberg-style dark terminal UI** — Shadcn + Recharts
5. **Settings page** — encrypted credentials (Fernet), risk params, mode toggles, coin universe
6. **Master ON/OFF toggle** (`bot_enabled`) — top bar, gates execution while scanner runs
7. **Net profit in Telegram trade notifications** — `format_trade_msg` includes profit_usd + lifetime totals
8. **Reset Stats button** — `POST /api/reset-stats` wipes trade history
9. **15-min Telegram Balance Snapshot** — `telegram_balance_task` background loop + `POST /api/test-balance-telegram`, "Send Balance Now" button
10. **Daily Summary @ 00:00 WIB** — `daily_summary_task` background loop, persisted de-dup, "Send Daily Summary" button
11. **CSV Export trades** — `GET /api/export-trades-csv`, "Export Trades to CSV" button

## ❌ Features in Emergent Workspace BUT NOT YET ON VPS

12. **Strategy Backtest** (`/backtest` page) — Implemented Feb 28 ~15:00 WIB (commits `6eee828`, `eae720b`, `644de6a`)
    - Background `opportunity_logger_task` (logs every opp to `db.opportunity_log`, TTL 7d)
    - `GET /api/opportunity-log-stats`, `POST /api/clear-opportunity-log`, `POST /api/backtest-strategies`
    - New page with 3 default presets + side-by-side comparison + winner ranking
    - New nav link "BACKTEST" in top bar (orange)
    - **Status: USER CHOSE NOT TO DEPLOY YET** — wants to test paper trading first with current settings

## 🎯 GOING-FORWARD DIRECTIVE

**User's instruction (28 Feb 2026):**
> *"Jika nanti ada perubahan settingan BOT, nanti pakai settingan yang update terakhir ini ya"*

**Interpretation:** Any future code changes / new features must be ADDITIVE to commit `f9929fe` (the VPS baseline). Do NOT introduce breaking changes that would conflict with what's currently running on the VPS.

**Practical rules for next agent:**
- Treat commit `f9929fe` as the production baseline
- The Backtest feature in Emergent workspace exists as an **opt-in upgrade** the user can pull later when ready
- When user reports a bug or asks for fix, FIRST verify it exists in the f9929fe codebase (which is what they're actually running)
- All settings (threshold, slippage, modal, enabled coins, telegram creds, encrypted Binance/Phantom keys) live in MongoDB Atlas — they persist across code deploys
- When the user does eventually pull Backtest (or any new feature), they will: `git pull` → `yarn build` (if frontend changed) → `nssm restart ArbitrageBackend` + `nssm restart ArbitrageFrontend`

## 🔑 VPS Infrastructure Notes

- **Python:** 3.11.9 (downgraded from 3.14 due to solders/solana compile fail)
- **Node:** 20.x
- **DB:** MongoDB Atlas Free M0 (Singapore region)
- **Service Manager:** NSSM (Non-Sucking Service Manager)
- **Deploy flow:** GitHub repo `Hermanming/arbitrage-CEX_DEX-update-28062026` → `git pull` → `yarn build` → `nssm restart`
- **Local app path:** `C:\arbitrage-bot`

## 📊 User's Current Operating Strategy

- **Mode:** PAPER (no real money at risk yet)
- **Goal:** Collect 24h+ of data to evaluate threshold/slippage settings
- **Threshold/Slippage:** Using the "previous settings" (whatever was active before this snapshot)
- **Next decision point:** After 24h paper run, user will analyze Daily Summary results to decide if/when to go LIVE
