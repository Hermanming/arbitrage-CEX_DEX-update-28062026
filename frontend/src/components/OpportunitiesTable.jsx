import { useState } from "react";
import { DASHBOARD } from "@/constants/testIds";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Zap as Lightning } from "lucide-react";

export default function OpportunitiesTable({ opportunities, onTraded }) {
  const [executing, setExecuting] = useState(null);
  const top = (opportunities || []).filter((o) => o.actionable).slice(0, 8);

  const execute = async (opp) => {
    setExecuting(opp.id);
    try {
      const trade = await api.execute(opp.id);
      const profit = trade.profit_usd ?? 0;
      toast.success(
        `${trade.coin} executed · ${profit >= 0 ? "+" : ""}$${profit.toFixed(4)}`
      );
      onTraded && onTraded();
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message || "Execute failed";
      toast.error(msg);
    } finally {
      setExecuting(null);
    }
  };

  return (
    <div className="border border-[#1E2229] bg-[#0C0E12]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
          Live Opportunities · Actionable
        </div>
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#00FF66]">
          {top.length} signals
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569]">
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Asset</th>
              <th className="text-left px-4 py-2 border-b border-[#1E2229]">Direction</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Buy</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Sell</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Net %</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Est. $</th>
              <th className="text-right px-4 py-2 border-b border-[#1E2229]">Action</th>
            </tr>
          </thead>
          <tbody>
            {top.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center text-[#475569] py-8 font-mono text-xs">
                  No signals above threshold.
                </td>
              </tr>
            )}
            {top.map((o) => (
              <tr
                key={o.id}
                data-testid={DASHBOARD.tableOpportunityRow}
                className="hover:bg-[#13161C] border-b border-[#1E2229]"
              >
                <td className="px-4 py-2.5 font-semibold">{o.coin}</td>
                <td className="px-4 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em] text-[#00D1FF]">
                  {o.buy_side} → {o.sell_side}
                </td>
                <td className="px-4 py-2.5 text-right font-mono">
                  ${(o.buy_side === "CEX" ? o.cex_price : o.dex_price).toFixed(6)}
                </td>
                <td className="px-4 py-2.5 text-right font-mono">
                  ${(o.sell_side === "CEX" ? o.cex_price : o.dex_price).toFixed(6)}
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-[#00FF66]">
                  {o.net_profit_pct.toFixed(4)}%
                </td>
                <td className="px-4 py-2.5 text-right font-mono text-[#00FF66]">
                  ${o.est_profit_usd.toFixed(4)}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    type="button"
                    data-testid={DASHBOARD.btnManualExecute}
                    onClick={() => execute(o)}
                    disabled={executing === o.id}
                    className="inline-flex items-center gap-1 px-3 py-1 border border-[#00FF66] text-[#00FF66] font-mono text-[11px] uppercase tracking-[0.15em] hover:bg-[#00FF66] hover:text-black disabled:opacity-50"
                  >
                    <Lightning size={11} weight="bold" />
                    {executing === o.id ? "…" : "Execute"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
