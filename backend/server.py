"""FastAPI server for CEX-DEX Arbitrage Bot."""
import asyncio
import csv
import io
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from constants import COIN_LIST, TOKENS
from constants import BINANCE_TAKER_FEE_PCT, JUPITER_AVG_FEE_PCT
from crypto_utils import encrypt, decrypt, mask
from engine import (
    binance_ws_task,
    execute_trade_live,
    execute_trade_simulation,
    price_polling_task,
    state,
)
from notifier import (
    format_balance_msg,
    format_daily_summary_msg,
    format_drift_alert_msg,
    format_partial_trade_alert_msg,
    format_trade_msg,
    send_telegram,
)

WIB = ZoneInfo("Asia/Jakarta")  # UTC+7

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("server")

mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]

SETTINGS_ID = "bot_settings"


# --------------- Models ----------------
class SettingsIn(BaseModel):
    binance_api_key: Optional[str] = None
    binance_api_secret: Optional[str] = None
    phantom_private_key: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    paper_mode: Optional[bool] = None
    auto_exec: Optional[bool] = None
    trade_modal_usd: Optional[float] = None
    threshold_pct: Optional[float] = None
    slippage_pct: Optional[float] = None
    enabled_coins: Optional[list[str]] = None
    daily_loss_limit_usd: Optional[float] = None
    max_daily_trades: Optional[int] = None
    bot_enabled: Optional[bool] = None
    auto_reverse_on_partial: Optional[bool] = None
    drift_alert_pct: Optional[float] = None


class ExecuteOpportunityIn(BaseModel):
    opportunity_id: str


# --------------- DB helpers ----------------
async def load_settings_into_state():
    doc = await db.settings.find_one({"_id": SETTINGS_ID})
    if not doc:
        return
    state.settings.update({
        "paper_mode": doc.get("paper_mode", True),
        "auto_exec": doc.get("auto_exec", False),
        "trade_modal_usd": doc.get("trade_modal_usd", 100.0),
        "threshold_pct": doc.get("threshold_pct", 0.5),
        "slippage_pct": doc.get("slippage_pct", 0.3),
        "enabled_coins": doc["enabled_coins"] if "enabled_coins" in doc and doc["enabled_coins"] is not None else list(COIN_LIST),
        "daily_loss_limit_usd": doc.get("daily_loss_limit_usd", 0.0),
        "max_daily_trades": doc.get("max_daily_trades", 0),
        "bot_enabled": doc.get("bot_enabled", True),
        "auto_reverse_on_partial": doc.get("auto_reverse_on_partial", False),
        "drift_alert_pct": float(doc.get("drift_alert_pct") or 5.0),
    })
    state.creds = {
        "binance_api_key": doc.get("binance_api_key", ""),
        "binance_api_secret": doc.get("binance_api_secret", ""),
        "phantom_private_key": doc.get("phantom_private_key", ""),
        "telegram_bot_token": doc.get("telegram_bot_token", ""),
        "telegram_chat_id": doc.get("telegram_chat_id", ""),
    }
    # Persisted daily-summary de-dup marker (survives restart)
    state.last_daily_summary_date = doc.get("last_daily_summary_date", "")
    # Persisted inventory baseline (survives restart)
    state.inventory_baseline = doc.get("inventory_baseline", {}) or {}


def _decrypt_cred(name: str) -> str:
    enc = state.creds.get(name, "")
    if not enc:
        return ""
    try:
        return decrypt(enc)
    except Exception:
        return ""


# --------------- Background tasks ----------------
async def auto_exec_task():
    """When auto exec is on, fire trades for opportunities above threshold."""
    last_fired = {}  # coin -> timestamp, to throttle
    while True:
        try:
            if state.settings.get("auto_exec") and state.settings.get("bot_enabled", True):
                # Reset daily counters at UTC date change
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if state.daily_date != today:
                    state.daily_date = today
                    state.daily_pnl = 0.0
                    state.daily_trades = 0

                threshold = state.settings.get("threshold_pct", 0.5)
                paper = state.settings.get("paper_mode", True)
                for opp in list(state.opportunities):
                    # Re-read caps each opp so they're respected per-trade
                    loss_cap = float(state.settings.get("daily_loss_limit_usd") or 0)
                    trade_cap = int(state.settings.get("max_daily_trades") or 0)
                    if loss_cap > 0 and state.daily_pnl <= -abs(loss_cap):
                        break
                    if trade_cap > 0 and state.daily_trades >= trade_cap:
                        break
                    if opp["net_profit_pct"] < threshold:
                        continue
                    coin = opp["coin"]
                    now = time.time()
                    if now - last_fired.get(coin, 0) < 30:  # throttle 30s per coin
                        continue
                    last_fired[coin] = now
                    try:
                        if paper:
                            trade = await execute_trade_simulation(opp)
                        else:
                            modal_now = float(state.settings.get("trade_modal_usd") or 0)
                            ok, reason = await _preflight_balance_check(opp, modal_now)
                            if not ok:
                                logger.warning(f"auto-exec preflight skip {coin}: {reason}")
                                continue
                            trade = await execute_trade_live(
                                opp,
                                _decrypt_cred("binance_api_key"),
                                _decrypt_cred("binance_api_secret"),
                                _decrypt_cred("phantom_private_key"),
                            )
                        trade["trigger"] = "auto"
                        await db.trades.insert_one({**trade, "_id": trade["id"]})
                        await _notify_trade(trade)
                        # Alert if partial/reversed (live mode only)
                        if trade.get("status") in ("partial", "reversed"):
                            await _notify_partial(trade)
                        # update daily counters
                        state.daily_trades += 1
                        state.daily_pnl += float(trade.get("profit_usd") or 0)
                    except Exception as e:
                        logger.exception(f"auto exec error: {e}")
        except Exception as e:
            logger.exception(f"auto_exec_task: {e}")
        await asyncio.sleep(3.0)


