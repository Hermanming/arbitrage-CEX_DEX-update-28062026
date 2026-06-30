import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";

const STATUS_CONFIG = {
  ok: { icon: "🟢", label: "OK", color: "text-[#00FF66]", border: "border-[#00FF66]/40" },
  imbalance_high: { icon: "🟡", label: "IMBALANCE", color: "text-[#FFB020]", border: "border-[#FFB020]/40" },
  drift_exceeded: { icon: "🔴", label: "DRIFT", color: "text-[#FF3333]", border: "border-[#FF3333]/40" },
  no_baseline: { icon: "⚪", label: "NO BASELINE", color: "text-[#475569]", border: "border-[#1E2229]" },
};

function fmtQty(n) {
  if (n === undefined || n === null) return "—";
  const v = Number(n);
  if (v === 0) return "0";
  if (Math.abs(v) >= 1) return v.toFixed(4);
  return v.toFixed(6);
}

function fmtPct(n) {
  if (n === undefined || n === null) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

export default function InventoryHealth() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const r = await api.inventoryDrift();
      setData(r);
    } catch (e) {
      console.error("InventoryHealth.load failed:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);

  const baselineSet = data?.baseline_set;
  const coins = data?.coins || [];

  // Summary counts
  const counts = coins.reduce(
    (acc, c) => {
      acc[c.status] = (acc[c.status] || 0) + 1;
      return acc;
    },
    {}
  );
  const hasIssue = (counts.drift_exceeded || 0) + (counts.imbalance_high || 0) > 0;
  const headerStatus = !baselineSet
    ? STATUS_CONFIG.no_baseline
    : hasIssue
    ? counts.drift_exceeded
      ? STATUS_CONFIG.drift_exceeded
      : STATUS_CONFIG.imbalance_high
    : STATUS_CONFIG.ok;

  return (
    <div className="border border-[#1E2229] bg-[#0C0E12]" data-testid="inventory-health-card">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
        <div className="flex items-center gap-3">
          <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
            Inventory Health
          </div>
          <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
            CEX ↔ DEX · refresh 30s
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-mono uppercase tracking-[0.18em] ${headerStatus.color}`}>
            {headerStatus.icon} {headerStatus.label}
          </span>
          {data?.drift_alert_pct !== undefined && (
            <span className="text-[10px] font-mono text-[#475569]">
              · drift {data.drift_alert_pct}% · imb {data.imbalance_alert_pct}%
            </span>
          )}
        </div>
      </div>

      <div className="p-4">
        {loading && !data ? (
          <div className="text-[11px] font-mono text-[#475569] py-2">Loading…</div>
        ) : !baselineSet ? (
          <div className="space-y-2">
            <div className="text-[11px] font-mono text-[#94A3B8]">
              ⚪ Baseline belum di-set. Klik <Link to="/settings" className="text-[#FFB020] underline">Settings</Link> → tombol <span className="text-[#FFB020]">"Reset Inventory Baseline"</span> setelah Anda selesai pre-position coin di Binance + Phantom.
            </div>
            <div className="text-[10px] font-mono text-[#475569]">
              Tanpa baseline, drift monitor tidak bisa bandingkan saldo. Bot tetap jalan normal.
            </div>
          </div>
        ) : coins.length === 0 ? (
          <div className="text-[11px] font-mono text-[#475569] py-2">
            Tidak ada saldo terdeteksi di Binance / Phantom. Pastikan API keys di-set & saldo &gt; 0.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569]">
                  <th className="text-left px-2 py-2">Coin</th>
                  <th className="text-right px-2 py-2">CEX (Binance)</th>
                  <th className="text-right px-2 py-2">DEX (Phantom)</th>
                  <th className="text-right px-2 py-2">Total</th>
                  <th className="text-right px-2 py-2">Baseline</th>
                  <th className="text-right px-2 py-2">Drift</th>
                  <th className="text-right px-2 py-2">Imbalance</th>
                  <th className="text-left px-2 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {coins.map((c) => {
                  const cfg = STATUS_CONFIG[c.status] || STATUS_CONFIG.no_baseline;
                  const driftColor =
                    c.drift_pct === null
                      ? "text-[#475569]"
                      : Math.abs(c.drift_pct) > (data?.drift_alert_pct || 5)
                      ? "text-[#FF3333]"
                      : "text-[#94A3B8]";
                  const imbColor =
                    c.imbalance_pct === null
                      ? "text-[#475569]"
                      : c.imbalance_pct > (data?.imbalance_alert_pct || 40)
                      ? "text-[#FFB020]"
                      : "text-[#94A3B8]";
                  return (
                    <tr
                      key={c.coin}
                      data-testid={`inv-row-${c.coin}`}
                      className="border-t border-[#1E2229] hover:bg-[#13161C]"
                    >
                      <td className="px-2 py-2 font-mono font-bold">{c.coin}</td>
                      <td className="px-2 py-2 text-right font-mono text-[11px]">
                        {fmtQty(c.current?.cex_qty)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-[11px]">
                        {fmtQty(c.current?.dex_qty)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-[11px] text-[#FFFFFF]">
                        {fmtQty(c.current?.total_qty)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-[11px] text-[#475569]">
                        {fmtQty(c.baseline?.total_qty)}
                      </td>
                      <td className={`px-2 py-2 text-right font-mono text-[11px] ${driftColor}`}>
                        {fmtPct(c.drift_pct)}
                      </td>
                      <td className={`px-2 py-2 text-right font-mono text-[11px] ${imbColor}`}>
                        {c.imbalance_pct === null ? "—" : `${c.imbalance_pct.toFixed(2)}%`}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-block px-2 py-0.5 border ${cfg.border} ${cfg.color} font-mono text-[9px] uppercase tracking-[0.15em]`}
                        >
                          {cfg.icon} {cfg.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
