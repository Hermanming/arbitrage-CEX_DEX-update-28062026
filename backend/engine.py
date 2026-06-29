"""Arbitrage engine: realtime price polling, opportunity scanning, execution."""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

from constants import (
    BINANCE_TAKER_FEE_PCT,
    COIN_LIST,
    JUPITER_AVG_FEE_PCT,
    TOKENS,
)

logger = logging.getLogger("engine")

BINANCE_URL = "https://data-api.binance.vision/api/v3/ticker/price"
JUPITER_PRICE_URL = "https://lite-api.jup.ag/price/v3"


class EngineState:
    def __init__(self):
        # latest prices
        self.prices: dict[str, dict] = {}
        # current opportunities (computed each scan)
        self.opportunities: list[dict] = []
        # in-memory settings cache (loaded from DB)
        self.settings: dict = {
            "paper_mode": True,
            "auto_exec": False,
            "trade_modal_usd": 100.0,
            "threshold_pct": 0.5,
            "slippage_pct": 0.3,
            "enabled_coins": list(TOKENS.keys()),
            "daily_loss_limit_usd": 0.0,   # 0 = unlimited
            "max_daily_trades": 0,         # 0 = unlimited
            "bot_enabled": True,           # master ON/OFF for execution
        }
        # encrypted credentials (raw encrypted strings, decrypted on use)
        self.creds: dict = {}
        # stats
        self.last_balance_notif: float = 0.0
        # WebSocket status indicator
        self.ws_connected: bool = False
        # daily counters (reset by date string)
        self.daily_date: str = ""
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        # rolling cumulative profit series for chart [(ts_iso, cum_profit)]
        self.profit_series: list[dict] = []


state = EngineState()


async def fetch_binance_prices(client: httpx.AsyncClient) -> dict[str, float]:
    """Fetch each symbol individually so invalid symbols don't break the batch."""
    async def fetch_one(coin: str, symbol: str):
        try:
            r = await client.get(BINANCE_URL, params={"symbol": symbol}, timeout=6.0)
            if r.status_code != 200:
                return coin, None
            data = r.json()
            return coin, float(data["price"])
        except Exception:
            return coin, None

    tasks = [fetch_one(c, TOKENS[c][0]) for c in COIN_LIST]
    results = await asyncio.gather(*tasks)
    return {coin: price for coin, price in results if price is not None}


async def fetch_jupiter_prices(client: httpx.AsyncClient) -> dict[str, float]:
    mints = [TOKENS[c][1] for c in COIN_LIST]
    try:
        r = await client.get(
            JUPITER_PRICE_URL,
            params={"ids": ",".join(mints)},
            timeout=8.0,
        )
        r.raise_for_status()
        data = r.json()
        out = {}
        for coin, (_, mint, _) in TOKENS.items():
            entry = data.get(mint)
            if entry and isinstance(entry, dict):
                # v3 returns "usdPrice" or "price" depending on era; handle both
                price = entry.get("usdPrice") or entry.get("price")
                if price is not None:
                    out[coin] = float(price)
        return out
    except Exception as e:
        logger.warning(f"Jupiter fetch error: {e}")
        return {}


