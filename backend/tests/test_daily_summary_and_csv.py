"""Tests for Daily Summary + CSV export features (iteration 5)."""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Ensure backend imports work
sys.path.insert(0, "/app/backend")
from notifier import format_daily_summary_msg  # noqa: E402

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if "REACT_APP_BACKEND_URL" in os.environ else None
# fall back to frontend .env
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

API = f"{BASE_URL}/api"
WIB = ZoneInfo("Asia/Jakarta")

MONGO_URL = None
DB_NAME = None
with open("/app/backend/.env") as f:
    for line in f:
        line = line.strip()
        if line.startswith("MONGO_URL="):
            MONGO_URL = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("DB_NAME="):
            DB_NAME = line.split("=", 1)[1].strip().strip('"')


# ---------- daily-summary endpoint ----------

class TestDailySummaryEndpoint:
    def test_get_daily_summary_default_yesterday(self):
        r = requests.get(f"{API}/daily-summary", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # All required keys present
        for k in [
            "day_label", "wib_date", "total_profit", "total_trades",
            "wins", "losses", "winrate", "best_coin", "worst_coin", "per_coin"
        ]:
            assert k in data, f"missing key {k}"
        # Default is YESTERDAY WIB
        expected = (datetime.now(WIB).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)).strftime("%Y-%m-%d")
        assert data["wib_date"] == expected, f"expected {expected} got {data['wib_date']}"
        assert isinstance(data["per_coin"], list)

    def test_get_daily_summary_specific_date(self):
        r = requests.get(f"{API}/daily-summary", params={"date": "2025-01-15"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["wib_date"] == "2025-01-15"
        assert data["day_label"].startswith("2025-01-15")

    def test_get_daily_summary_bad_date(self):
        r = requests.get(f"{API}/daily-summary", params={"date": "bad"}, timeout=15)
        assert r.status_code == 400
        assert r.json().get("detail") == "date must be YYYY-MM-DD"

    def test_post_test_daily_summary_no_creds(self):
        # Assumes no telegram creds configured (paper mode, fresh env)
        r = requests.post(f"{API}/test-daily-summary", timeout=15)
        # Either credentials are set (should not be in test env) or 400
        if r.status_code == 200:
            pytest.skip("Telegram creds appear to be set; cannot test 400 path")
        assert r.status_code == 400
        assert r.json().get("detail") == "Telegram credentials not set"


# ---------- aggregation correctness ----------

def _aggregation_correctness():
    """Seed trades for today WIB and verify GET /api/daily-summary?date=today aggregates correctly."""
    from pymongo import MongoClient
    sclient = MongoClient(MONGO_URL)
    sdb = sclient[DB_NAME]

    today_wib = datetime.now(WIB).strftime("%Y-%m-%d")
    # Build timestamps inside today's WIB window, store as UTC ISO (matching server)
    day_start = datetime.strptime(today_wib, "%Y-%m-%d").replace(tzinfo=WIB)
    mid = day_start + timedelta(hours=10)
    ts_iso = mid.astimezone(timezone.utc).isoformat()

    tag = f"TEST_{uuid.uuid4().hex[:8]}"
    seed = [
        {"_id": f"{tag}-1", "id": f"{tag}-1", "ts": ts_iso, "coin": "BONK", "profit_usd": 5.0},
        {"_id": f"{tag}-2", "id": f"{tag}-2", "ts": ts_iso, "coin": "BONK", "profit_usd": 3.5},
        {"_id": f"{tag}-3", "id": f"{tag}-3", "ts": ts_iso, "coin": "SOL",  "profit_usd": -2.0},
        {"_id": f"{tag}-4", "id": f"{tag}-4", "ts": ts_iso, "coin": "ETH",  "profit_usd": 1.25},
        {"_id": f"{tag}-5", "id": f"{tag}-5", "ts": ts_iso, "coin": "ETH",  "profit_usd": 0.0},
    ]
    try:
        sdb.trades.insert_many(seed)
        r = requests.get(f"{API}/daily-summary", params={"date": today_wib}, timeout=15)
        assert r.status_code == 200, r.text
        summary = r.json()
        assert summary["wib_date"] == today_wib
        coins_present = {pc["coin"] for pc in summary["per_coin"]}
        assert {"BONK", "SOL", "ETH"}.issubset(coins_present)
        if summary["total_trades"]:
            expected_winrate = round(summary["wins"] / summary["total_trades"] * 100.0, 2)
            assert summary["winrate"] == expected_winrate
        assert summary["best_coin"]["profit"] >= summary["worst_coin"]["profit"]
        profits = [pc["profit"] for pc in summary["per_coin"]]
        assert profits == sorted(profits, reverse=True)
    finally:
        sdb.trades.delete_many({"_id": {"$regex": f"^{tag}-"}})
        sclient.close()


def _aggregation_isolated_clean_day():
    """Use a far-future WIB date with NO trades and seed only our trades for exact assertions."""
    from pymongo import MongoClient
    sclient = MongoClient(MONGO_URL)
    sdb = sclient[DB_NAME]

    future_wib = (datetime.now(WIB) + timedelta(days=30)).strftime("%Y-%m-%d")
    day_start = datetime.strptime(future_wib, "%Y-%m-%d").replace(tzinfo=WIB)
    ts_iso = (day_start + timedelta(hours=5)).astimezone(timezone.utc).isoformat()

    tag = f"TEST_{uuid.uuid4().hex[:8]}"
    seed = [
        {"_id": f"{tag}-1", "id": f"{tag}-1", "ts": ts_iso, "coin": "BONK", "profit_usd": 5.0},
        {"_id": f"{tag}-2", "id": f"{tag}-2", "ts": ts_iso, "coin": "BONK", "profit_usd": 3.5},
        {"_id": f"{tag}-3", "id": f"{tag}-3", "ts": ts_iso, "coin": "SOL",  "profit_usd": -2.0},
        {"_id": f"{tag}-4", "id": f"{tag}-4", "ts": ts_iso, "coin": "ETH",  "profit_usd": 1.25},
    ]
    try:
        sdb.trades.insert_many(seed)
        r = requests.get(f"{API}/daily-summary", params={"date": future_wib}, timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["wib_date"] == future_wib
        assert s["total_trades"] == 4
        assert s["wins"] == 3
        assert s["losses"] == 1
        assert s["total_profit"] == round(5.0 + 3.5 - 2.0 + 1.25, 4)
        assert s["winrate"] == round(3 / 4 * 100.0, 2)
        assert s["best_coin"]["coin"] == "BONK"
        assert s["best_coin"]["profit"] == round(8.5, 4)
        assert s["best_coin"]["trades"] == 2
        assert s["worst_coin"]["coin"] == "SOL"
        assert s["worst_coin"]["profit"] == -2.0
        assert [pc["coin"] for pc in s["per_coin"]] == ["BONK", "ETH", "SOL"]
    finally:
        sdb.trades.delete_many({"_id": {"$regex": f"^{tag}-"}})
        sclient.close()


# ---------- format_daily_summary_msg ----------

class TestFormatDailySummaryMsg:
    def test_format_with_trades(self):
        summary = {
            "day_label": "2025-01-15 (Wed)",
            "wib_date": "2025-01-15",
            "total_profit": 12.3456,
            "total_trades": 4,
            "wins": 3,
            "losses": 1,
            "winrate": 75.0,
            "best_coin": {"coin": "BONK", "profit": 8.5, "trades": 2},
            "worst_coin": {"coin": "SOL", "profit": -2.0, "trades": 1},
            "per_coin": [],
        }
        msg = format_daily_summary_msg(summary)
        assert "Daily Summary" in msg
        assert "2025-01-15 (Wed)" in msg
        assert "Net P&L" in msg
        assert "12.3456" in msg
        assert "Trades" in msg
        assert "Winrate" in msg
        assert "75.00%" in msg
        assert "Best Coin" in msg
        assert "BONK" in msg
        assert "Worst Coin" in msg
        assert "SOL" in msg
        assert "No trades executed today" not in msg

    def test_format_no_trades(self):
        summary = {
            "day_label": "2025-01-16 (Thu)",
            "wib_date": "2025-01-16",
            "total_profit": 0.0,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "winrate": 0.0,
            "best_coin": {},
            "worst_coin": {},
            "per_coin": [],
        }
        msg = format_daily_summary_msg(summary)
        assert "Daily Summary" in msg
        assert "2025-01-16 (Thu)" in msg
        assert "No trades executed today" in msg


# ---------- CSV export ----------

class TestExportTradesCsv:
    def test_csv_headers_and_disposition(self):
        r = requests.get(f"{API}/export-trades-csv", timeout=15)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/csv" in ct.lower(), f"content-type={ct}"
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert "arb-trades-" in cd
        assert cd.endswith('.csv"') or cd.endswith(".csv")

        body = r.text.splitlines()
        assert len(body) >= 1
        header = body[0]
        for col in [
            "ts", "coin", "mode", "buy_side", "sell_side",
            "buy_price", "sell_price", "modal_usd", "spread_pct",
            "net_profit_pct", "profit_usd", "status", "trigger",
        ]:
            assert col in header, f"missing column {col}"

    def test_csv_rows_match_trades(self):
        trades_resp = requests.get(f"{API}/trades", params={"limit": 1000}, timeout=15)
        assert trades_resp.status_code == 200
        trades = trades_resp.json()

        csv_resp = requests.get(f"{API}/export-trades-csv", timeout=15)
        assert csv_resp.status_code == 200
        lines = csv_resp.text.splitlines()
        # header + N rows; N should equal len(trades) (export streams all trades, /trades default 100 but we asked 1000)
        # there could be additional trades created in between, so just check >=
        assert len(lines) - 1 >= 0
        if trades:
            assert len(lines) - 1 >= len(trades) - 5  # tolerate small drift


class TestCsvAfterReset:
    def test_csv_after_reset_has_only_header(self):
        # Reset
        rs = requests.post(f"{API}/reset-stats", timeout=15)
        assert rs.status_code == 200
        # Export
        r = requests.get(f"{API}/export-trades-csv", timeout=15)
        assert r.status_code == 200
        lines = [ln for ln in r.text.splitlines() if ln.strip()]
        assert len(lines) == 1, f"expected only header, got {len(lines)} lines"


# ---------- background task / lifespan ----------

class TestBackgroundTaskRegistered:
    def test_backend_logs_show_tasks_started(self):
        # supervisor log
        import subprocess
        out = subprocess.run(
            ["bash", "-lc", "tail -n 400 /var/log/supervisor/backend.*.log 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        assert "Background tasks started" in out, "Expected 'Background tasks started' in backend logs"

    def test_no_unhandled_daily_summary_errors(self):
        import subprocess
        out = subprocess.run(
            ["bash", "-lc", "tail -n 400 /var/log/supervisor/backend.*.log 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        ).stdout
        # The task name appears in the logger; ensure no uncaught exception trace involves daily_summary_task
        assert "daily_summary_task:" not in out or "ERROR" not in out.split("daily_summary_task:")[0][-200:], \
            "daily_summary_task appears to have raised"


# Sync wrappers so pytest (without pytest-asyncio) can execute the async helpers
def test_aggregation_correctness():
    _aggregation_correctness()


def test_aggregation_isolated_clean_day():
    _aggregation_isolated_clean_day()
