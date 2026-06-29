import { useEffect, useState, useCallback } from "react";
import StatsCards from "@/components/StatsCards";
import ScreeningTable from "@/components/ScreeningTable";
import OpportunitiesTable from "@/components/OpportunitiesTable";
import TradeHistoryTable from "@/components/TradeHistoryTable";
import ProfitChart from "@/components/ProfitChart";
import { api } from "@/lib/api";

export default function Dashboard() {
  const [stats, setStats] = useState({});
  const [prices, setPrices] = useState([]);
  const [opps, setOpps] = useState([]);
  const [trades, setTrades] = useState([]);

  const loadAll = useCallback(async (full = false) => {
    try {
      const [s, p, o] = await Promise.all([
        api.stats(),
        api.prices(),
        api.opportunities(),
      ]);
      setStats(s);
      setPrices(p);
      setOpps(o);
      if (full) {
        const t = await api.trades();
        setTrades(t);
      }
    } catch (e) {
      console.error("Dashboard.loadAll failed:", e);
    }
  }, []);

  const loadTrades = useCallback(async () => {
    try {
      const t = await api.trades();
      setTrades(t);
    } catch (e) {
      console.error("Dashboard.loadTrades failed:", e);
    }
  }, []);

  useEffect(() => {
    loadAll(true);
    const polling = setInterval(() => loadAll(false), 4000);
    const histPoll = setInterval(loadTrades, 8000);
    return () => {
      clearInterval(polling);
      clearInterval(histPoll);
    };
  }, [loadAll, loadTrades]);

  return (
    <div className="w-full max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6">
      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#475569]">
          //  COMMAND CENTER
        </div>
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Arbitrage <span className="text-[#00FF66]">Terminal</span>
          </h1>
          <div className="flex items-center gap-3 text-[10px] font-mono uppercase tracking-[0.2em]">
            <div className="text-[#94A3B8]">
              CEX: Binance Spot · DEX: Jupiter (Solana)
            </div>
            <div className="flex items-center gap-1.5 border border-[#1E2229] px-2 py-1">
              <span className={`w-1.5 h-1.5 rounded-full inline-block ${stats?.ws_connected ? "bg-[#00FF66]" : "bg-[#FFB800]"}`} style={{ borderRadius: "50%" }} />
              <span className={stats?.ws_connected ? "text-[#00FF66]" : "text-[#FFB800]"}>
                {stats?.ws_connected ? "WS Live" : "Polling"}
              </span>
            </div>
            {(stats?.daily_pnl !== undefined) && (
              <div className="border border-[#1E2229] px-2 py-1">
                <span className="text-[#475569]">DAILY: </span>
                <span className={`${stats.daily_pnl >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"}`}>
                  {stats.daily_pnl >= 0 ? "+" : ""}${(stats.daily_pnl || 0).toFixed(2)}
                </span>
                <span className="text-[#475569]"> · {stats.daily_trades || 0} tx</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <StatsCards stats={stats} />

      <OpportunitiesTable opportunities={opps} onTraded={loadTrades} />

      <ProfitChart />

      <ScreeningTable prices={prices} opportunities={opps} />

      <TradeHistoryTable trades={trades} />

      <footer className="pt-2 pb-6 text-[10px] font-mono uppercase tracking-[0.2em] text-[#475569]">
        Network latency may affect signal accuracy · Always pre-position balances before LIVE mode.
      </footer>
    </div>
  );
}