def compute_opportunities() -> list[dict]:
    opps = []
    threshold = state.settings.get("threshold_pct", 0.5)
    slippage = state.settings.get("slippage_pct", 0.3)
    modal = state.settings.get("trade_modal_usd", 100.0)
    enabled_setting = state.settings.get("enabled_coins")
    enabled = set(enabled_setting if enabled_setting is not None else COIN_LIST)
    fee_total = BINANCE_TAKER_FEE_PCT + JUPITER_AVG_FEE_PCT + slippage

    for coin, info in state.prices.items():
        if coin not in enabled:
            continue
        cex = info.get("binance")
        dex = info.get("jupiter")
        if not cex or not dex or cex <= 0 or dex <= 0:
            continue
        # buy on cheaper side, sell on the other
        if dex > cex:
            buy_side, sell_side = "CEX", "DEX"
            buy_price, sell_price = cex, dex
        else:
            buy_side, sell_side = "DEX", "CEX"
            buy_price, sell_price = dex, cex

        spread_pct = (sell_price - buy_price) / buy_price * 100.0
        net_profit_pct = spread_pct - fee_total
        est_profit_usd = (net_profit_pct / 100.0) * modal

        opp = {
            "id": f"{coin}-{int(time.time()*1000)}",
            "coin": coin,
            "cex_price": cex,
            "dex_price": dex,
            "buy_side": buy_side,
            "sell_side": sell_side,
            "spread_pct": round(spread_pct, 4),
            "net_profit_pct": round(net_profit_pct, 4),
            "est_profit_usd": round(est_profit_usd, 4),
            "actionable": net_profit_pct >= threshold,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        opps.append(opp)

    # Sort by net profit descending
    opps.sort(key=lambda x: x["net_profit_pct"], reverse=True)
    return opps


async def price_polling_task():
    """Continuously fetch prices from Binance + Jupiter and update state."""
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        while True:
            try:
                bnb, jup = await asyncio.gather(
                    fetch_binance_prices(client),
                    fetch_jupiter_prices(client),
                )
                now = datetime.now(timezone.utc).isoformat()
                for coin in COIN_LIST:
                    prev = state.prices.get(coin, {})
                    state.prices[coin] = {
                        "coin": coin,
                        "binance": bnb.get(coin, prev.get("binance")),
                        "jupiter": jup.get(coin, prev.get("jupiter")),
                        "ts": now,
                    }
                state.opportunities = compute_opportunities()
            except Exception as e:
                logger.exception(f"price_polling error: {e}")
            # When WS is connected, poll only as a slower fallback for accuracy
            await asyncio.sleep(15.0 if state.ws_connected else 4.0)


async def binance_ws_task():
    """Subscribe to Binance combined ticker streams for sub-second CEX updates."""
    import json
    streams = "/".join(f"{TOKENS[c][0].lower()}@ticker" for c in COIN_LIST)
    # data-stream is the geo-friendly mirror for WS (same protocol as stream.binance.com)
    urls = [
        f"wss://data-stream.binance.vision/stream?streams={streams}",
        f"wss://stream.binance.com:9443/stream?streams={streams}",
    ]
    backoff = 2.0
    last_compute = 0.0
    sym_to_coin = {TOKENS[c][0]: c for c in COIN_LIST}
    while True:
        for url in urls:
            try:
                import websockets
                async with websockets.connect(url, ping_interval=20, ping_timeout=60, close_timeout=5, max_size=2**22) as ws:
                    state.ws_connected = True
                    backoff = 2.0
                    logger.info(f"Binance WS connected via {url.split('//')[1].split('/')[0]}")
                    try:
                        async for raw in ws:
                            try:
                                msg = json.loads(raw)
                                data = msg.get("data") or {}
                                sym = data.get("s")
                                last = data.get("c")
                                if not sym or not last:
                                    continue
                                coin = sym_to_coin.get(sym)
                                if not coin:
                                    continue
                                prev = state.prices.get(coin, {})
                                state.prices[coin] = {
                                    "coin": coin,
                                    "binance": float(last),
                                    "jupiter": prev.get("jupiter"),
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                }
                                now_t = time.time()
                                if now_t - last_compute > 0.2:
                                    state.opportunities = compute_opportunities()
                                    last_compute = now_t
                            except Exception:
                                pass
                    finally:
                        state.ws_connected = False
            except Exception as e:
                state.ws_connected = False
                logger.warning(f"Binance WS error ({url[:40]}...): {e}")
                await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30.0)


