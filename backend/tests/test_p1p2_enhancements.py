"""Backend tests for P1/P2 enhancements: profit-series, enabled_coins filter,
risk caps (daily_loss_limit_usd, max_daily_trades), WebSocket status, daily
metrics."""
import os
import time
import requests
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("/app/frontend/.env"))
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_COINS = ["BONK", "ORCA", "PYTH", "JTO", "RAY", "WIF", "SOL", "JUP",
                  "RENDER", "POPCAT", "MEW", "IO"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    yield sess
    # Final cleanup: restore safe defaults
    sess.post(f"{API}/settings", json={
        "enabled_coins": EXPECTED_COINS,
        "auto_exec": False,
        "threshold_pct": 0.5,
        "daily_loss_limit_usd": 0,
        "max_daily_trades": 0,
        "paper_mode": True,
    })


def _exec_one_paper_trade(s):
    """Helper: ensure paper_mode, fetch opp, execute. Returns trade or None."""
    s.post(f"{API}/settings", json={"paper_mode": True})
    for _ in range(6):
        opps = s.get(f"{API}/opportunities").json()
        if opps:
            r = s.post(f"{API}/execute", json={"opportunity_id": opps[0]["id"]})
            if r.status_code == 200:
                return r.json()
        time.sleep(3)
    return None


# ---------- Settings: new fields exposed ----------
class TestNewSettingsFields:
    def test_settings_exposes_new_fields(self, s):
        # ensure defaults
        s.post(f"{API}/settings", json={
            "enabled_coins": EXPECTED_COINS,
            "daily_loss_limit_usd": 0,
            "max_daily_trades": 0,
        })
        d = s.get(f"{API}/settings").json()
        for k in ("enabled_coins", "daily_loss_limit_usd", "max_daily_trades",
                  "ws_connected", "all_coins"):
            assert k in d, f"missing {k}"
        assert isinstance(d["enabled_coins"], list)
        assert set(d["enabled_coins"]) == set(EXPECTED_COINS)
        assert isinstance(d["all_coins"], list)
        assert set(d["all_coins"]) == set(EXPECTED_COINS)
        assert len(d["all_coins"]) == 12
        assert isinstance(d["ws_connected"], bool)
        assert d["daily_loss_limit_usd"] == 0
        assert d["max_daily_trades"] == 0


# ---------- Stats: new fields ----------
class TestStatsNewFields:
    def test_stats_has_ws_and_daily(self, s):
        d = s.get(f"{API}/stats").json()
        for k in ("ws_connected", "daily_pnl", "daily_trades"):
            assert k in d, f"missing {k}"
        assert isinstance(d["ws_connected"], bool)
        assert isinstance(d["daily_trades"], int)
        assert isinstance(d["daily_pnl"], (int, float))

    def test_ws_connected_becomes_true(self, s):
        # WS connects ~5s after startup; poll up to ~30s
        ok = False
        for _ in range(15):
            d = s.get(f"{API}/stats").json()
            if d.get("ws_connected") is True:
                ok = True
                break
            time.sleep(2)
        assert ok, "ws_connected never became True within 30s"


# ---------- Profit series ----------
class TestProfitSeries:
    def test_profit_series_endpoint_exists(self, s):
        r = s.get(f"{API}/profit-series")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_profit_series_grows_after_execute(self, s):
        before = s.get(f"{API}/profit-series").json()
        before_len = len(before)
        trade = _exec_one_paper_trade(s)
        assert trade is not None, "Could not execute a paper trade"
        after = s.get(f"{API}/profit-series").json()
        assert len(after) >= 1
        assert len(after) >= before_len + 1
        last = after[-1]
        for k in ("ts", "cumulative", "trade_pnl", "coin"):
            assert k in last, f"missing {k}"
        # cumulative should equal running sum
        cum = 0.0
        for pt in after:
            cum += pt["trade_pnl"]
            # tolerance for rounding
            assert abs(pt["cumulative"] - round(cum, 4)) < 0.01, (
                f"cumulative mismatch: {pt['cumulative']} vs running {cum}"
            )


# ---------- Enabled coins filter ----------
class TestEnabledCoinsFilter:
    def test_filter_to_3_coins(self, s):
        sel = ["SOL", "JUP", "BONK"]
        r = s.post(f"{API}/settings", json={"enabled_coins": sel})
        assert r.status_code == 200
        # Give the engine a moment to recompute
        time.sleep(5)
        # Try a few times in case of timing
        ok = False
        for _ in range(5):
            opps = s.get(f"{API}/opportunities").json()
            if opps:
                coins = {o["coin"] for o in opps}
                assert coins.issubset(set(sel)), f"opps leak: {coins}"
                ok = True
                break
            time.sleep(2)
        # Reset
        s.post(f"{API}/settings", json={"enabled_coins": EXPECTED_COINS})
        if not ok:
            pytest.skip("No opps returned during filter window")

    def test_empty_enabled_coins_returns_no_opps(self, s):
        r = s.post(f"{API}/settings", json={"enabled_coins": []})
        assert r.status_code == 200
        # When sent [] - server stores empty list; backend treats falsy as full list.
        # Verify behavior either way: either opps==[] (strict) OR
        # backend falls back to all coins (state.settings or COIN_LIST).
        time.sleep(5)
        opps = s.get(f"{API}/opportunities").json()
        # Per the spec, expected = [] (empty). Record actual.
        settings = s.get(f"{API}/settings").json()
        # Reset before asserting so we always clean up
        s.post(f"{API}/settings", json={"enabled_coins": EXPECTED_COINS})
        # Spec says: enabled_coins=[] -> opps empty
        assert opps == [], (
            f"Expected empty opps when enabled_coins=[], got {len(opps)} "
            f"(settings.enabled_coins={settings.get('enabled_coins')})"
        )


# ---------- Risk caps ----------
class TestRiskCaps:
    def test_risk_caps_persist(self, s):
        r = s.post(f"{API}/settings", json={
            "daily_loss_limit_usd": 5,
            "max_daily_trades": 3,
        })
        assert r.status_code == 200
        d = s.get(f"{API}/settings").json()
        assert d["daily_loss_limit_usd"] == 5
        assert d["max_daily_trades"] == 3
        # cleanup partial done below

    def test_max_daily_trades_cap_enforced(self, s):
        # Reset daily counters by forcing date check via setting and waiting
        # First record baseline daily_trades
        baseline = s.get(f"{API}/stats").json()["daily_trades"]
        cap = baseline + 3  # cap relative to current counter
        # Configure caps + low threshold for auto-exec
        s.post(f"{API}/settings", json={
            "paper_mode": True,
            "auto_exec": True,
            "threshold_pct": -100,
            "daily_loss_limit_usd": 0,
            "max_daily_trades": cap,
        })
        # Watch trades increment but stop at cap
        deadline = time.time() + 25
        last_dt = baseline
        while time.time() < deadline:
            time.sleep(2)
            dt = s.get(f"{API}/stats").json()["daily_trades"]
            last_dt = dt
            if dt >= cap:
                break
        # Wait a bit more to ensure no overshoot
        time.sleep(8)
        final_dt = s.get(f"{API}/stats").json()["daily_trades"]

        # Disable auto_exec & reset caps
        s.post(f"{API}/settings", json={
            "auto_exec": False,
            "threshold_pct": 0.5,
            "daily_loss_limit_usd": 0,
            "max_daily_trades": 0,
        })

        # Assertions: incremented at least once and never exceeded cap
        assert last_dt > baseline, (
            f"daily_trades didn't increment from baseline ({baseline} -> {last_dt})"
        )
        assert final_dt <= cap, (
            f"max_daily_trades cap breached: final={final_dt} > cap={cap}"
        )

    def test_daily_pnl_reflects_today_trades(self, s):
        # daily_pnl is in-memory; after the previous test it should be > 0 for paper
        d = s.get(f"{API}/stats").json()
        # Just confirm it's a numeric value; sign may vary by spread
        assert isinstance(d["daily_pnl"], (int, float))


# ---------- WebSocket smoke check / price freshness ----------
class TestWsPriceFreshness:
    def test_prices_present_and_change(self, s):
        # Ensure prices populated and binance values change over ~15s
        # (WS gives sub-second updates; even fallback 4s poll changes ts)
        first = s.get(f"{API}/prices").json()
        assert isinstance(first, list)
        # take any coin with a binance value
        f_map = {p["coin"]: p for p in first if p.get("binance")}
        assert f_map, "No binance prices in /api/prices"
        time.sleep(15)
        second = s.get(f"{API}/prices").json()
        s_map = {p["coin"]: p for p in second if p.get("binance")}
        # Compare ts/value changes for overlapping coins
        ts_changed = 0
        for c, fp in f_map.items():
            sp = s_map.get(c)
            if not sp:
                continue
            if sp.get("ts") != fp.get("ts") or sp.get("binance") != fp.get("binance"):
                ts_changed += 1
        # At least one price should change in 15s (market is 24/7)
        assert ts_changed >= 1, (
            f"No price changed within 15s window; ws may be stale "
            f"(checked {len(f_map)} coins)"
        )


# ---------- Final cleanup ----------
def test_zz_final_reset(s):
    r = s.post(f"{API}/settings", json={
        "enabled_coins": EXPECTED_COINS,
        "auto_exec": False,
        "threshold_pct": 0.5,
        "daily_loss_limit_usd": 0,
        "max_daily_trades": 0,
        "paper_mode": True,
    })
    assert r.status_code == 200
    d = s.get(f"{API}/settings").json()
    assert d["auto_exec"] is False
    assert d["threshold_pct"] == 0.5
    assert d["daily_loss_limit_usd"] == 0
    assert d["max_daily_trades"] == 0
    assert set(d["enabled_coins"]) == set(EXPECTED_COINS)
