import { DASHBOARD } from "@/constants/testIds";

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export default function TradeHistoryTable({ trades }) {
  return (
    <div className="border border-[#1E2229] bg-[#0C0E12]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
          Trade History
        </div>
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
          {(trades || []).length} records
        </div>
      </div>
      <div className="overflow-x-auto max-h-[420px]">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-[#0C0E12]">
            <tr className="text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569]">
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Time</th>
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Coin</th>
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Mode</th>
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Route</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Modal</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Spread %</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Net %</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">PnL</th>
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Status</th>
            </tr>
          </thead>
          <tbody>
            {(trades || []).length === 0 && (
              <tr>
                <td colSpan={9} className="text-center text-[#475569] py-8 font-mono text-xs">
                  No trades yet. Execute an opportunity to populate.
                </td>
              </tr>
            )}
            {(trades || []).map((t) => {
              const pnl = t.profit_usd ?? 0;
              const color = pnl > 0 ? "text-[#00FF66]" : pnl < 0 ? "text-[#FF3333]" : "text-white";
              return (
                <tr
                  key={t.id}
                  data-testid={DASHBOARD.tableHistoryRow}
                  className="hover:bg-[#13161C] border-b border-[#1E2229]"
                >
                  <td className="px-4 py-2 font-mono text-[11px] text-[#94A3B8]">{fmtTime(t.ts)}</td>
                  <td className="px-4 py-2 font-semibold">{t.coin}</td>
                  <td className="px-4 py-2 font-mono text-[10px] uppercase tracking-[0.15em]">
                    <span
                      className={`px-1.5 py-0.5 border ${
                        t.mode === "paper"
                          ? "border-[#00D1FF] text-[#00D1FF]"
                          : "border-[#FF3333] text-[#FF3333]"
                      }`}
                    >
                      {t.mode}
                    </span>
                  </td>
                  <td className="px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] text-[#94A3B8]">
                    {t.buy_side} → {t.sell_side}
                  </td>
                  <td className="px-4 py-2 text-right font-mono">${(t.modal_usd ?? 0).toFixed(2)}</td>
                  <td className="px-4 py-2 text-right font-mono text-[#94A3B8]">
                    {(t.spread_pct ?? 0).toFixed(4)}%
                  </td>
                  <td className={`px-4 py-2 text-right font-mono ${color}`}>
                    {(t.net_profit_pct ?? 0).toFixed(4)}%
                  </td>
                  <td className={`px-4 py-2 text-right font-mono font-semibold ${color}`}>
                    {pnl >= 0 ? "+" : ""}${pnl.toFixed(4)}
                  </td>
                  <td className="px-4 py-2 font-mono text-[10px] uppercase tracking-[0.15em]">
                    <span
                      className={`${
                        t.status === "filled"
                          ? "text-[#00FF66]"
                          : t.status === "partial"
                          ? "text-[#FFB800]"
                          : "text-[#FF3333]"
                      }`}
                    >
                      {t.status}
                    </span>
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