async def execute_trade_simulation(opp: dict) -> dict:
    """Paper trade execution: just record the trade with computed profit."""
    modal = state.settings.get("trade_modal_usd", 100.0)
    net_pct = opp["net_profit_pct"]
    profit_usd = round(modal * net_pct / 100.0, 4)
    trade = {
        "id": str(uuid.uuid4()),
        "coin": opp["coin"],
        "mode": "paper",
        "buy_side": opp["buy_side"],
        "sell_side": opp["sell_side"],
        "buy_price": opp["cex_price"] if opp["buy_side"] == "CEX" else opp["dex_price"],
        "sell_price": opp["cex_price"] if opp["sell_side"] == "CEX" else opp["dex_price"],
        "modal_usd": modal,
        "spread_pct": opp["spread_pct"],
        "net_profit_pct": net_pct,
        "profit_usd": profit_usd,
        "status": "filled",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    return trade


async def execute_trade_live(opp: dict, binance_key: str, binance_secret: str, phantom_key: str) -> dict:
    """Live trade: execute on CEX & DEX with pre-positioned balances (parallel hedge)."""
    from binance.client import Client as BinanceClient
    modal = state.settings.get("trade_modal_usd", 100.0)
    coin = opp["coin"]
    symbol = TOKENS[coin][0]

    trade = {
        "id": str(uuid.uuid4()),
        "coin": coin,
        "mode": "live",
        "buy_side": opp["buy_side"],
        "sell_side": opp["sell_side"],
        "buy_price": opp["cex_price"] if opp["buy_side"] == "CEX" else opp["dex_price"],
        "sell_price": opp["cex_price"] if opp["sell_side"] == "CEX" else opp["dex_price"],
        "modal_usd": modal,
        "spread_pct": opp["spread_pct"],
        "net_profit_pct": opp["net_profit_pct"],
        "profit_usd": round(modal * opp["net_profit_pct"] / 100.0, 4),
        "status": "filled",
        "ts": datetime.now(timezone.utc).isoformat(),
        "error": None,
    }

    try:
        # CEX leg via python-binance: BUY or SELL on Binance spot
        side = "BUY" if opp["buy_side"] == "CEX" else "SELL"
        client = BinanceClient(binance_key, binance_secret)
        # quoteOrderQty allows USDT-based market orders
        order = client.create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quoteOrderQty=modal,
        )
        trade["binance_order_id"] = order.get("orderId")
        trade["status"] = "filled"
    except Exception as e:
        logger.exception(f"Binance live trade failed: {e}")
        trade["status"] = "failed"
        trade["error"] = f"binance: {e}"
        return trade

    # DEX leg via Jupiter swap (best-effort; non-fatal on failure)
    try:
        await jupiter_swap(opp, phantom_key, modal)
        trade["status"] = "filled"
    except Exception as e:
        logger.exception(f"Jupiter swap failed: {e}")
        trade["status"] = "partial"
        trade["error"] = f"jupiter: {e}"

    return trade


async def jupiter_swap(opp: dict, phantom_key: str, modal_usd: float):
    """Execute swap via Jupiter v1 API. Buys/sells token vs USDC."""
    import base64
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction
    from solders import message as sol_message
    from solana.rpc.async_api import AsyncClient as SolanaAsyncClient
    from solana.rpc.types import TxOpts
    from constants import USDC_MINT, USDC_DECIMALS
    import os

    coin = opp["coin"]
    _, mint, decimals = TOKENS[coin]

    # If buying on DEX -> swap USDC for token. Sell on DEX -> swap token for USDC.
    side_buy_on_dex = opp["buy_side"] == "DEX"
    input_mint = USDC_MINT if side_buy_on_dex else mint
    output_mint = mint if side_buy_on_dex else USDC_MINT

    if side_buy_on_dex:
        amount = int(modal_usd * (10 ** USDC_DECIMALS))
    else:
        token_qty = modal_usd / opp["dex_price"]
        amount = int(token_qty * (10 ** decimals))

    slippage_bps = int(state.settings.get("slippage_pct", 0.3) * 100)

    async with httpx.AsyncClient(timeout=20.0) as client:
        q = await client.get(
            "https://lite-api.jup.ag/swap/v1/quote",
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": slippage_bps,
            },
        )
        q.raise_for_status()
        quote = q.json()

        kp = Keypair.from_base58_string(phantom_key)
        swap_req = {
            "quoteResponse": quote,
            "userPublicKey": str(kp.pubkey()),
            "wrapAndUnwrapSol": True,
        }
        sresp = await client.post("https://lite-api.jup.ag/swap/v1/swap", json=swap_req)
        sresp.raise_for_status()
        swap_tx_b64 = sresp.json()["swapTransaction"]

    raw_tx = VersionedTransaction.from_bytes(base64.b64decode(swap_tx_b64))
    sig = kp.sign_message(sol_message.to_bytes_versioned(raw_tx.message))
    signed = VersionedTransaction.populate(raw_tx.message, [sig])

    rpc = os.environ.get("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
    sol_client = SolanaAsyncClient(rpc)
    try:
        await sol_client.send_raw_transaction(bytes(signed), opts=TxOpts(skip_preflight=False))
    finally:
        await sol_client.close()
