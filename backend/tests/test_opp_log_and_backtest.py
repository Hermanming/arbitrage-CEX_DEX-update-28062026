"""Tests for opportunity logger + backtest simulator endpoints."""
import os
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://arb-profit-engine-2.preview.emergentagent.com"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- /opportunity-log-stats ---
class TestOpportunityLogStats:
    def test_stats_shape(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/opportunity-log-stats")
        assert r.status_code == 200
        data = r.json()
        assert set(["count", "from_ts", "to_ts", "by_coin"]).issubset(data.keys())
        assert isinstance(data["by_coin"], list)
        if data["count"] > 0:
            for c in data["by_coin"]:
                assert "coin" in c
                assert "count" in c
                assert "avg_spread_pct" in c
                assert "max_spread_pct" in c


# --- /clear-opportunity-log ---
class TestClearOpportunityLog:
    def test_clear_returns_status_and_zeroes_count(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/clear-opportunity-log")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"
        assert "deleted" in body
        # Verify count is now 0
        stats = api_client.get(f"{BASE_URL}/api/opportunity-log-stats").json()
        assert stats["count"] == 0


# --- /backtest-strategies validation ---
class TestBacktestValidation:
    def test_empty_configs_400(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/backtest-strategies", json={"configs": []})
        assert r.status_code == 400
        assert "At least one strategy config required" in r.json().get("detail", "")

    def test_more_than_5_configs_400(self, api_client):
        configs = [{"name": f"S{i}", "threshold_pct": 0.1, "slippage_pct": 0.2} for i in range(6)]
        r = api_client.post(f"{BASE_URL}/api/backtest-strategies", json={"configs": configs})
        assert r.status_code == 400
        assert "Max 5 strategies" in r.json().get("detail", "")

    def test_bad_iso_date_400(self, api_client):
        r = api_client.post(
            f"{BASE_URL}/api/backtest-strategies",
            json={
                "configs": [{"name": "A", "threshold_pct": 0.1, "slippage_pct": 0.2}],
                "from_date": "not-a-date",
            },
        )
        assert r.status_code == 400


# --- /backtest-strategies with empty dataset ---
class TestBacktestEmptyDataset:
    def test_empty_dataset_after_clear(self, api_client):
        api_client.post(f"{BASE_URL}/api/clear-opportunity-log")
        r = api_client.post(
            f"{BASE_URL}/api/backtest-strategies",
            json={"configs": [{"name": "A", "threshold_pct": 0.1, "slippage_pct": 0.2}]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["opportunities_count"] == 0
        assert body["results"] == []
        assert body["winner"] is None


# --- Seeded backtest correctness ---
@pytest.fixture
def seeded_opps():
    """Seed 6 synthetic opportunity_log docs and clean up after."""
    import asyncio
    base_ts = datetime.now(timezone.utc) - timedelta(hours=2)
    docs = [
        # coin, offset_seconds, spread_pct, modal_usd
        {"coin": "SOL", "off": 0, "spread": 0.6, "modal": 100.0},
        {"coin": "SOL", "off": 10, "spread": 0.7, "modal": 100.0},  # within 30s of prev -> throttled
        {"coin": "SOL", "off": 60, "spread": 0.9, "modal": 100.0},  # not throttled
        {"coin": "JUP", "off": 5, "spread": 1.2, "modal": 100.0},
        {"coin": "JUP", "off": 200, "spread": 0.4, "modal": 100.0},  # below threshold for 0.5 net but check
        {"coin": "RAY", "off": 30, "spread": 0.2, "modal": 100.0},   # too small for any
    ]

    async def seed():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.opportunity_log.delete_many({})
        for d in docs:
            await db.opportunity_log.insert_one({
                "coin": d["coin"],
                "ts": base_ts + timedelta(seconds=d["off"]),
                "cex_price": 100.0,
                "dex_price": 101.0,
                "buy_side": "CEX",
                "sell_side": "DEX",
                "spread_pct": d["spread"],
                "modal_usd": d["modal"],
            })
        client.close()

    async def cleanup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        await db.opportunity_log.delete_many({})
        client.close()

    asyncio.get_event_loop().run_until_complete(seed())
    yield docs
    asyncio.get_event_loop().run_until_complete(cleanup())


class TestBacktestCorrectness:
    def test_seeded_backtest(self, api_client, seeded_opps):
        # Run with 3 configs
        configs = [
            {"name": "Aggro", "threshold_pct": 0.1, "slippage_pct": 0.2},
            {"name": "Mid", "threshold_pct": 0.3, "slippage_pct": 0.2},
            {"name": "Cons", "threshold_pct": 0.5, "slippage_pct": 0.2},
        ]
        r = api_client.post(f"{BASE_URL}/api/backtest-strategies", json={"configs": configs})
        assert r.status_code == 200
        body = r.json()
        assert body["opportunities_count"] == 6
        assert len(body["results"]) == 3

        # Fee total = 0.1 (binance) + 0.25 (jupiter) + 0.2 (slippage) = 0.55
        # net = spread - 0.55
        # Aggro threshold 0.1: net >= 0.1 -> spread >= 0.65
        #   SOL@0.6 -> net 0.05, skip
        #   SOL@0.7 -> net 0.15 OK, ts +10s
        #   SOL@0.9 -> net 0.35 OK, ts +60s (>30s after +10)
        #   JUP@1.2 -> net 0.65 OK
        #   JUP@0.4 -> net -0.15 skip
        #   RAY@0.2 -> net -0.35 skip
        # Total trades = 3
        aggro = next(r for r in body["results"] if r["name"] == "Aggro")
        assert aggro["total_trades"] == 3, f"Aggro trades wrong: {aggro}"
        # SOL profits: (0.15/100)*100 + (0.35/100)*100 = 0.15 + 0.35 = 0.50
        # JUP profit: (0.65/100)*100 = 0.65
        # Total = 1.15
        assert abs(aggro["total_profit"] - 1.15) < 0.01, f"Aggro profit: {aggro['total_profit']}"
        assert aggro["best_coin"]["coin"] == "JUP"
        # winner is Aggro since highest profit
        assert body["winner"] == "Aggro"

        # Mid threshold 0.3: net >= 0.3 -> spread >= 0.85
        # SOL@0.9 -> 0.35 OK; JUP@1.2 -> 0.65 OK -> 2 trades
        mid = next(r for r in body["results"] if r["name"] == "Mid")
        assert mid["total_trades"] == 2

        # Cons threshold 0.5: net >= 0.5 -> spread >= 1.05
        # JUP@1.2 OK only -> 1 trade
        cons = next(r for r in body["results"] if r["name"] == "Cons")
        assert cons["total_trades"] == 1

    def test_date_range_filter(self, api_client, seeded_opps):
        # Get the from_ts/to_ts from stats first
        stats = api_client.get(f"{BASE_URL}/api/opportunity-log-stats").json()
        # Use a very narrow range covering only the first doc
        from_dt = datetime.fromisoformat(stats["from_ts"].replace("Z", "+00:00"))
        to_dt = from_dt + timedelta(seconds=15)
        r = api_client.post(
            f"{BASE_URL}/api/backtest-strategies",
            json={
                "configs": [{"name": "A", "threshold_pct": 0.0, "slippage_pct": 0.2}],
                "from_date": from_dt.isoformat(),
                "to_date": to_dt.isoformat(),
            },
        )
        assert r.status_code == 200
        body = r.json()
        # Within first 15 seconds: SOL@0 (off=0), SOL@10 (off=10), JUP@5 (off=5) -> 3 opps
        assert body["opportunities_count"] == 3


# --- TTL index verification ---
class TestTTLIndex:
    def test_ttl_index_exists(self):
        import asyncio
        async def check():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            idx = await db.opportunity_log.index_information()
            client.close()
            return idx

        idx = asyncio.get_event_loop().run_until_complete(check())
        # Find an index with expireAfterSeconds=604800 on 'ts'
        found = False
        for name, info in idx.items():
            if info.get("expireAfterSeconds") == 7 * 86400:
                keys = info.get("key", [])
                if any(k[0] == "ts" for k in keys):
                    found = True
                    break
        assert found, f"TTL index on 'ts' with 7d not found. Indexes: {idx}"