async def opportunity_logger_task():
    """Persist live opportunities (spread > 0) to a TTL-bounded collection for backtesting.

    Throttle: 30s minimum per coin. TTL: 7 days. Skips opportunities with non-positive spread."""
    # Ensure TTL index (auto-deletes docs after 7 days)
    try:
        await db.opportunity_log.create_index(
            "ts", expireAfterSeconds=7 * 86400
        )
        await db.opportunity_log.create_index([("coin", 1), ("ts", 1)])
    except Exception as e:
        logger.warning(f"opportunity_log index: {e}")

    while True:
        await asyncio.sleep(5)
        try:
            now_epoch = time.time()
            for opp in list(state.opportunities):
                if (opp.get("spread_pct") or 0) <= 0:
                    continue
                coin = opp["coin"]
                if now_epoch - state.last_opp_log_ts.get(coin, 0) < 30:
                    continue
                state.last_opp_log_ts[coin] = now_epoch
                doc = {
                    "coin": coin,
                    "ts": datetime.now(timezone.utc),  # BSON datetime for TTL
                    "cex_price": float(opp["cex_price"]),
                    "dex_price": float(opp["dex_price"]),
                    "buy_side": opp["buy_side"],
                    "sell_side": opp["sell_side"],
                    "spread_pct": float(opp["spread_pct"]),
                    "modal_usd": float(state.settings.get("trade_modal_usd", 100.0)),
                }
                try:
                    await db.opportunity_log.insert_one(doc)
                except Exception:
                    pass
        except Exception as e:
            logger.exception(f"opportunity_logger_task: {e}")


async def _preflight_balance_check(opp: dict, modal: float) -> tuple[bool, str]:
    """Verify we have enough balance on both CEX and DEX to execute the trade.

    Returns (ok, reason). If ok=False, the caller should skip execution.
    Skips check if Binance API key or Phantom private key are not configured.
    """
    coin = opp["coin"]
    buy_side = opp["buy_side"]  # "CEX" or "DEX"
    cex_price = float(opp.get("cex_price") or 0)
    dex_price = float(opp.get("dex_price") or 0)
    if cex_price <= 0 or dex_price <= 0:
        return True, ""  # Cannot validate without prices; let downstream decide

    cex_bal = await _fetch_binance_balances()
    dex_bal = await _fetch_phantom_balances()
    if not cex_bal and not dex_bal:
        # API keys missing or balance fetch failed → don't block (preserves prior behavior)
        return True, "preflight-skipped"

    # Required amounts on each side (USD-equivalent semantics):
    if buy_side == "CEX":
        # CEX BUY: need USDT >= modal
        usdt_have = float(cex_bal.get("USDT") or 0)
        if usdt_have + 0.01 < modal:
            return False, f"insufficient USDT on Binance: have ${usdt_have:.2f}, need ${modal:.2f}"
        # DEX SELL: need coin >= modal/dex_price
        coin_needed = modal / dex_price
        coin_have = float(dex_bal.get(coin) or 0)
        if coin_have * 0.999 < coin_needed:
            return False, f"insufficient {coin} on Phantom: have {coin_have:.6f}, need {coin_needed:.6f}"
    else:  # buy_side == "DEX"
        # DEX BUY: need USDC >= modal
        usdc_have = float(dex_bal.get("USDC") or 0)
        if usdc_have + 0.01 < modal:
            return False, f"insufficient USDC on Phantom: have ${usdc_have:.2f}, need ${modal:.2f}"
        # CEX SELL: need coin >= modal/cex_price
        coin_needed = modal / cex_price
        coin_have = float(cex_bal.get(coin) or 0)
        if coin_have * 0.999 < coin_needed:
            return False, f"insufficient {coin} on Binance: have {coin_have:.6f}, need {coin_needed:.6f}"

    # Gas check: need at least 0.005 SOL on Phantom for swap fees
    sol_have = float(dex_bal.get("SOL") or 0)
    if sol_have < 0.005 and coin != "SOL":
        return False, f"insufficient SOL gas on Phantom: have {sol_have:.4f}, need >= 0.005"

    return True, ""


async def _compute_inventory_snapshot() -> dict:
    """Return current inventory per coin: {coin: {cex_qty, dex_qty, total_qty, ts}}."""
    cex_bal = await _fetch_binance_balances()
    dex_bal = await _fetch_phantom_balances()
    snapshot = {}
    coins_seen = set(cex_bal.keys()) | set(dex_bal.keys())
    coins_seen.discard("USDT")
    coins_seen.discard("USDC")
    for coin in coins_seen:
        cex_qty = float(cex_bal.get(coin) or 0)
        dex_qty = float(dex_bal.get(coin) or 0)
        snapshot[coin] = {
            "cex_qty": round(cex_qty, 6),
            "dex_qty": round(dex_qty, 6),
            "total_qty": round(cex_qty + dex_qty, 6),
        }
    return snapshot


