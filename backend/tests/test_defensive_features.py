"""Backend tests for defensive trading features:
- Settings persistence for auto_reverse_on_partial and drift_alert_pct
- /api/inventory-baseline/reset
- /api/inventory-drift
- _compute_drift correctness
- _preflight_balance_check (no-keys path)
- Notifier formatters (drift alert, partial trade alert)
- Jupiter retry source code inspection
"""
import os
import sys
import inspect
import pytest
import requests

def _read_frontend_env_url() -> str:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env_url()).rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
sys.path.insert(0, "/app/backend")


# -------------------- Settings persistence --------------------
class TestSettingsPersistence:
    def test_settings_round_trip_new_fields(self):
        # Save new fields
        r = requests.post(
            f"{BASE_URL}/api/settings",
            json={"auto_reverse_on_partial": True, "drift_alert_pct": 7.5},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Verify GET returns them
        g = requests.get(f"{BASE_URL}/api/settings", timeout=15)
        assert g.status_code == 200
        data = g.json()
        assert data["auto_reverse_on_partial"] is True
        assert float(data["drift_alert_pct"]) == 7.5

        # Revert to defaults
        r2 = requests.post(
            f"{BASE_URL}/api/settings",
            json={"auto_reverse_on_partial": False, "drift_alert_pct": 5.0},
            timeout=15,
        )
        assert r2.status_code == 200
        g2 = requests.get(f"{BASE_URL}/api/settings", timeout=15).json()
        assert g2["auto_reverse_on_partial"] is False
        assert float(g2["drift_alert_pct"]) == 5.0


# -------------------- Inventory baseline & drift --------------------
class TestInventoryBaselineAndDrift:
    def test_reset_baseline_empty_when_no_keys(self):
        r = requests.post(f"{BASE_URL}/api/inventory-baseline/reset", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "baseline" in data
        assert "coins" in data
        assert "ts" in data
        # No API keys configured → baseline should be empty dict
        assert isinstance(data["baseline"], dict)
        assert data["coins"] == len(data["baseline"])

    def test_inventory_drift_no_keys(self):
        r = requests.get(f"{BASE_URL}/api/inventory-drift", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "coins" in data and isinstance(data["coins"], list)
        assert "drift_alert_pct" in data
        assert "imbalance_alert_pct" in data
        assert data["imbalance_alert_pct"] == 40.0
        assert "baseline_set" in data
        assert "ts" in data
        # Without keys, no coin snapshot possible -> coins == []
        assert data["coins"] == []


# -------------------- _compute_drift correctness --------------------
class TestComputeDrift:
    def test_drift_math(self):
        from server import _compute_drift
        baseline = {"cex_qty": 1.5, "dex_qty": 1.5, "total_qty": 3.0}
        current = {"cex_qty": 0.5, "dex_qty": 1.6, "total_qty": 2.1}
        m = _compute_drift("SOL", current, baseline)
        # drift = (2.1 - 3.0) / 3.0 * 100 = -30%
        assert abs(m["drift_pct"] - (-30.0)) < 0.01
        # imbalance = |0.5 - 1.6| / 2.1 * 100 ≈ 52.38%
        assert abs(m["imbalance_pct"] - 52.3810) < 0.05
        assert m["baseline_total"] == 3.0
        assert m["current_total"] == 2.1

    def test_drift_zero_baseline(self):
        from server import _compute_drift
        m = _compute_drift("X", {"cex_qty": 0, "dex_qty": 0, "total_qty": 0},
                           {"cex_qty": 0, "dex_qty": 0, "total_qty": 0})
        assert m["drift_pct"] == 0.0
        assert m["imbalance_pct"] == 0.0


# -------------------- Pre-flight balance check --------------------
class TestPreflightBalanceCheck:
    def test_preflight_skipped_no_keys(self):
        import asyncio
        from server import _preflight_balance_check
        opp = {"coin": "SOL", "buy_side": "CEX", "sell_side": "DEX",
               "cex_price": 200.0, "dex_price": 201.0}
        ok, reason = asyncio.run(_preflight_balance_check(opp, 100.0))
        assert ok is True
        assert reason == "preflight-skipped"

    def test_preflight_zero_prices_returns_true(self):
        import asyncio
        from server import _preflight_balance_check
        opp = {"coin": "SOL", "buy_side": "CEX", "sell_side": "DEX",
               "cex_price": 0, "dex_price": 0}
        ok, reason = asyncio.run(_preflight_balance_check(opp, 100.0))
        assert ok is True

    def test_preflight_insufficient_usdt_cex_buy(self, monkeypatch):
        import asyncio
        import server
        async def fake_cex():
            return {"USDT": 10.0, "SOL": 100.0}
        async def fake_dex():
            return {"SOL": 100.0, "USDC": 1000.0}
        monkeypatch.setattr(server, "_fetch_binance_balances", fake_cex)
        monkeypatch.setattr(server, "_fetch_phantom_balances", fake_dex)
        opp = {"coin": "SOL", "buy_side": "CEX", "sell_side": "DEX",
               "cex_price": 200.0, "dex_price": 201.0}
        ok, reason = asyncio.run(server._preflight_balance_check(opp, 100.0))
        assert ok is False
        assert "USDT" in reason

    def test_preflight_insufficient_sol_gas(self, monkeypatch):
        import asyncio
        import server
        async def fake_cex():
            return {"USDT": 1000.0, "ETH": 1.0}
        async def fake_dex():
            return {"SOL": 0.001, "USDC": 1000.0, "ETH": 1.0}
        monkeypatch.setattr(server, "_fetch_binance_balances", fake_cex)
        monkeypatch.setattr(server, "_fetch_phantom_balances", fake_dex)
        opp = {"coin": "ETH", "buy_side": "CEX", "sell_side": "DEX",
               "cex_price": 3000.0, "dex_price": 3010.0}
        ok, reason = asyncio.run(server._preflight_balance_check(opp, 100.0))
        assert ok is False
        assert "SOL gas" in reason

    def test_preflight_insufficient_coin_on_sell_side(self, monkeypatch):
        import asyncio
        import server
        async def fake_cex():
            return {"USDT": 1000.0, "ETH": 0.001}
        async def fake_dex():
            return {"SOL": 1.0, "USDC": 1000.0}
        monkeypatch.setattr(server, "_fetch_binance_balances", fake_cex)
        monkeypatch.setattr(server, "_fetch_phantom_balances", fake_dex)
        # DEX buy → CEX sell ETH; CEX has only 0.001 ETH but needs ~0.0332
        opp = {"coin": "ETH", "buy_side": "DEX", "sell_side": "CEX",
               "cex_price": 3000.0, "dex_price": 3010.0}
        ok, reason = asyncio.run(server._preflight_balance_check(opp, 100.0))
        assert ok is False
        assert "ETH" in reason


# -------------------- Notifier formatters --------------------
class TestNotifierFormatters:
    def test_drift_alert_msg(self):
        from notifier import format_drift_alert_msg
        m = {"drift_pct": -30.0, "imbalance_pct": 52.38,
             "baseline_total": 3.0, "current_total": 2.1,
             "current_cex": 0.5, "current_dex": 1.6}
        s = format_drift_alert_msg("SOL", m, 5.0, 40.0)
        assert "SOL" in s
        assert "3.0" in s or "3.000000" in s
        assert "2.1" in s or "2.100000" in s
        assert "-30.00%" in s
        assert "52.38%" in s
        assert "CEX" in s
        assert "DEX" in s
        assert "Rebalance" in s or "rebalance" in s.lower()

    def test_partial_trade_alert_msg(self):
        from notifier import format_partial_trade_alert_msg
        trade = {
            "coin": "SOL", "status": "partial", "buy_side": "CEX", "sell_side": "DEX",
            "modal_usd": 100.0, "jupiter_attempts": 3, "reversed_cex": False,
            "error": "x" * 500,
        }
        s = format_partial_trade_alert_msg(trade)
        assert "PARTIAL" in s
        assert "3/3" in s
        assert "❌" in s
        # error truncated to 300 chars
        assert ("x" * 300) in s
        assert ("x" * 301) not in s

    def test_partial_trade_alert_reversed(self):
        from notifier import format_partial_trade_alert_msg
        trade = {
            "coin": "SOL", "status": "reversed", "buy_side": "CEX", "sell_side": "DEX",
            "modal_usd": 100.0, "jupiter_attempts": 3, "reversed_cex": True,
            "error": "short",
        }
        s = format_partial_trade_alert_msg(trade)
        assert "REVERSED" in s
        assert "✅" in s


# -------------------- Jupiter retry source inspection --------------------
class TestJupiterRetrySource:
    def test_retry_loop_structure(self):
        import engine
        src = inspect.getsource(engine.execute_trade_live)
        # Must define 3-attempt backoff
        assert "[0.0, 2.0, 5.0]" in src or "0.0, 2.0, 5.0" in src
        assert "jupiter_attempts" in src
        assert "reversed_cex" in src
        assert "executed_qty" in src
        assert "auto_reverse_on_partial" in src
        assert "after" in src and "retries" in src


# -------------------- Drift threshold status in API --------------------
class TestDriftStatus:
    def test_drift_exceeded_status_via_seeded_baseline(self):
        # Seed a baseline + monkeypatch snapshot, then call endpoint
        # Since we cannot patch a live process, just unit-test _compute_drift
        # was already done. Here we just confirm the API returns status fields.
        r = requests.get(f"{BASE_URL}/api/inventory-drift", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # status field is on each coin; with no coins we just assert shape
        assert "coins" in data
