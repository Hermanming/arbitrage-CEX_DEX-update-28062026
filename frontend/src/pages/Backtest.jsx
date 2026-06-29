import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const DEFAULT_CONFIGS = [
  { name: "Aggressive", threshold_pct: 0.2, slippage_pct: 0.2 },
  { name: "Balanced", threshold_pct: 0.3, slippage_pct: 0.3 },
  { name: "Conservative", threshold_pct: 0.5, slippage_pct: 0.5 },
];

const STRATEGY_COLORS = ["#00FF66", "#FFB020", "#00D1FF", "#FF3B9A", "#FF3333"];

function fmtTs(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function StatCell({ label, value, color }) {
  return (
    <div className="px-3 py-2 border border-[#1E2229]">
      <div className="text-[9px] font-mono uppercase tracking-[0.18em] text-[#475569]">
        {label}
      </div>
      <div
        className={`mt-0.5 font-mono text-sm ${color || "text-[#FFFFFF]"}`}
      >
        {value}
      </div>
    </div>
  );
}

export default function Backtest() {
  const [logStats, setLogStats] = useState(null);
  const [configs, setConfigs] = useState(DEFAULT_CONFIGS);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [clearing, setClearing] = useState(false);

  const loadStats = async () => {
    try {
      const s = await api.opportunityLogStats();
      setLogStats(s);
    } catch (e) {
      console.error("loadStats:", e);
    }
  };

  useEffect(() => {
    loadStats();
    const t = setInterval(loadStats, 8000);
    return () => clearInterval(t);
  }, []);

  const updateConfig = (idx, field, value) => {
    const next = [...configs];
    next[idx] = { ...next[idx], [field]: value };
    setConfigs(next);
  };

  const runBacktest = async () => {
    // Validate
    for (const c of configs) {
      if (!c.name?.trim()) return toast.error("Setiap strategi harus punya nama");
      if (Number(c.threshold_pct) < 0 || Number(c.slippage_pct) < 0)
        return toast.error("Threshold & slippage harus >= 0");
    }
    setRunning(true);
    try {
      const r = await api.backtestStrategies(
        configs.map((c) => ({
          name: c.name,
          threshold_pct: Number(c.threshold_pct),
          slippage_pct: Number(c.slippage_pct),
        })),
        null,
        null,
      );
      setResult(r);
      if (r.opportunities_count === 0) {
        toast.warning("Belum ada opportunity yang ter-log. Biarkan bot jalan beberapa menit dulu.");
      } else {
        toast.success(
          `Backtest selesai · ${r.opportunities_count} opportunities · winner: ${r.winner || "—"}`
        );
      }
    } catch (e) {
      toast.error("Backtest gagal: " + (e?.response?.data?.detail || e.message));
    } finally {
      setRunning(false);
    }
  };

  const clearLog = async () => {
    if (!window.confirm("Hapus seluruh opportunity log? Ini hanya menghapus data backtest, tidak menyentuh trade history."))
      return;
    setClearing(true);
    try {
      const r = await api.clearOpportunityLog();
      toast.success(`${r.deleted} opportunities dihapus`);
      setResult(null);
      await loadStats();
    } catch (e) {
      toast.error("Gagal clear: " + (e?.response?.data?.detail || e.message));
    } finally {
      setClearing(false);
    }
  };

  const winnerName = result?.winner;

  return (
    <div className="w-full max-w-[1600px] mx-auto px-4 md:px-6 py-6 space-y-6">
      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#475569]">
          //  STRATEGY LAB
        </div>
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Strategy <span className="text-[#FFB020]">Backtest</span>
          </h1>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#94A3B8]">
            Compare up to 5 strategies against live opportunity history
          </div>
        </div>
      </div>

      {/* Dataset Stats */}
      <div className="border border-[#1E2229] bg-[#0C0E12]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
            Opportunity Dataset
          </div>
          <button
            onClick={clearLog}
            disabled={clearing || !logStats?.count}
            data-testid="btn-clear-opp-log"
            className="px-3 py-1.5 border border-[#FF3333] text-[#FF3333] font-mono text-[10px] uppercase tracking-[0.18em] hover:bg-[#FF3333] hover:text-black disabled:opacity-40"
          >
            {clearing ? "Clearing…" : "Clear Log"}
          </button>
        </div>
        <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCell
            label="Total Opportunities"
            value={(logStats?.count ?? 0).toLocaleString()}
            color="text-[#00FF66]"
          />
          <StatCell label="From" value={fmtTs(logStats?.from_ts)} />
          <StatCell label="To" value={fmtTs(logStats?.to_ts)} />
          <StatCell
            label="Unique Coins"
            value={(logStats?.by_coin?.length ?? 0).toString()}
          />
        </div>
        {!!logStats?.by_coin?.length && (
          <div className="px-4 pb-4">
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569] mb-2">
              Per-Coin Sample Size · Avg Spread · Max Spread
            </div>
            <div className="flex flex-wrap gap-2">
              {logStats.by_coin.map((c) => (
                <div
                  key={c.coin}
                  className="border border-[#1E2229] px-2 py-1 font-mono text-[10px]"
                >
                  <span className="text-[#FFFFFF] font-bold">{c.coin}</span>
                  <span className="text-[#475569] mx-1">·</span>
                  <span className="text-[#94A3B8]">{c.count}x</span>
                  <span className="text-[#475569] mx-1">·</span>
                  <span className="text-[#FFB020]">avg {c.avg_spread_pct.toFixed(3)}%</span>
                  <span className="text-[#475569] mx-1">·</span>
                  <span className="text-[#00FF66]">max {c.max_spread_pct.toFixed(3)}%</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Strategy Configs */}
      <div className="border border-[#1E2229] bg-[#0C0E12]">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
            Strategy Configurations
          </div>
          <button
            onClick={runBacktest}
            disabled={running || !logStats?.count}
            data-testid="btn-run-backtest"
            className="px-5 py-2 bg-[#FFB020] text-black font-mono text-xs uppercase tracking-[0.2em] hover:opacity-90 disabled:opacity-40"
          >
            {running ? "Running…" : "▶ Run Backtest"}
          </button>
        </div>
        <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
          {configs.map((c, idx) => (
            <div
              key={idx}
              className="border border-[#1E2229] p-3 space-y-3"
              style={{ borderTopColor: STRATEGY_COLORS[idx], borderTopWidth: 2 }}
            >
              <div className="flex items-center justify-between">
                <input
                  type="text"
                  value={c.name}
                  onChange={(e) => updateConfig(idx, "name", e.target.value)}
                  data-testid={`backtest-name-${idx}`}
                  className="bg-transparent border-b border-[#1E2229] font-mono text-xs uppercase tracking-[0.18em] text-[#FFFFFF] w-full focus:outline-none focus:border-[#FFB020]"
                />
              </div>
              <div className="space-y-2">
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
                    Threshold %
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    value={c.threshold_pct}
                    onChange={(e) => updateConfig(idx, "threshold_pct", e.target.value)}
                    data-testid={`backtest-threshold-${idx}`}
                    className="w-full mt-1 bg-[#0C0E12] border border-[#1E2229] px-2 py-1.5 font-mono text-sm text-[#FFFFFF] focus:outline-none focus:border-[#FFB020]"
                  />
                </div>
                <div>
                  <label className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
                    Slippage %
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    value={c.slippage_pct}
                    onChange={(e) => updateConfig(idx, "slippage_pct", e.target.value)}
                    data-testid={`backtest-slippage-${idx}`}
                    className="w-full mt-1 bg-[#0C0E12] border border-[#1E2229] px-2 py-1.5 font-mono text-sm text-[#FFFFFF] focus:outline-none focus:border-[#FFB020]"
                  />
                </div>
                <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569] pt-1">
                  Spread needed ≥{" "}
                  <span className="text-[#FFB020]">
                    {(0.1 + 0.25 + Number(c.slippage_pct) + Number(c.threshold_pct)).toFixed(2)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="border border-[#1E2229] bg-[#0C0E12]" data-testid="backtest-results">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
            <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
              Backtest Results
            </div>
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
              {result.opportunities_count.toLocaleString()} opportunities · {result.duration_hours}h
              window
              {winnerName && (
                <span>
                  {" · "}
                  <span className="text-[#FFB020]">winner: {winnerName} 🏆</span>
                </span>
              )}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569]">
                  <th className="text-left px-4 py-2 border-b border-[#1E2229]">Strategy</th>
                  <th className="text-right px-4 py-2 border-b border-[#1E2229]">Threshold / Slip</th>
                  <th className="text-right px-4 py-2 border-b border-[#1E2229]">Trades</th>
                  <th className="text-right px-4 py-2 border-b border-[#1E2229]">Total Profit</th>
                  <th className="text-right px-4 py-2 border-b border-[#1E2229]">Avg / Trade</th>
                  <th className="text-right px-4 py-2 border-b border-[#1E2229]">$ / Hour</th>
                  <th className="text-right px-4 py-2 border-b border-[#1E2229]">Proj. Daily</th>
                  <th className="text-left px-4 py-2 border-b border-[#1E2229]">Best Coin</th>
                  <th className="text-left px-4 py-2 border-b border-[#1E2229]">Worst Coin</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r, idx) => {
                  const isWinner = r.name === winnerName;
                  return (
                    <tr
                      key={r.name}
                      data-testid={`backtest-row-${idx}`}
                      className={`hover:bg-[#13161C] border-b border-[#1E2229] ${
                        isWinner ? "bg-[#0F1A12]" : ""
                      }`}
                    >
                      <td className="px-4 py-2.5 font-semibold">
                        <span
                          className="inline-block w-2 h-2 mr-2"
                          style={{ background: STRATEGY_COLORS[idx] }}
                        />
                        {r.name}
                        {isWinner && <span className="ml-2">🏆</span>}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-[#94A3B8]">
                        {r.threshold_pct}% / {r.slippage_pct}%
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono">
                        {r.total_trades.toLocaleString()}
                      </td>
                      <td
                        className={`px-4 py-2.5 text-right font-mono font-bold ${
                          r.total_profit >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"
                        }`}
                      >
                        ${r.total_profit.toFixed(4)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-[#94A3B8]">
                        ${r.avg_per_trade.toFixed(4)}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-[#94A3B8]">
                        ${r.profit_per_hour.toFixed(4)}
                      </td>
                      <td
                        className={`px-4 py-2.5 text-right font-mono ${
                          r.projected_daily_profit >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"
                        }`}
                      >
                        ${r.projected_daily_profit.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-[11px]">
                        {r.best_coin ? (
                          <span className="text-[#00FF66]">
                            {r.best_coin.coin}{" "}
                            <span className="text-[#475569]">
                              (${r.best_coin.profit.toFixed(2)} · {r.best_coin.trades}t)
                            </span>
                          </span>
                        ) : (
                          <span className="text-[#475569]">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-[11px]">
                        {r.worst_coin && r.worst_coin.coin !== r.best_coin?.coin ? (
                          <span className="text-[#FF3333]">
                            {r.worst_coin.coin}{" "}
                            <span className="text-[#475569]">
                              (${r.worst_coin.profit.toFixed(2)} · {r.worst_coin.trades}t)
                            </span>
                          </span>
                        ) : (
                          <span className="text-[#475569]">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Per-coin breakdown for winner */}
          {winnerName && result.results.find((r) => r.name === winnerName)?.per_coin?.length > 0 && (
            <div className="border-t border-[#1E2229] p-4">
              <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569] mb-2">
                Per-Coin Breakdown · {winnerName}
              </div>
              <div className="flex flex-wrap gap-2">
                {result.results
                  .find((r) => r.name === winnerName)
                  .per_coin.map((c) => (
                    <div
                      key={c.coin}
                      className="border border-[#1E2229] px-2 py-1 font-mono text-[10px]"
                    >
                      <span className="text-[#FFFFFF] font-bold">{c.coin}</span>
                      <span className="text-[#475569] mx-1">·</span>
                      <span
                        className={c.profit >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"}
                      >
                        ${c.profit.toFixed(4)}
                      </span>
                      <span className="text-[#475569] mx-1">·</span>
                      <span className="text-[#94A3B8]">{c.trades}t</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569] pb-6">
        ℹ️ Backtest assumes paper-mode 100% fills · Real-world live trading kena hidden cost (network fee, RPC latency, partial fills). Buffer ~0.1-0.2% dari hasil backtest.
      </div>
    </div>
  );
}
