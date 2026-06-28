"""Backend API tests for CEX-DEX Arbitrage Bot."""
import os
import time
import requests
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Load frontend env to get BASE_URL
load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_COINS = ["BONK", "ORCA", "PYTH", "JTO", "RAY", "WIF", "SOL", "JUP",
                  "RENDER", "POPCAT", "MEW", "IO"]


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Basic endpoints ----------
class TestBasics:
    def test_root(self, s):
        r = s.get(f"{API}/")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "cex-dex-arbitrage"
        assert data["status"] == "online"

    def test_coins(self, s):
        r = s.get(f"{API}/coins")
        assert r.status_code == 200
        coins = r.json()
        assert isinstance(coins, list)
        assert set(coins) == set(EXPECTED_COINS)
        assert len(coins) == 12


# ---------- Price polling ----------
class TestPrices:
    def test_prices_structure(self, s):
        # Allow polling to populate
        for _ in range(6):
            r = s.get(f"{API}/prices")
            if r.status_code == 200 and r.json():
                break
            time.sleep(2)
        r = s.get(f"{API}/prices")
        assert r.status_code == 200
        prices = r.json()
        assert isinstance(prices, list)
        assert len(prices) == 12
        coins = {p["coin"] for p in prices}
        assert coins == set(EXPECTED_COINS)
        for p in prices:
            assert "coin" in p
            assert "binance" in p
            assert "jupiter" in p
            assert "ts" in p

    def test_prices_have_some_data(self, s):
        r = s.get(f"{API}/prices")
        prices = r.json()
        with_binance = [p for p in prices if p.get("binance") is not None]
        with_jupiter = [p for p in prices if p.get("jupiter") is not None]
        # At least some coins should have prices
        assert len(with_binance) >= 8, f"Only {len(with_binance)} have Binance prices"
        assert len(with_jupiter) >= 8, f"Only {len(with_jupiter)} have Jupiter prices"


# ---------- Opportunities ----------
class TestOpportunities:
    def test_opportunities_structure(self, s):
        r = s.get(f"{API}/opportunities")
        assert r.status_code == 200
        opps = r.json()
        assert isinstance(opps, list)
        if not opps:
            pytest.skip("No opportunities currently (no overlapping prices)")
        for o in opps:
            for k in ("id", "coin", "buy_side", "sell_side", "spread_pct",
                     "net_profit_pct", "est_profit_usd", "actionable"):
                assert k in o, f"missing {k}"
            assert o["buy_side"] in ("CEX", "DEX")
            assert o["sell_side"] in ("CEX", "DEX")
            assert o["buy_side"] != o["sell_side"]

    def test_opportunities_sorted_desc(self, s):
        r = s.get(f"{API}/opportunities")
        opps = r.json()
        if len(opps) < 2:
            pytest.skip("Need >=2 opps to verify sort")
        for i in range(len(opps) - 1):
            assert opps[i]["net_profit_pct"] >= opps[i + 1]["net_profit_pct"]


# ---------- Stats & Trades ----------
class TestStatsTrades:
    def test_stats(self, s):
        r = s.get(f"{API}/stats")
        assert r.status_code == 200
        d = r.json()
        for k in ("total_profit", "total_trades", "winrate",
                  "live_opportunities", "mode", "auto_exec"):
            assert k in d
        assert d["mode"] in ("paper", "live")
        assert isinstance(d["auto_exec"], bool)

    def test_trades_list(self, s):
        r = s.get(f"{API}/trades")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Settings ----------
class TestSettings:
    def test_get_settings_defaults(self, s):
        r = s.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        for k in ("binance_api_key_masked", "has_binance_key", "paper_mode",
                  "auto_exec", "trade_modal_usd", "threshold_pct", "slippage_pct"):
            assert k in d

    def test_partial_update_settings(self, s):
        # Update risk params
        r = s.post(f"{API}/settings", json={
            "trade_modal_usd": 200,
            "threshold_pct": 0.3,
            "slippage_pct": 0.5,
        })
        assert r.status_code == 200
        g = s.get(f"{API}/settings").json()
        assert g["trade_modal_usd"] == 200
        assert g["threshold_pct"] == 0.3
        assert g["slippage_pct"] == 0.5

    def test_credentials_encrypted_and_masked(self, s):
        r = s.post(f"{API}/settings", json={
            "binance_api_key": "test_key_abc123",
            "binance_api_secret": "test_secret_def456",
        })
        assert r.status_code == 200
        g = s.get(f"{API}/settings").json()
        assert g["has_binance_key"] is True
        m = g["binance_api_key_masked"]
        # Should keep first 4 + last 4 and mask middle
        assert m.startswith("test")
        assert m.endswith("c123")
        assert "*" in m
        # Make sure plain value is not leaked
        assert m != "test_key_abc123"

    def test_paper_mode_toggle(self, s):
        # Toggle off
        r = s.post(f"{API}/settings", json={"paper_mode": False})
        assert r.status_code == 200
        assert s.get(f"{API}/settings").json()["paper_mode"] is False
        # Toggle back on
        s.post(f"{API}/settings", json={"paper_mode": True})
        assert s.get(f"{API}/settings").json()["paper_mode"] is True