def _compute_drift(coin: str, current: dict, baseline: dict) -> dict:
    """Compute drift metrics for one coin.

    Returns dict with:
      - drift_pct: % change in total inventory from baseline (signed)
      - imbalance_pct: % imbalance between CEX and DEX sides (positive)
      - baseline_total, current_total
    """
    b_total = float(baseline.get("total_qty") or 0)
    c_total = float(current.get("total_qty") or 0)
    drift_pct = ((c_total - b_total) / b_total * 100.0) if b_total > 0 else 0.0
    c_cex = float(current.get("cex_qty") or 0)
    c_dex = float(current.get("dex_qty") or 0)
    side_sum = c_cex + c_dex
    imbalance_pct = (abs(c_cex - c_dex) / side_sum * 100.0) if side_sum > 0 else 0.0
    return {
        "drift_pct": round(drift_pct, 4),
        "imbalance_pct": round(imbalance_pct, 4),
        "baseline_total": b_total,
        "current_total": c_total,
        "current_cex": c_cex,
        "current_dex": c_dex,
    }


async def inventory_drift_task():
    """Every 5 minutes, compute inventory drift per coin and alert Telegram if exceeded.

    Throttle: 1 alert per coin per hour to avoid spam.
    Skips coins without a baseline (user must call /api/inventory-baseline/reset once).
    """
    while True:
        await asyncio.sleep(300)  # 5 min
        try:
            if not state.inventory_baseline:
                continue
            tg_token = _decrypt_cred("telegram_bot_token")
            tg_chat = _decrypt_cred("telegram_chat_id")
            drift_threshold = float(state.settings.get("drift_alert_pct") or 5.0)
            imbalance_threshold = 40.0
            snapshot = await _compute_inventory_snapshot()
            if not snapshot:
                continue
            now_epoch = time.time()
            for coin, current in snapshot.items():
                baseline = state.inventory_baseline.get(coin)
                if not baseline:
                    continue
                m = _compute_drift(coin, current, baseline)
                trigger_drift = abs(m["drift_pct"]) > drift_threshold
                trigger_imb = m["imbalance_pct"] > imbalance_threshold and m["current_total"] > 0
                if not (trigger_drift or trigger_imb):
                    continue
                if now_epoch - state.last_drift_alert_ts.get(coin, 0) < 3600:
                    continue  # throttle 1h per coin
                state.last_drift_alert_ts[coin] = now_epoch
                if tg_token and tg_chat:
                    msg = format_drift_alert_msg(coin, m, drift_threshold, imbalance_threshold)
                    await send_telegram(tg_token, tg_chat, msg)
                logger.warning(f"Inventory drift alert: {coin} drift={m['drift_pct']}% imb={m['imbalance_pct']}%")
        except Exception as e:
            logger.exception(f"inventory_drift_task: {e}")


async def telegram_balance_task():
    """Every 15 minutes, send Binance + Phantom balances + bot status to Telegram."""
    while True:
        await asyncio.sleep(60)
        try:
            tg_token = _decrypt_cred("telegram_bot_token")
            tg_chat = _decrypt_cred("telegram_chat_id")
            if not tg_token or not tg_chat:
                continue
            now = time.time()
            if now - state.last_balance_notif < 900:  # 15 min
                continue
            state.last_balance_notif = now

            cex_bal = await _fetch_binance_balances()
            dex_bal = await _fetch_phantom_balances()

            # Build status snapshot
            total_profit = 0.0
            total_trades = 0
            try:
                cur = db.trades.find({}, {"profit_usd": 1})
                async for t in cur:
                    total_trades += 1
                    total_profit += float(t.get("profit_usd") or 0)
            except Exception:
                pass
            status_snapshot = {
                "paper_mode": state.settings.get("paper_mode", True),
                "auto_exec": state.settings.get("auto_exec", False),
                "bot_enabled": state.settings.get("bot_enabled", True),
                "daily_pnl": state.daily_pnl,
                "daily_trades": state.daily_trades,
                "total_profit": round(total_profit, 4),
                "total_trades": total_trades,
            }
            msg = format_balance_msg(cex_bal, dex_bal, prices=state.prices, status=status_snapshot)
            await send_telegram(tg_token, tg_chat, msg)
        except Exception as e:
            logger.exception(f"balance task: {e}")


async def _fetch_binance_balances() -> dict[str, float]:
    api_key = _decrypt_cred("binance_api_key")
    api_secret = _decrypt_cred("binance_api_secret")
    if not api_key or not api_secret:
        return {}
    try:
        from binance.client import Client
        client = Client(api_key, api_secret)
        info = client.get_account()
        balances = {}
        relevant = set(COIN_LIST) | {"USDT"}
        for b in info.get("balances", []):
            asset = b["asset"]
            if asset in relevant:
                total = float(b["free"]) + float(b["locked"])
                if total > 0:
                    balances[asset] = total
        return balances
    except Exception as e:
        logger.warning(f"binance balance fail: {e}")
        return {}


