# CEX-DEX Arbitrage Bot — PRD

## Original Problem Statement (Indonesian)
1. Skrip BOT untuk trading arbitrage CEX-DEX.
2. CEX = Binance, DEX = Jupiter (Solana).
3. Tampilan sederhana, simpel, dan elegan.
4. Koin: BONK, ORCA, PYTH, JTO, RAY, WIF, SOL, JUP, RENDER, POPCAT, MEW, IO.
5. Paper trading dan live trading dengan harga realtime dari Binance & Jupiter.
6. Settings: modal trade, threshold %, slippage %.
7. Binance API key/secret + Phantom private key dimasukkan via UI Settings (terenkripsi).
8. Notifikasi Telegram tiap trade (modal, koin, profit).
9. Notifikasi saldo CEX & DEX (koin + USDT/USDC) tiap 15 menit ke Telegram.
10. Dashboard: Total Profit, Total Trade, Winrate, Live Opportunities.
11. Telegram bot token + chat ID via UI Settings.
12. Mode eksekusi: Auto atau Manual.
13. Screening real-time: harga CEX, DEX, spread, net profit setelah fee.
14. Trade history.
15. Tidak diblokir oleh CEX/DEX (digunakan endpoint publik).

## Architecture
- **Frontend**: React (CRA) + Tailwind + shadcn/ui (square corners, terminal aesthetic).
- **Backend**: FastAPI with async background tasks (price polling, auto-exec, telegram balance).
- **Database**: MongoDB (settings, trades).
- **Encryption**: Fernet (`FERNET_KEY` in backend/.env).
- **Price Sources**:
  - Binance: `https://data-api.binance.vision/api/v3/ticker/price` (per-symbol, no geo-block).
  - Jupiter: `https://lite-api.jup.ag/price/v3?ids=...`.
- **Telegram**: `https://api.telegram.org/bot<token>/sendMessage`.
- **Solana**: solders + solana RPC for Jupiter swap execution.

## Endpoints (`/api`)
- `GET /prices` — latest CEX/DEX prices per coin.
- `GET /opportunities` — sorted by net profit.
- `GET /stats` — total_profit, total_trades, winrate, live_opportunities, mode, auto_exec.
- `GET /trades?limit=N` — trade history.
- `GET /settings` — masked credentials + risk params.
- `POST /settings` — partial update; encrypts secrets.
- `POST /execute` — manual execute by opportunity_id (paper or live).
- `POST /test-telegram` — sends a test message.
- `GET /coins` — coin list.

## What's Implemented (2026-02-XX)
- Realtime polling (4s without WS, 15s as fallback when WS up) Binance + Jupiter for 12 coins.
- **WebSocket Binance** (`wss://data-stream.binance.vision`) for sub-second CEX updates with reconnect & exponential backoff.
- Opportunity calculation with fees (CEX 0.1% + DEX 0.25% + user slippage %), throttled to ~5 recompute/sec on WS.
- Auto-execution loop (30s throttle per coin) when toggled.
- **Risk caps**: `daily_loss_limit_usd` and `max_daily_trades` enforced per-trade in BOTH auto-exec and manual /api/execute.
- **Per-coin enable/disable** via `enabled_coins` setting. Filter in `compute_opportunities`.
- **Cumulative profit chart** (recharts) at `/api/profit-series` (most recent 200 trades).
- WS connectivity badge + daily PnL/trade count on dashboard top bar.
- Paper trade simulator records profit_usd into Mongo.
- Live trade leg: Binance market order via python-binance + Jupiter v1 swap via solders.
- Telegram notify on each trade + 15-min balance snapshot.
- Bloomberg-style dark terminal UI.
- Settings page for credentials (encrypted), risk params, mode toggles, coin universe selector.
- **Master ON/OFF toggle** (`bot_enabled`) in top bar — scanner keeps streaming prices while execution is paused (gates BOTH auto-exec and manual `/api/execute`).
- **Net profit in Telegram trade notifications** — `format_trade_msg` includes profit_usd, net_profit_pct, and lifetime totals (total_profit, total_trades, winrate).
- **Reset Stats** button in Settings — `POST /api/reset-stats` wipes all trade history and resets in-memory daily counters.
- **Enhanced 15-min Telegram balance snapshot** — now includes bot status header (ON/OFF, Paper/Live, Auto/Manual), today's PnL + trade count, lifetime stats, per-asset USD valuation (using state.prices), and grand total. New `POST /api/test-balance-telegram` endpoint + "Send Balance Now" button in Settings to preview on demand.
- **Daily Summary Telegram @ 00:00 WIB (UTC+7)** — background task `daily_summary_task` aggregates the previous WIB day (total P&L, trades, wins/losses, winrate, avg/trade, best & worst coin, full per-coin breakdown). De-dup via persisted `last_daily_summary_date` in Mongo so restarts don't double-send. Endpoints: `GET /api/daily-summary?date=YYYY-MM-DD` + `POST /api/test-daily-summary`. UI: **Send Daily Summary** button in Settings.
- **CSV export of trade history** — `GET /api/export-trades-csv` streams full history (ts, coin, mode, buy/sell side & price, modal, spread, profit, status, trigger, etc). UI: **Export Trades to CSV** button in Settings triggers browser download (`arb-trades-YYYYMMDD-HHMM.csv`).

## Backend Tests
- Iteration 1: 18/18 (initial endpoints).
- Iteration 2: 10/12 (P1/P2 - 2 bugs found).
- Iteration 3: 12/12 + 18/18 regression = **34/34** after fixes.
- Iteration 4: **10/10** — bot_enabled toggle, /api/execute gate, /api/reset-stats, telegram_balance_task + /api/test-balance-telegram + notifier formatters (`/app/backend/tests/test_bot_toggle_and_balance.py`).
- Iteration 5: **13/13** — daily summary aggregation, /api/daily-summary, /api/test-daily-summary, /api/export-trades-csv (`/app/backend/tests/test_daily_summary_and_csv.py`).

## Pending / Backlog
- P2: Bybit/OKX adapter as alternative CEX leg (for users blocked from Binance).
- P2: Multi-DEX support (Raydium / Orca direct).
- P2: Refactor server.py (now ~720 lines) — split routes / background tasks / balance helpers into separate modules.
- P2: Store `trades.ts` as BSON datetime instead of ISO string + add index (currently relies on lexicographic ISO ordering for daily summary aggregation).
- P2: True async streaming for CSV export (currently buffers in memory — fine until ~50k+ trades).

## Next Action Items
- User to `git pull` on Windows VPS → `cd frontend && yarn build` → restart NSSM services.
- Optional: Verify daily Telegram summary arrives at 00:00 WIB; verify CSV export downloads from VPS dashboard.
