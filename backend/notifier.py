"""Telegram notifier."""
import logging
import httpx

logger = logging.getLogger("notifier")


async def send_telegram(token: str, chat_id: str, message: str) -> bool:
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return True
    except Exception as e:
        logger.warning(f"Telegram send failed: {e}")
        return False


def format_trade_msg(trade: dict) -> str:
    emoji = "🟢" if trade.get("profit_usd", 0) >= 0 else "🔴"
    return (
        f"{emoji} *Arbitrage Trade Executed*\n\n"
        f"*Mode:* `{trade['mode'].upper()}`\n"
        f"*Coin:* `{trade['coin']}`\n"
        f"*Modal:* `${trade['modal_usd']:.2f}`\n"
        f"*Buy:* `{trade['buy_side']}` @ `${trade['buy_price']:.6f}`\n"
        f"*Sell:* `{trade['sell_side']}` @ `${trade['sell_price']:.6f}`\n"
        f"*Spread:* `{trade['spread_pct']:.4f}%`\n"
        f"*Profit:* `${trade['profit_usd']:.4f}` "
        f"(`{trade['net_profit_pct']:.4f}%`)\n"
        f"*Status:* `{trade['status']}`"
    )


def format_balance_msg(cex_balances: dict, dex_balances: dict) -> str:
    cex_lines = [f"  • `{c}`: `{v:.6f}`" for c, v in cex_balances.items() if v > 0]
    dex_lines = [f"  • `{c}`: `{v:.6f}`" for c, v in dex_balances.items() if v > 0]
    return (
        "📊 *Balance Snapshot (15m)*\n\n"
        "*CEX (Binance):*\n" + ("\n".join(cex_lines) if cex_lines else "  _empty_") + "\n\n"
        "*DEX (Phantom):*\n" + ("\n".join(dex_lines) if dex_lines else "  _empty_")
    )