async def _fetch_phantom_balances() -> dict[str, float]:
    pk = _decrypt_cred("phantom_private_key")
    if not pk:
        return {}
    try:
        from solders.keypair import Keypair
        from solana.rpc.async_api import AsyncClient
        from solders.pubkey import Pubkey
        import httpx
        kp = Keypair.from_base58_string(pk)
        owner = str(kp.pubkey())
        rpc = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
        balances = {}

        # SOL balance
        sol_client = AsyncClient(rpc)
        try:
            resp = await sol_client.get_balance(kp.pubkey())
            balances["SOL"] = (resp.value or 0) / 1e9
        finally:
            await sol_client.close()

        # SPL tokens via RPC
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(rpc, json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    owner,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed"},
                ],
            })
            data = r.json().get("result", {}).get("value", [])
            mint_to_coin = {info[1]: c for c, info in TOKENS.items()}
            mint_to_coin["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"] = "USDC"
            for acc in data:
                pinfo = acc["account"]["data"]["parsed"]["info"]
                mint = pinfo["mint"]
                amt = float(pinfo["tokenAmount"]["uiAmount"] or 0)
                if amt > 0 and mint in mint_to_coin:
                    coin = mint_to_coin[mint]
                    balances[coin] = balances.get(coin, 0) + amt
        return balances
    except Exception as e:
        logger.warning(f"phantom balance fail: {e}")
        return {}


async def _compute_daily_summary(target_wib_date: Optional[str] = None) -> dict:
    """Aggregate trades for a single WIB day.

    target_wib_date: 'YYYY-MM-DD'. Defaults to *yesterday* in WIB (the day that just ended at 00:00 WIB).
    """
    now_wib = datetime.now(WIB)
    if target_wib_date:
        day_start_wib = datetime.strptime(target_wib_date, "%Y-%m-%d").replace(tzinfo=WIB)
    else:
        # Day that just ended = yesterday (WIB)
        today_wib = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
        day_start_wib = today_wib - timedelta(days=1)
    day_end_wib = day_start_wib + timedelta(days=1)
    start_utc_iso = day_start_wib.astimezone(timezone.utc).isoformat()
    end_utc_iso = day_end_wib.astimezone(timezone.utc).isoformat()

    total_profit = 0.0
    wins = 0
    losses = 0
    total_trades = 0
    per_coin: dict[str, dict] = {}

    cur = db.trades.find(
        {"ts": {"$gte": start_utc_iso, "$lt": end_utc_iso}},
        {"coin": 1, "profit_usd": 1},
    )
    async for t in cur:
        total_trades += 1
        p = float(t.get("profit_usd") or 0)
        total_profit += p
        if p > 0:
            wins += 1
        elif p < 0:
            losses += 1
        coin = t.get("coin") or "?"
        rec = per_coin.setdefault(coin, {"coin": coin, "profit": 0.0, "trades": 0})
        rec["profit"] += p
        rec["trades"] += 1

    winrate = (wins / total_trades * 100.0) if total_trades else 0.0
    best = max(per_coin.values(), key=lambda x: x["profit"], default=None)
    worst = min(per_coin.values(), key=lambda x: x["profit"], default=None)

    return {
        "day_label": day_start_wib.strftime("%Y-%m-%d (%a)"),
        "wib_date": day_start_wib.strftime("%Y-%m-%d"),
        "total_profit": round(total_profit, 4),
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "winrate": round(winrate, 2),
        "best_coin": (
            {"coin": best["coin"], "profit": round(best["profit"], 4), "trades": best["trades"]}
            if best
            else {}
        ),
        "worst_coin": (
            {"coin": worst["coin"], "profit": round(worst["profit"], 4), "trades": worst["trades"]}
            if worst
            else {}
        ),
        "per_coin": [
            {"coin": v["coin"], "profit": round(v["profit"], 4), "trades": v["trades"]}
            for v in sorted(per_coin.values(), key=lambda x: x["profit"], reverse=True)
        ],
    }


async def daily_summary_task():
    """At 00:00 WIB (UTC+7) every day, send the previous-day summary to Telegram once."""
    while True:
        await asyncio.sleep(30)
        try:
            now_wib = datetime.now(WIB)
            # Fire shortly after midnight WIB; guard with state.last_daily_summary_date
            wib_today_str = now_wib.strftime("%Y-%m-%d")
            if not (now_wib.hour == 0 and now_wib.minute < 10):
                continue
            if state.last_daily_summary_date == wib_today_str:
                continue
            tg_token = _decrypt_cred("telegram_bot_token")
            tg_chat = _decrypt_cred("telegram_chat_id")
            if not tg_token or not tg_chat:
                # No telegram configured — still mark date so we don't retry every 30s today
                state.last_daily_summary_date = wib_today_str
                continue

            summary = await _compute_daily_summary()  # defaults to yesterday WIB
            msg = format_daily_summary_msg(summary)
            sent = await send_telegram(tg_token, tg_chat, msg)
            if sent:
                state.last_daily_summary_date = wib_today_str
                # Persist to Mongo so a restart shortly after midnight WIB doesn't re-send
                try:
                    await db.settings.update_one(
                        {"_id": SETTINGS_ID},
                        {"$set": {"last_daily_summary_date": wib_today_str}},
                        upsert=True,
                    )
                except Exception:
                    pass
                logger.info(f"Daily summary sent for {summary['wib_date']}")
        except Exception as e:
            logger.exception(f"daily_summary_task: {e}")


