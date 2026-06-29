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


def format_trade_msg(trade: dict, totals: dict | None = None) -> str:
    emoji = "🟢" if trade.get("profit_usd", 0) >= 0 else "🔴"
    msg = (
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
    if totals:
        msg += (
            f"\n\n📊 *Lifetime Stats*\n"
            f"• Total Profit: `${totals.get('total_profit', 0):.4f}`\n"
            f"• Total Trades: `{totals.get('total_trades', 0)}`\n"
            f"• Winrate: `{totals.get('winrate', 0):.2f}%`"
        )
    return msg


def _price_for(coin: str, prices: dict | None, source: str = "binance") -> float | None:
    """Return USD price for coin from in-memory prices map. source = 'binance' or 'jupiter'."""
    if not prices:
        return None
    info = prices.get(coin) or {}
    p = info.get(source) or info.get("binance") or info.get("jupiter")
    try:
        return float(p) if p else None
    except Exception:
        return None


def _format_balance_lines(balances: dict, prices: dict | None, source: str) -> tuple[list[str], float]:
    lines: list[str] = []
    total_usd = 0.0
    # Sort by USD value desc
    items = []
    for coin, qty in balances.items():
        if qty <= 0:
            continue
        if coin in ("USDT", "USDC"):
            usd = qty
        else:
            price = _price_for(coin, prices, source)
            usd = qty * price if price else 0.0
        items.append((coin, qty, usd))
    items.sort(key=lambda x: x[2], reverse=True)
    for coin, qty, usd in items:
        total_usd += usd
        if usd > 0:
            lines.append(f"  • `{coin}`: `{qty:.6f}` ≈ `${usd:,.2f}`")
        else:
            lines.append(f"  • `{coin}`: `{qty:.6f}`")
    return lines, total_usd


def format_daily_summary_msg(summary: dict) -> str:
    """Format the end-of-day Telegram summary (WIB day just ended)."""
    total_profit = float(summary.get("total_profit") or 0.0)
    total_trades = int(summary.get("total_trades") or 0)
    winrate = float(summary.get("winrate") or 0.0)
    wins = int(summary.get("wins") or 0)
    losses = int(summary.get("losses") or 0)
    best = summary.get("best_coin") or {}
    worst = summary.get("worst_coin") or {}
    day_label = summary.get("day_label", "")
    avg_profit = (total_profit / total_trades) if total_trades else 0.0

    pnl_emoji = "🟢" if total_profit >= 0 else "🔴"
    parts = [
        f"📅 *Daily Summary* — `{day_label}` (WIB)",
        "",
        f"{pnl_emoji} *Net P&L:* `${total_profit:,.4f}`",
        f"*Trades:* `{total_trades}` total · ✅ `{wins}` wins · ❌ `{losses}` losses",
        f"*Winrate:* `{winrate:.2f}%`",
        f"*Avg / Trade:* `${avg_profit:,.4f}`",
    ]

    if best.get("coin"):
        parts.append(
            f"\n🏆 *Best Coin:* `{best['coin']}` → `${float(best['profit']):,.4f}` "
            f"over `{int(best.get('trades') or 0)}` trades"
        )
    if worst.get("coin") and worst.get("coin") != best.get("coin"):
        parts.append(
            f"💀 *Worst Coin:* `{worst['coin']}` → `${float(worst['profit']):,.4f}` "
            f"over `{int(worst.get('trades') or 0)}` trades"
        )

    if total_trades == 0:
        parts.append("\n_No trades executed today._")

    return "\n".join(parts)


def format_balance_msg(
    cex_balances: dict,
    dex_balances: dict,
    prices: dict | None = None,
    status: dict | None = None,
) -> str:
    cex_lines, cex_total = _format_balance_lines(cex_balances, prices, "binance")
    dex_lines, dex_total = _format_balance_lines(dex_balances, prices, "jupiter")
    grand_total = cex_total + dex_total

    parts = ["📊 *Balance Snapshot (15m)*"]

    if status:
        mode = "LIVE" if not status.get("paper_mode", True) else "PAPER"
        exec_mode = "AUTO" if status.get("auto_exec") else "MANUAL"
        bot_state = "ON 🟢" if status.get("bot_enabled", True) else "OFF 🔴"
        parts.append(
            f"\n*Bot:* `{bot_state}`  ·  *Mode:* `{mode}`  ·  *Exec:* `{exec_mode}`"
        )
        daily_pnl = status.get("daily_pnl")
        daily_trades = status.get("daily_trades")
        if daily_pnl is not None or daily_trades is not None:
            pnl_emoji = "🟢" if (daily_pnl or 0) >= 0 else "🔴"
            parts.append(
                f"*Today:* {pnl_emoji} `${(daily_pnl or 0):,.4f}`  ·  Trades: `{daily_trades or 0}`"
            )
        total_profit = status.get("total_profit")
        total_trades = status.get("total_trades")
        if total_profit is not None:
            parts.append(
                f"*Lifetime:* `${total_profit:,.4f}` over `{total_trades or 0}` trades"
            )

    parts.append(
        "\n*CEX (Binance):* " + (f"`${cex_total:,.2f}` total" if cex_total > 0 else "")
    )
    parts.append("\n".join(cex_lines) if cex_lines else "  _no API key or empty_")
    parts.append(
        "\n*DEX (Phantom):* " + (f"`${dex_total:,.2f}` total" if dex_total > 0 else "")
    )
    parts.append("\n".join(dex_lines) if dex_lines else "  _no API key or empty_")

    if grand_total > 0:
        parts.append(f"\n💰 *Grand Total:* `${grand_total:,.2f}`")

    return "\n".join(parts)
