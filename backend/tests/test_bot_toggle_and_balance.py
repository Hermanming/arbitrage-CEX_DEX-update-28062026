"""End-to-end tests for the 4 features:
1) Master ON/OFF (bot_enabled) toggle
2) Telegram trade msg includes net profit + lifetime stats (unit-level)
3) Reset Stats endpoint
4) /api/test-balance-telegram + format_balance_msg (unit-level)
5) Bonus: telegram_balance_task is registered and not crashing
"""
import os
import sys
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://arb-profit-engine-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Make backend importable for unit-level notifier tests
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- 1. bot_enabled toggle ----------
class TestBotEnabledToggle:
    def test_stats_has_bot_enabled_field(self, http):
        r = http.get(f"{API}/stats")
        assert r.status_code == 200
        data = r.json()
        assert "bot_enabled" in data
        assert isinstance(data["bot_enabled"], bool)

    def test_settings_has_bot_enabled(self, http):
        r = http.get(f"{API}/settings")
        assert r.status_code == 200
        assert "bot_enabled" in r.json()

    def test_toggle_bot_enabled_off_then_on(self, http):
        # Force OFF
        r = http.post(f"{API}/settings", json={"bot_enabled": False})
        assert r.status_code == 200
        time.sleep(0.5)
        s = http.get(f"{API}/settings").json()
        assert s["bot_enabled"] is False, "bot_enabled did not switch to False"

        stats = http.get(f"{API}/stats").json()
        assert stats["bot_enabled"] is False

        # Back ON
        r2 = http.post(f"{API}/settings", json={"bot_enabled": True})
        assert r2.status_code == 200
        time.sleep(0.5)
        s2 = http.get(f"{API}/settings").json()
        assert s2["bot_enabled"] is True


# ---------- 2. /api/execute blocked when bot is OFF ----------
class TestExecuteRespectsBotEnabled:
    def test_execute_blocked_when_bot_off(self, http):
        http.post(f"{API}/settings", json={"bot_enabled": False})
        time.sleep(0.5)
        # opportunities may or may not exist; either way, OFF must short-circuit
        r = http.post(f"{API}/execute", json={"opportunity_id": "any-id"})
        assert r.status_code == 400, f"expected 400 when bot OFF, got {r.status_code}"
        detail = r.json().get("detail", "")
        assert "Bot is OFF" in detail or "bot" in detail.lower()

    def test_execute_when_bot_on(self, http):
        # Turn back on, ensure paper mode
        http.post(f"{API}/settings", json={"bot_enabled": True, "paper_mode": True})
        time.sleep(0.5)
        # Wait for opportunities to be computed
        opp_id = None
        for _ in range(30):
            r = http.get(f"{API}/opportunities")
            if r.status_code == 200:
                opps = r.json()
                if opps:
                    opp_id = opps[0].get("id")
                    if opp_id:
                        break
            time.sleep(2)
        if not opp_id:
            pytest.skip("No live opportunities available within 60s; skipping execute happy-path")

        r = http.post(f"{API}/execute", json={"opportunity_id": opp_id})
        # Could be 200 (trade created) or 404 if opp expired in between, or 400 for risk cap
        assert r.status_code in (200, 400, 404), f"unexpected status {r.status_code}: {r.text}"
        if r.status_code == 200:
            body = r.json()
            assert "id" in body
            assert body.get("trigger") == "manual"


# ---------- 3. Reset Stats ----------
class TestResetStats:
    def test_reset_clears_history(self, http):
        # Try to create some history via manual execute (best-effort)
        http.post(f"{API}/settings", json={"bot_enabled": True, "paper_mode": True})
        time.sleep(0.5)
        opps = http.get(f"{API}/opportunities").json()
        if opps:
            http.post(f"{API}/execute", json={"opportunity_id": opps[0]["id"]})

        r = http.post(f"{API}/reset-stats")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert "deleted" in body and isinstance(body["deleted"], int)

        # Verify counters cleared
        time.sleep(0.5)
        stats = http.get(f"{API}/stats").json()
        assert stats["total_profit"] == 0
        assert stats["total_trades"] == 0
        assert stats["winrate"] == 0
        assert stats["daily_pnl"] == 0
        assert stats["daily_trades"] == 0

        trades = http.get(f"{API}/trades").json()
        assert trades == [] or len(trades) == 0


# ---------- 4. /api/test-balance-telegram without creds ----------
class TestTestBalanceTelegram:
    def test_returns_400_without_creds(self, http):
        r = http.post(f"{API}/test-balance-telegram")
        # If creds happen to be configured we accept 200; otherwise 400
        if r.status_code == 400:
            assert "Telegram credentials not set" in r.json().get("detail", "")
        else:
            assert r.status_code == 200


# ---------- 5. Notifier unit-level checks ----------
class TestNotifierFormatters:
    def test_format_trade_msg_includes_profit_and_pct(self):
        from notifier import format_trade_msg
        trade = {
            "id": "t1", "mode": "paper", "coin": "SOL", "modal_usd": 100.0,
            "buy_side": "binance", "buy_price": 100.0,
            "sell_side": "jupiter", "sell_price": 101.0,
            "spread_pct": 1.0, "profit_usd": 0.85, "net_profit_pct": 0.85,
            "status": "executed",
        }
        msg = format_trade_msg(trade, totals={"total_profit": 12.34, "total_trades": 5, "winrate": 80.0})
        assert "Profit" in msg
        assert "$0.8500" in msg
        assert "0.8500%" in msg
        assert "Lifetime Stats" in msg
        assert "$12.3400" in msg
        assert "Winrate" in msg

    def test_format_balance_msg_with_status_and_prices(self):
        from notifier import format_balance_msg
        cex = {"SOL": 2.0, "USDT": 50.0}
        dex = {"SOL": 1.0, "USDC": 25.0}
        prices = {"SOL": {"binance": 100.0, "jupiter": 99.0}}
        status = {
            "paper_mode": True, "auto_exec": False, "bot_enabled": True,
            "daily_pnl": 1.23, "daily_trades": 2,
            "total_profit": 9.99, "total_trades": 10,
        }
        msg = format_balance_msg(cex, dex, prices=prices, status=status)
        assert "Bot:" in msg
        assert "ON" in msg
        assert "Today:" in msg
        assert "Lifetime:" in msg
        # USD valuations
        assert "$200.00" in msg or "$200" in msg  # 2 * 100
        assert "$99.00" in msg or "$99" in msg    # 1 * 99
        assert "$50.00" in msg                     # USDT
        assert "$25.00" in msg                     # USDC
        assert "Grand Total" in msg


# ---------- 6. Background task is registered & not throwing ----------
class TestBackgroundTask:
    def test_background_tasks_started_log(self):
        import subprocess
        out = subprocess.run(
            ["bash", "-lc", "tail -n 400 /var/log/supervisor/backend.*.log 2>/dev/null || true"],
            capture_output=True, text=True,
        )
        combined = out.stdout + out.stderr
        assert "Background tasks started" in combined, "lifespan startup log missing"
        # No balance task crash signature
        assert "balance task:" not in combined.lower().replace("balance task: ", "balance task:") or \
               "balance task: " not in combined  # heuristic: no exception line