async def _notify_trade(trade: dict):
    tg_token = _decrypt_cred("telegram_bot_token")
    tg_chat = _decrypt_cred("telegram_chat_id")
    if not tg_token or not tg_chat:
        return
    try:
        # Aggregate lifetime totals for the message
        total_profit = 0.0
        total_trades = 0
        wins = 0
        cur = db.trades.find({}, {"profit_usd": 1})
        async for t in cur:
            total_trades += 1
            p = float(t.get("profit_usd") or 0)
            total_profit += p
            if p > 0:
                wins += 1
        winrate = (wins / total_trades * 100.0) if total_trades else 0.0
        msg = format_trade_msg(trade, {
            "total_profit": round(total_profit, 4),
            "total_trades": total_trades,
            "winrate": round(winrate, 2),
        })
        await send_telegram(tg_token, tg_chat, msg)
    except Exception as e:
        logger.warning(f"notify_trade fail: {e}")


async def _notify_partial(trade: dict):
    """Send urgent Telegram alert for partial/reversed trades."""
    tg_token = _decrypt_cred("telegram_bot_token")
    tg_chat = _decrypt_cred("telegram_chat_id")
    if not tg_token or not tg_chat:
        return
    try:
        msg = format_partial_trade_alert_msg(trade)
        await send_telegram(tg_token, tg_chat, msg)
    except Exception as e:
        logger.warning(f"notify_partial fail: {e}")


# --------------- Lifespan ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await load_settings_into_state()
    tasks = [
        asyncio.create_task(price_polling_task()),
        asyncio.create_task(binance_ws_task()),
        asyncio.create_task(auto_exec_task()),
        asyncio.create_task(telegram_balance_task()),
        asyncio.create_task(daily_summary_task()),
        asyncio.create_task(opportunity_logger_task()),
        asyncio.create_task(inventory_drift_task()),
    ]
    logger.info("Background tasks started")
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        mongo_client.close()


app = FastAPI(lifespan=lifespan)
api = APIRouter(prefix="/api")


# --------------- Routes ----------------
@api.get("/")
async def root():
    return {"service": "cex-dex-arbitrage", "status": "online"}


@api.get("/prices")
async def get_prices():
    return list(state.prices.values())


@api.get("/opportunities")
async def get_opportunities():
    return state.opportunities


@api.get("/stats")
async def get_stats():
    total_profit = 0.0
    total_trades = 0
    wins = 0
    cursor = db.trades.find({})
    async for t in cursor:
        total_trades += 1
        p = float(t.get("profit_usd", 0))
        total_profit += p
        if p > 0:
            wins += 1
    winrate = (wins / total_trades * 100.0) if total_trades else 0.0
    live_opps = sum(1 for o in state.opportunities if o["actionable"])
    return {
        "total_profit": round(total_profit, 4),
        "total_trades": total_trades,
        "winrate": round(winrate, 2),
        "live_opportunities": live_opps,
        "mode": "paper" if state.settings.get("paper_mode") else "live",
        "auto_exec": bool(state.settings.get("auto_exec")),
        "bot_enabled": bool(state.settings.get("bot_enabled", True)),
        "ws_connected": bool(state.ws_connected),
        "daily_pnl": round(state.daily_pnl, 4),
        "daily_trades": state.daily_trades,
    }


@api.get("/profit-series")
async def profit_series(limit: int = 200):
    """Returns cumulative profit time-series (most recent N trades, oldest first for the chart)."""
    cur = db.trades.find({}, {"_id": 0, "ts": 1, "profit_usd": 1, "coin": 1}).sort("ts", -1).limit(limit)
    docs = await cur.to_list(length=limit)
    docs.reverse()  # chronological for the chart
    cum = 0.0
    out = []
    for d in docs:
        cum += float(d.get("profit_usd") or 0)
        out.append({"ts": d["ts"], "cumulative": round(cum, 4), "trade_pnl": round(float(d.get("profit_usd") or 0), 4), "coin": d.get("coin")})
    return out


@api.get("/trades")
async def list_trades(limit: int = 100):
    cur = db.trades.find({}, {"_id": 0}).sort("ts", -1).limit(limit)
    return await cur.to_list(length=limit)


