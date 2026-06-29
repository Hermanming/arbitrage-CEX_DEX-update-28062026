import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import { api } from "@/lib/api";

// Module-level constants — avoid re-creating these on every render
const CHART_MARGIN = { top: 8, right: 16, left: 4, bottom: 4 };
const AXIS_TICK = { fontSize: 10, fontFamily: "IBM Plex Mono" };
const AXIS_LINE = { stroke: "#1E2229" };

function fmtTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="border border-[#1E2229] bg-[#0C0E12] px-3 py-2 font-mono text-xs">
      <div className="text-[#94A3B8]">{new Date(p.ts).toLocaleString()}</div>
      <div className="text-[#FFFFFF] mt-1">
        Cum: <span className={p.cumulative >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"}>
          ${p.cumulative.toFixed(4)}
        </span>
      </div>
      <div className="text-[#94A3B8]">
        {p.coin} ·{" "}
        <span className={p.trade_pnl >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"}>
          {p.trade_pnl >= 0 ? "+" : ""}${p.trade_pnl.toFixed(4)}
        </span>
      </div>
    </div>
  );
}

export default function ProfitChart() {
  const [data, setData] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        const series = await api.profitSeries();
        setData(series);
      } catch (e) {
        console.error("ProfitChart.load failed:", e);
      }
    };
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, []);

  const last = data.length ? data[data.length - 1].cumulative : 0;
  const color = last >= 0 ? "#00FF66" : "#FF3333";

  return (
    <div className="border border-[#1E2229] bg-[#0C0E12]">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E2229]">
        <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
          Cumulative Profit · Lifetime
        </div>
        <div className="text-[10px] font-mono uppercase tracking-[0.18em]">
          <span className="text-[#475569]">Current: </span>
          <span className={last >= 0 ? "text-[#00FF66]" : "text-[#FF3333]"}>
            ${last.toFixed(4)}
          </span>
        </div>
      </div>
      <div className="p-2 md:p-4 h-[240px]">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-[#475569] font-mono text-xs">
            No data yet · execute a trade to populate the curve
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={CHART_MARGIN}>
              <CartesianGrid stroke="#1E2229" strokeDasharray="3 3" />
              <XAxis
                dataKey="ts"
                tickFormatter={fmtTime}
                stroke="#475569"
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={AXIS_LINE}
              />
              <YAxis
                stroke="#475569"
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={AXIS_LINE}
                width={50}
                tickFormatter={(v) => `$${Number(v).toFixed(2)}`}
              />
              <ReferenceLine y={0} stroke="#1E2229" strokeWidth={1} />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="cumulative"
                stroke={color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
