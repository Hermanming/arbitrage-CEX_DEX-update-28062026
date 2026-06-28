import { DASHBOARD } from "@/constants/testIds";

function Stat({ label, value, accent = "text-white", subline, testId }) {
  return (
    <div
      data-testid={testId}
      className="border border-[#1E2229] bg-[#0C0E12] px-4 py-4 md:px-5 md:py-5"
    >
      <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#475569]">
        {label}
      </div>
      <div className={`mt-2 text-2xl md:text-3xl font-mono font-semibold tracking-tight ${accent}`}>
        {value}
      </div>
      {subline && (
        <div className="mt-1 text-[10px] font-mono uppercase tracking-[0.15em] text-[#475569]">
          {subline}
        </div>
      )}
    </div>
  );
}

export default function StatsCards({ stats }) {
  const profit = stats?.total_profit ?? 0;
  const profitColor = profit > 0 ? "text-[#00FF66]" : profit < 0 ? "text-[#FF3333]" : "text-white";
  const winrateColor = (stats?.winrate ?? 0) >= 50 ? "text-[#00FF66]" : "text-[#FFB800]";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 border border-[#1E2229] [&>*]:border-t-0 [&>*]:border-l-0 md:[&>*:nth-child(-n+4)]:border-t-0 [&>*]:border-r [&>*:last-child]:border-r-0 [&>*]:border-b [&>*]:md:border-b-0">
      <Stat
        testId={DASHBOARD.statTotalProfit}
        label="Total Profit"
        value={`$${profit.toFixed(4)}`}
        accent={profitColor}
        subline={profit >= 0 ? "Net realized" : "Drawdown"}
      />
      <Stat
        testId={DASHBOARD.statTotalTrade}
        label="Total Trades"
        value={stats?.total_trades ?? 0}
        accent="text-white"
        subline={`Mode: ${(stats?.mode || "paper").toUpperCase()}`}
      />
      <Stat
        testId={DASHBOARD.statWinrate}
        label="Winrate"
        value={`${(stats?.winrate ?? 0).toFixed(2)}%`}
        accent={winrateColor}
        subline={(stats?.auto_exec ? "AUTO EXEC" : "MANUAL EXEC")}
      />
      <Stat
        testId={DASHBOARD.statLiveOpportunities}
        label="Live Opportunities"
        value={stats?.live_opportunities ?? 0}
        accent={(stats?.live_opportunities ?? 0) > 0 ? "text-[#00D1FF]" : "text-[#475569]"}
        subline="Above threshold"
      />
    </div>
  );
}