@api.get("/settings")
async def get_settings():
    # Return masked credentials + plain settings
    def maskc(name):
        v = _decrypt_cred(name)
        return mask(v) if v else ""
    return {
        "binance_api_key_masked": maskc("binance_api_key"),
        "binance_api_secret_masked": maskc("binance_api_secret"),
        "phantom_private_key_masked": maskc("phantom_private_key"),
        "telegram_bot_token_masked": maskc("telegram_bot_token"),
        "telegram_chat_id": _decrypt_cred("telegram_chat_id"),
        "has_binance_key": bool(_decrypt_cred("binance_api_key")),
        "has_phantom_key": bool(_decrypt_cred("phantom_private_key")),
        "has_telegram": bool(_decrypt_cred("telegram_bot_token") and _decrypt_cred("telegram_chat_id")),
        "paper_mode": state.settings.get("paper_mode", True),
        "auto_exec": state.settings.get("auto_exec", False),
        "trade_modal_usd": state.settings.get("trade_modal_usd", 100.0),
        "threshold_pct": state.settings.get("threshold_pct", 0.5),
        "slippage_pct": state.settings.get("slippage_pct", 0.3),
        "enabled_coins": state.settings["enabled_coins"] if state.settings.get("enabled_coins") is not None else list(COIN_LIST),
        "daily_loss_limit_usd": state.settings.get("daily_loss_limit_usd", 0.0),
        "max_daily_trades": state.settings.get("max_daily_trades", 0),
        "bot_enabled": state.settings.get("bot_enabled", True),
        "auto_reverse_on_partial": state.settings.get("auto_reverse_on_partial", False),
        "drift_alert_pct": state.settings.get("drift_alert_pct", 5.0),
        "ws_connected": bool(state.ws_connected),
        "all_coins": list(COIN_LIST),
    }


@api.post("/settings")
async def update_settings(payload: SettingsIn):
    update_doc = {}
    # Encrypt credentials if provided (non-empty)
    if payload.binance_api_key:
        update_doc["binance_api_key"] = encrypt(payload.binance_api_key)
    if payload.binance_api_secret:
        update_doc["binance_api_secret"] = encrypt(payload.binance_api_secret)
    if payload.phantom_private_key:
        update_doc["phantom_private_key"] = encrypt(payload.phantom_private_key)
    if payload.telegram_bot_token:
        update_doc["telegram_bot_token"] = encrypt(payload.telegram_bot_token)
    if payload.telegram_chat_id is not None:
        update_doc["telegram_chat_id"] = encrypt(payload.telegram_chat_id) if payload.telegram_chat_id else ""

    # Plain settings
    for f in (
        "paper_mode", "auto_exec", "trade_modal_usd",
        "threshold_pct", "slippage_pct", "enabled_coins",
        "daily_loss_limit_usd", "max_daily_trades", "bot_enabled",
        "auto_reverse_on_partial", "drift_alert_pct",
    ):
        v = getattr(payload, f)
        if v is not None:
            update_doc[f] = v

    if update_doc:
        await db.settings.update_one(
            {"_id": SETTINGS_ID}, {"$set": update_doc}, upsert=True
        )
        await load_settings_into_state()

    return {"status": "ok"}


@api.post("/execute")
async def execute_manual(payload: ExecuteOpportunityIn):
    if not state.settings.get("bot_enabled", True):
        raise HTTPException(status_code=400, detail="Bot is OFF. Enable it from the dashboard before executing.")
    opp = next((o for o in state.opportunities if o["id"] == payload.opportunity_id), None)
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found or expired")
    # Reset daily counters if date changed
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.daily_date != today:
        state.daily_date = today
        state.daily_pnl = 0.0
        state.daily_trades = 0
    # Enforce risk caps for manual too
    loss_cap = float(state.settings.get("daily_loss_limit_usd") or 0)
    trade_cap = int(state.settings.get("max_daily_trades") or 0)
    if loss_cap > 0 and state.daily_pnl <= -abs(loss_cap):
        raise HTTPException(status_code=400, detail=f"Daily loss limit reached (${state.daily_pnl:.2f})")
    if trade_cap > 0 and state.daily_trades >= trade_cap:
        raise HTTPException(status_code=400, detail=f"Daily trade cap reached ({state.daily_trades}/{trade_cap})")

    paper = state.settings.get("paper_mode", True)
    if paper:
        trade = await execute_trade_simulation(opp)
    else:
        bk = _decrypt_cred("binance_api_key")
        bs = _decrypt_cred("binance_api_secret")
        pk = _decrypt_cred("phantom_private_key")
        if not bk or not bs or not pk:
            raise HTTPException(status_code=400, detail="Live trading requires Binance + Phantom keys in Settings")
        modal_now = float(state.settings.get("trade_modal_usd") or 0)
        ok, reason = await _preflight_balance_check(opp, modal_now)
        if not ok:
            raise HTTPException(status_code=400, detail=f"Pre-flight blocked: {reason}")
        trade = await execute_trade_live(opp, bk, bs, pk)
    trade["trigger"] = "manual"
    await db.trades.insert_one({**trade, "_id": trade["id"]})
    await _notify_trade(trade)
    if trade.get("status") in ("partial", "reversed"):
        await _notify_partial(trade)
    state.daily_trades += 1
    state.daily_pnl += float(trade.get("profit_usd") or 0)
    return trade


@api.post("/test-telegram")
async def test_telegram():
    tg_token = _decrypt_cred("telegram_bot_token")
    tg_chat = _decrypt_cred("telegram_chat_id")
    if not tg_token or not tg_chat:
        raise HTTPException(status_code=400, detail="Telegram credentials not set")
    ok = await send_telegram(tg_token, tg_chat, "✅ *Test message* from Arbitrage Bot.")
    return {"sent": ok}


