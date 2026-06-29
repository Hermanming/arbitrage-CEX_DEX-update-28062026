"""FastAPI server for CEX-DEX Arbitrage Bot."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from constants import COIN_LIST, TOKENS
from crypto_utils import encrypt, decrypt, mask
from engine import (
    binance_ws_task,
    execute_trade_live,
    execute_trade_simulation,
    price_polling_task,
    state,
)
from notifier import format_balance_msg, format_trade_msg, send_telegram

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
    })
    state.creds = {
        "binance_api_key": doc.get("binance_api_key", ""),
        "binance_api_secret": doc.get("binance_api_secret", ""),
        "phantom_private_key": doc.get("phantom_private_key", ""),
        "telegram_bot_token": doc.get("telegram_bot_token", ""),
        "telegram_chat_id": doc.get("telegram_chat_id", ""),
    }


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
                            trade = await execute_trade_live(
                                opp,
                                _decrypt_cred("binance_api_key"),
                                _decrypt_cred("binance_api_secret"),
                                _decrypt_cred("phantom_private_key"),
                            )
                        trade["trigger"] = "auto"
                        await db.trades.insert_one({**trade, "_id": trade["id"]})
                        await _notify_trade(trade)
                        # update daily counters
                        state.daily_trades += 1
                        state.daily_pnl += float(trade.get("profit_usd") or 0)
                    except Exception as e:
                        logger.exception(f"auto exec error: {e}")
        except Exception as e:
            logger.exception(f"auto_exec_task: {e}")
        await asyncio.sleep(3.0)


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


async def _notify_trade(trade: dict):
    tg_token = _decrypt_cred("telegram_bot_token")
    tg_chat = _decrypt_cred("telegram_chat_id")
    if tg_token and tg_chat:
        # Build lifetime totals snapshot for the message
        try:
            total_profit = 0.0
            total_trades = 0
            wins = 0
            cur = db.trades.find({})
            async for t in cur:
                total_trades += 1
                p = float(t.get("profit_usd", 0))
                total_profit += p
                if p > 0:
                    wins += 1
            totals = {
                "total_profit": round(total_profit, 4),
                "total_trades": total_trades,
                "winrate": (wins / total_trades * 100.0) if total_trades else 0.0,
            }
        except Exception:
            totals = None
        await send_telegram(tg_token, tg_chat, format_trade_msg(trade, totals))


# --------------- Lifespan ----------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    await load_settings_into_state()
    tasks = [
        asyncio.create_task(price_polling_task()),
        asyncio.create_task(binance_ws_task()),
        asyncio.create_task(auto_exec_task()),
        asyncio.create_task(telegram_balance_task()),
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
        trade = await execute_trade_live(opp, bk, bs, pk)
    trade["trigger"] = "manual"
    await db.trades.insert_one({**trade, "_id": trade["id"]})
    await _notify_trade(trade)
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
