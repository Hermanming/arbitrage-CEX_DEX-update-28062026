import { useEffect, useRef } from "react";
import { DASHBOARD } from "@/constants/testIds";
import { ArrowUp, ArrowDown, Minus } from "lucide-react";

function formatPrice(p) {
  if (p === null || p === undefined) return "—";
  if (p >= 100) return p.toFixed(2);
  if (p >= 1) return p.toFixed(4);
  return p.toFixed(8);
}

export default function ScreeningTable({ prices, opportunities }) {
  const prevRef = useRef({});
  const flashRef = useRef({});

  // Track flashes per coin
  useEffect(() => {
    const next = { ...flashRef.current };
    for (const p of prices || []) {
      const prev = prevRef.current[p.coin] || {};
      next[p.coin] = next[p.coin] || {};
      if (prev.binance !== undefined && p.binance !== undefined && p.binance !== prev.binance) {
        next[p.coin].binance = p.binance > prev.binance ? "up" : "down";
      } else {
        next[p.coin].binance = null;
      }
      if (prev.jupiter !== undefined && p.jupiter !== undefined && p.jupiter !== prev.jupiter) {
        next[p.coin].jupiter = p.jupiter > prev.jupiter ? "up" : "down";
      } else {
        next[p.coin].jupiter = null;
      }
      prevRef.current[p.coin] = { binance: p.binance, jupiter: p.jupiter };
    }
    flashRef.current = next;
  }, [prices]);

  const oppMap = {};
  for (const o of opportunities || []) {
    if (!oppMap[o.coin]) oppMap[o.coin] = o;
  }

  const rows = (prices || []).slice().sort((a, b) => {
    const oa = oppMap[a.coin]?.net_profit_pct ?? -999;
    const ob = oppMap[b.coin]?.net_profit_pct ?? -999;
    return ob - oa;
  });

  return (
    <div className="border border-[#1E2229] bg-[#0C0E12]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
          Realtime Screening · CEX × DEX
        </div>
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
          Polling 4s
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569]">
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Asset</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Binance (CEX)</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Jupiter (DEX)</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Spread %</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Net Profit %</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Est. Profit</th>
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Route</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center text-[#475569] py-8 font-mono text-xs">
                  Awaiting price feed…
                </td>
              </tr>
            )}
            {rows.map((p) => {
              const opp = oppMap[p.coin];
              const np = opp?.net_profit_pct;
              const npColor = np === undefined ? "text-[#475569]" : np > 0 ? "text-[#00FF66]" : "text-[#FF3333]";
              const flashB = flashRef.current[p.coin]?.binance;
              const flashJ = flashRef.current[p.coin]?.jupiter;
              return (
                <tr
                  key={p.coin}
                  data-testid={DASHBOARD.tableScreeningRow}
                  className="hover:bg-[#13161C] border-b border-[#1E2229]"
                >
                  <td className="px-4 py-2.5 font-semibold tracking-wide">{p.coin}</td>
                  <td className={`px-4 py-2.5 text-right font-mono ${flashB === "up" ? "flash-up" : flashB === "down" ? "flash-down" : ""}`}>
                    {p.binance ? `$${formatPrice(p.binance)}` : "—"}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono ${flashJ === "up" ? "flash-up" : flashJ === "down" ? "flash-down" : ""}`}>
                    {p.jupiter ? `$${formatPrice(p.jupiter)}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-[#94A3B8]">
                    {opp ? `${opp.spread_pct.toFixed(4)}%` : "—"}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono ${npColor}`}>
                    {opp ? `${np.toFixed(4)}%` : "—"}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono ${npColor}`}>
                    {opp ? `$${opp.est_profit_usd.toFixed(4)}` : "—"}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em]">
                    {opp ? (
                      <span className="inline-flex items-center gap-1 text-[#94A3B8]">
                        {opp.buy_side}
                        <ArrowDown size={10} weight="bold" />
                        {opp.sell_side}
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
    </div>
  );
}