@api.post("/test-balance-telegram")
async def test_balance_telegram():
    """Manually trigger a balance snapshot to Telegram (preview the 15-min message)."""
    tg_token = _decrypt_cred("telegram_bot_token")
    tg_chat = _decrypt_cred("telegram_chat_id")
    if not tg_token or not tg_chat:
        raise HTTPException(status_code=400, detail="Telegram credentials not set")

    cex_bal = await _fetch_binance_balances()
    dex_bal = await _fetch_phantom_balances()

    total_profit = 0.0
    total_trades = 0
    try:
        cur = db.trades.find({}, {"profit_usd": 1})
        async for t in cur:
            total_trades += 1
            total_profit += float(t.get("profit_usd") or 0)
    except Exception:
        pass
    status_snapshot = {
        "paper_mode": state.settings.get("paper_mode", True),
        "auto_exec": state.settings.get("auto_exec", False),
        "bot_enabled": state.settings.get("bot_enabled", True),
        "daily_pnl": state.daily_pnl,
        "daily_trades": state.daily_trades,
        "total_profit": round(total_profit, 4),
        "total_trades": total_trades,
    }
    msg = format_balance_msg(cex_bal, dex_bal, prices=state.prices, status=status_snapshot)
    ok = await send_telegram(tg_token, tg_chat, msg)
    # Also reset the 15-min timer so the next periodic message lands 15 min from now
    state.last_balance_notif = time.time()
    return {"sent": ok, "cex_assets": len(cex_bal), "dex_assets": len(dex_bal)}


@api.get("/daily-summary")
async def get_daily_summary(date: Optional[str] = None):
    """Get the WIB daily summary. If no `date` (YYYY-MM-DD) provided, returns yesterday WIB."""
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return await _compute_daily_summary(date)


@api.post("/test-daily-summary")
async def test_daily_summary(date: Optional[str] = None):
    """Send a daily summary to Telegram on demand. Defaults to yesterday WIB."""
    tg_token = _decrypt_cred("telegram_bot_token")
    tg_chat = _decrypt_cred("telegram_chat_id")
    if not tg_token or not tg_chat:
        raise HTTPException(status_code=400, detail="Telegram credentials not set")
    summary = await _compute_daily_summary(date)
    msg = format_daily_summary_msg(summary)
    sent = await send_telegram(tg_token, tg_chat, msg)
    return {"sent": sent, "summary": summary}