# ---------- Execute manual ----------
class TestExecute:
    def test_execute_invalid_opp(self, s):
        r = s.post(f"{API}/execute", json={"opportunity_id": "NONEXISTENT-123"})
        assert r.status_code == 404

    def test_execute_paper_trade(self, s):
        # Ensure paper mode
        s.post(f"{API}/settings", json={"paper_mode": True})
        # Snapshot stats
        before = s.get(f"{API}/stats").json()["total_trades"]
        # Find an opportunity (retry up to 5 times)
        trade = None
        for _ in range(5):
            opps = s.get(f"{API}/opportunities").json()
            if opps:
                opp_id = opps[0]["id"]
                r = s.post(f"{API}/execute", json={"opportunity_id": opp_id})
                if r.status_code == 200:
                    trade = r.json()
                    break
                # Might have expired during the call - retry
            time.sleep(3)
        assert trade is not None, "Could not execute any paper trade"
        assert trade["mode"] == "paper"
        assert "profit_usd" in trade
        assert "id" in trade
        # Verify in trades list
        trades = s.get(f"{API}/trades").json()
        assert any(t["id"] == trade["id"] for t in trades)
        # Verify stats incremented (>= due to possible parallel auto-exec tests)
        after = s.get(f"{API}/stats").json()["total_trades"]
        assert after >= before + 1

    def test_execute_live_without_keys_returns_400(self, s):
        # Clear credentials by setting empty (settings doc unset is required;
        # we'll switch to live and expect 400 because either keys are absent
        # or test infrastructure provides none). Since test credentials were
        # set previously (test_key_abc123), live execution will reach the
        # Binance client with fake creds. To trigger 400 path, we need to
        # ensure phantom_private_key is empty.
        # Get current settings
        before = s.get(f"{API}/settings").json()
        has_phantom = before.get("has_phantom_key", False)
        # Switch to live mode
        s.post(f"{API}/settings", json={"paper_mode": False})
        # Need an opp id
        opp_id = None
        for _ in range(5):
            opps = s.get(f"{API}/opportunities").json()
            if opps:
                opp_id = opps[0]["id"]
                break
            time.sleep(3)
        if not opp_id:
            s.post(f"{API}/settings", json={"paper_mode": True})
            pytest.skip("No opps available")

        r = s.post(f"{API}/execute", json={"opportunity_id": opp_id})
        # Reset
        s.post(f"{API}/settings", json={"paper_mode": True})
        if not has_phantom:
            # No phantom key -> should return 400
            assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text}"
            assert "live" in r.text.lower() or "key" in r.text.lower()
        else:
            # All keys present - may attempt live trade; just ensure not 500-server bug
            assert r.status_code in (200, 400, 404)


# ---------- Telegram ----------
class TestTelegram:
    def test_telegram_without_creds_400(self, s):
        # ensure no telegram creds; settings model lacks delete - we test current state
        cur = s.get(f"{API}/settings").json()
        if cur.get("has_telegram"):
            pytest.skip("Telegram credentials present, cannot test 400 path")
        r = s.post(f"{API}/test-telegram")
        assert r.status_code == 400


# ---------- Auto-exec ----------
class TestAutoExec:
    def test_auto_exec_fires_trades(self, s):
        # Set threshold very low so all opps qualify, enable auto, paper mode
        s.post(f"{API}/settings", json={
            "paper_mode": True,
            "auto_exec": True,
            "threshold_pct": -100,
        })
        before = s.get(f"{API}/stats").json()["total_trades"]
        # Wait for auto exec ticks (loops every 3s, prices polled every 4s)
        time.sleep(12)
        after = s.get(f"{API}/stats").json()["total_trades"]
        # Reset
        s.post(f"{API}/settings", json={
            "auto_exec": False,
            "threshold_pct": 0.5,
        })
        assert after > before, f"Auto-exec did not fire new trades (before={before}, after={after})"
        # Verify trades have trigger=auto
        trades = s.get(f"{API}/trades").json()
        autos = [t for t in trades if t.get("trigger") == "auto"]
        assert autos, "No auto-triggered trade found"


# ---------- Final cleanup ----------
def test_zz_reset_defaults(s):
    s.post(f"{API}/settings", json={
        "paper_mode": True,
        "auto_exec": False,
        "threshold_pct": 0.5,
        "trade_modal_usd": 100,
        "slippage_pct": 0.3,
    })
    g = s.get(f"{API}/settings").json()
    assert g["paper_mode"] is True
    assert g["auto_exec"] is False
    assert g["threshold_pct"] == 0.5
    assert g["trade_modal_usd"] == 100
    assert g["slippage_pct"] == 0.3
