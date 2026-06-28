"""Iteration 3 verification: explicit Bug 1/2/2b checks per review request."""
import os
import time
import requests
import pytest
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path("/app/frontend/.env"))
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

FULL_COINS = ["BONK", "ORCA", "PYTH", "JTO", "RAY", "WIF", "SOL", "JUP",
              "RENDER", "POPCAT", "MEW", "IO"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    yield sess
    sess.post(f"{API}/settings", json={
        "enabled_coins": FULL_COINS,
        "auto_exec": False,
        "threshold_pct": 0.5,
        "daily_loss_limit_usd": 0,
        "max_daily_trades": 0,
        "paper_mode": True,
    })


# Bug 1: enabled_coins=[] means NO coins
def test_bug1_empty_enabled_coins_returns_no_opps(s):
    r = s.post(f"{API}/settings", json={"enabled_coins": []})
    assert r.status_code == 200
    settings = s.get(f"{API}/settings").json()
    assert settings["enabled_coins"] == [], f"settings.enabled_coins should be [] got {settings['enabled_coins']}"
    # Wait for engine recompute (poll loop ~4s + WS recompute ~5/sec)
    ok = False
    for _ in range(10):
        time.sleep(1)
        opps = s.get(f"{API}/opportunities").json()
        if opps == []:
            ok = True
            break
    # Reset
    s.post(f"{API}/settings", json={"enabled_coins": FULL_COINS})
    assert ok, "GET /api/opportunities did not return [] within 10s after setting enabled_coins=[]"


# Bug 2: max_daily_trades cap is enforced INSIDE per-opp loop
def test_bug2_max_daily_trades_cap(s):
    baseline = s.get(f"{API}/stats").json()["daily_trades"]
    cap = baseline + 4
    s.post(f"{API}/settings", json={
        "paper_mode": True,
        "auto_exec": True,
        "threshold_pct": -100,
        "daily_loss_limit_usd": 0,
        "max_daily_trades": cap,
        "enabled_coins": FULL_COINS,
    })
    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(2)
        dt = s.get(f"{API}/stats").json()["daily_trades"]
        if dt >= cap:
            break
    time.sleep(8)
    final_dt = s.get(f"{API}/stats").json()["daily_trades"]
    # Disable auto_exec
    s.post(f"{API}/settings", json={
        "auto_exec": False,
        "threshold_pct": 0.5,
        "max_daily_trades": 0,
    })
    # Hold steady after disabling
    time.sleep(5)
    stable_dt = s.get(f"{API}/stats").json()["daily_trades"]
    assert final_dt <= cap, f"cap breached: final={final_dt} cap={cap}"
    assert stable_dt == final_dt, f"trades increased after auto_exec off: {final_dt} -> {stable_dt}"
    assert final_dt > baseline, f"no trades fired (baseline={baseline} final={final_dt})"


# Bug 2b: daily_loss_limit_usd is enforced
def test_bug2b_daily_loss_limit(s):
    baseline = s.get(f"{API}/stats").json()
    base_trades = baseline["daily_trades"]
    s.post(f"{API}/settings", json={
        "paper_mode": True,
        "auto_exec": True,
        "threshold_pct": -100,
        "daily_loss_limit_usd": 0.5,
        "max_daily_trades": 0,
        "enabled_coins": FULL_COINS,
    })
    deadline = time.time() + 25
    while time.time() < deadline:
        time.sleep(2)
        d = s.get(f"{API}/stats").json()
        if d["daily_pnl"] <= -0.5:
            break
    time.sleep(8)
    mid = s.get(f"{API}/stats").json()
    # Hold steady
    time.sleep(8)
    late = s.get(f"{API}/stats").json()
    # Reset
    s.post(f"{API}/settings", json={
        "auto_exec": False,
        "threshold_pct": 0.5,
        "daily_loss_limit_usd": 0,
    })
    # daily_pnl must be <= -0.5 (i.e. limit triggered) OR no trades qualified
    # AND daily_trades should not grow without bound after the cap is hit.
    assert late["daily_trades"] - mid["daily_trades"] <= 1, (
        f"daily_trades kept growing after loss cap: mid={mid['daily_trades']} late={late['daily_trades']}"
    )


# Regression: previous endpoints still work
def test_regression_endpoints(s):
    r = s.get(f"{API}/profit-series")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    stats = s.get(f"{API}/stats").json()
    assert "ws_connected" in stats
    settings = s.get(f"{API}/settings").json()
    assert "all_coins" in settings
    assert set(settings["all_coins"]) == set(FULL_COINS)
    assert len(settings["all_coins"]) == 12