@api.get("/export-trades-csv")
async def export_trades_csv():
    """Stream the full trade history as a CSV file."""
    columns = [
        "ts", "coin", "mode", "buy_side", "sell_side",
        "buy_price", "sell_price", "modal_usd", "spread_pct",
        "net_profit_pct", "profit_usd", "status", "trigger",
        "binance_order_id", "error", "id",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    cur = db.trades.find({}, {"_id": 0}).sort("ts", -1)
    async for t in cur:
        row = {k: t.get(k, "") for k in columns}
        writer.writerow(row)
    buf.seek(0)
    filename = f"arb-trades-{datetime.now(WIB).strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class BacktestConfigIn(BaseModel):
    name: str
    threshold_pct: float
    slippage_pct: float


class BacktestRequest(BaseModel):
    configs: list[BacktestConfigIn]
    from_date: Optional[str] = None  # ISO datetime
    to_date: Optional[str] = None


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@api.get("/opportunity-log-stats")
async def opportunity_log_stats():
    count = await db.opportunity_log.count_documents({})
    if count == 0:
        return {"count": 0, "from_ts": None, "to_ts": None, "by_coin": []}
    first = await db.opportunity_log.find_one({}, sort=[("ts", 1)])
    last = await db.opportunity_log.find_one({}, sort=[("ts", -1)])
    by_coin = await db.opportunity_log.aggregate([
        {"$group": {
            "_id": "$coin",
            "count": {"$sum": 1},
            "avg_spread": {"$avg": "$spread_pct"},
            "max_spread": {"$max": "$spread_pct"},
        }},
        {"$sort": {"count": -1}},
    ]).to_list(length=50)
    return {
        "count": count,
        "from_ts": first["ts"].isoformat() if hasattr(first["ts"], "isoformat") else str(first["ts"]),
        "to_ts": last["ts"].isoformat() if hasattr(last["ts"], "isoformat") else str(last["ts"]),
        "by_coin": [
            {
                "coin": d["_id"],
                "count": d["count"],
                "avg_spread_pct": round(d.get("avg_spread") or 0, 4),
                "max_spread_pct": round(d.get("max_spread") or 0, 4),
            }
            for d in by_coin
        ],
    }


@api.post("/clear-opportunity-log")
async def clear_opportunity_log():
    r = await db.opportunity_log.delete_many({})
    state.last_opp_log_ts = {}
    return {"deleted": r.deleted_count, "status": "ok"}


@api.get("/inventory-drift")
async def get_inventory_drift():
    """Compute current inventory drift vs baseline for each coin."""
    snapshot = await _compute_inventory_snapshot()
    drift_threshold = float(state.settings.get("drift_alert_pct") or 5.0)
    imbalance_threshold = 40.0
    coins = []
    for coin, current in snapshot.items():
        baseline = state.inventory_baseline.get(coin)
        if not baseline:
            coins.append({
                "coin": coin,
                "current": current,
                "baseline": None,
                "drift_pct": None,
                "imbalance_pct": None,
                "status": "no_baseline",
            })
            continue
        m = _compute_drift(coin, current, baseline)
        if abs(m["drift_pct"]) > drift_threshold:
            status = "drift_exceeded"
        elif m["imbalance_pct"] > imbalance_threshold:
            status = "imbalance_high"
        else:
            status = "ok"
        coins.append({
            "coin": coin,
            "current": current,
            "baseline": baseline,
            **m,
            "status": status,
        })
    return {
        "coins": coins,
        "drift_alert_pct": drift_threshold,
        "imbalance_alert_pct": imbalance_threshold,
        "baseline_set": bool(state.inventory_baseline),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@api.post("/inventory-baseline/reset")
async def reset_inventory_baseline():
    """Snapshot current CEX+DEX balances as the new inventory baseline."""
    snapshot = await _compute_inventory_snapshot()
    now_iso = datetime.now(timezone.utc).isoformat()
    baseline = {}
    for coin, q in snapshot.items():
        baseline[coin] = {**q, "ts": now_iso}
    state.inventory_baseline = baseline
    state.last_drift_alert_ts = {}
    try:
        await db.settings.update_one(
            {"_id": SETTINGS_ID},
            {"$set": {"inventory_baseline": baseline}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"persist baseline: {e}")
    return {"baseline": baseline, "coins": len(baseline), "ts": now_iso}


@api.post("/backtest-strategies")
async def backtest_strategies(req: BacktestRequest):
    """Replay logged opportunities against multiple strategy configurations.

    For each config, simulates the auto-exec loop (same 30s/coin throttle, same fee model)
    and returns total trades, total profit, avg per trade, per-coin breakdown.
    """
    if not req.configs:
        raise HTTPException(status_code=400, detail="At least one strategy config required")
    if len(req.configs) > 5:
        raise HTTPException(status_code=400, detail="Max 5 strategies per backtest")

    flt: dict = {}
    try:
        rng = {}
        if req.from_date:
            rng["$gte"] = _parse_iso(req.from_date)
        if req.to_date:
            rng["$lte"] = _parse_iso(req.to_date)
        if rng:
            flt["ts"] = rng
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid from_date/to_date (use ISO 8601)")

    opps_raw = await db.opportunity_log.find(flt).sort("ts", 1).to_list(length=200_000)
    if not opps_raw:
        return {
            "opportunities_count": 0,
            "duration_hours": 0,
            "from_ts": None,
            "to_ts": None,
            "results": [],
            "winner": None,
        }

    first_ts = opps_raw[0]["ts"]
    last_ts = opps_raw[-1]["ts"]
    duration_hours = max((last_ts - first_ts).total_seconds() / 3600.0, 1 / 3600.0)

    results = []
    for config in req.configs:
        fee_total = BINANCE_TAKER_FEE_PCT + JUPITER_AVG_FEE_PCT + float(config.slippage_pct)
        last_fired: dict[str, float] = {}
        total_profit = 0.0
        total_trades = 0
        per_coin: dict[str, dict] = {}

        for o in opps_raw:
            spread = float(o.get("spread_pct") or 0)
            net = spread - fee_total
            if net < float(config.threshold_pct):
                continue
            coin = o["coin"]
            ts_epoch = o["ts"].timestamp()
            if ts_epoch - last_fired.get(coin, 0) < 30:
                continue
            last_fired[coin] = ts_epoch
            modal = float(o.get("modal_usd") or 100.0)
            profit = (net / 100.0) * modal
            total_profit += profit
            total_trades += 1
            rec = per_coin.setdefault(coin, {"coin": coin, "profit": 0.0, "trades": 0})
            rec["profit"] += profit
            rec["trades"] += 1

        coin_breakdown = [
            {"coin": v["coin"], "profit": round(v["profit"], 4), "trades": v["trades"]}
            for v in sorted(per_coin.values(), key=lambda x: x["profit"], reverse=True)
        ]
        avg_per_trade = (total_profit / total_trades) if total_trades else 0.0
        profit_per_hour = total_profit / duration_hours

        results.append({
            "name": config.name,
            "threshold_pct": config.threshold_pct,
            "slippage_pct": config.slippage_pct,
            "total_trades": total_trades,
            "total_profit": round(total_profit, 4),
            "avg_per_trade": round(avg_per_trade, 4),
            "profit_per_hour": round(profit_per_hour, 4),
            "projected_daily_profit": round(profit_per_hour * 24.0, 2),
            "best_coin": coin_breakdown[0] if coin_breakdown else None,
            "worst_coin": coin_breakdown[-1] if coin_breakdown else None,
            "per_coin": coin_breakdown,
        })

    ranked = sorted(results, key=lambda r: r["total_profit"], reverse=True)
    winner_name = ranked[0]["name"] if ranked and ranked[0]["total_profit"] > 0 else None

    return {
        "opportunities_count": len(opps_raw),
        "duration_hours": round(duration_hours, 2),
        "from_ts": first_ts.isoformat(),
        "to_ts": last_ts.isoformat(),
        "winner": winner_name,
        "results": results,
    }


@api.post("/reset-stats")
async def reset_stats():
    """Clear all trade history and reset in-memory daily counters."""
    result = await db.trades.delete_many({})
    state.daily_pnl = 0.0
    state.daily_trades = 0
    state.daily_date = ""
    return {"deleted": result.deleted_count, "status": "ok"}


@api.get("/coins")
async def list_coins():
    return COIN_LIST


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
