import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { DASHBOARD } from "@/constants/testIds";
import { Activity, Settings as Gear, Zap as Lightning, Bot as Robot } from "lucide-react";


import { toast } from "sonner";

export default function TopBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const [settings, setSettings] = useState({ paper_mode: true, auto_exec: false });

  const load = async () => {
    try {
      const s = await api.settings();
      setSettings(s);
    } catch (e) {
      console.error("TopBar.loadSettings failed:", e);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const toggle = async (key) => {
    try {
      const next = !settings[key];
      await api.saveSettings({ [key]: next });
      setSettings({ ...settings, [key]: next });
      toast.success(`${key === "paper_mode" ? (next ? "PAPER" : "LIVE") : key === "auto_exec" ? (next ? "AUTO" : "MANUAL") : (next ? "BOT ON" : "BOT OFF")} mode activated`);
    } catch (e) {
      toast.error("Failed to update mode");
    }
  };

  const isDashboard = location.pathname === "/";

  return (
    <header
      className="sticky top-0 z-20 bg-[#060709] border-b border-[#1E2229]"
      style={{ backdropFilter: "blur(8px)" }}
    >
      <div className="w-full max-w-[1600px] mx-auto px-4 md:px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 border border-[#1E2229] bg-[#0C0E12]">
            <Robot size={18} weight="bold" color="#00FF66" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-wider uppercase">
              ARB<span className="text-[#00FF66]">.</span>TERMINAL
            </div>
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
              CEX × DEX × Solana
            </div>
          </div>
        </div>

        <nav className="hidden md:flex items-center gap-2 text-xs font-mono uppercase tracking-[0.12em]">
          <Link
            to="/"
            data-testid={DASHBOARD.navDashboardLink}
            className={`px-3 py-1.5 border ${
              isDashboard ? "border-[#00FF66] text-[#00FF66]" : "border-[#1E2229] text-[#94A3B8] hover:bg-[#13161C]"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <Activity size={12} weight="bold" /> Dashboard
            </span>
          </Link>
          <Link
            to="/settings"
            data-testid={DASHBOARD.navSettingsLink}
            className={`px-3 py-1.5 border ${
              !isDashboard ? "border-[#00FF66] text-[#00FF66]" : "border-[#1E2229] text-[#94A3B8] hover:bg-[#13161C]"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              <Gear size={12} weight="bold" /> Settings
            </span>
          </Link>
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => toggle("bot_enabled")}
            data-testid="nav-bot-onoff-switcher"
            className="flex items-center border font-mono text-[10px] uppercase tracking-[0.18em]"
            style={{ borderColor: settings.bot_enabled ? "#00FF66" : "#FF3333" }}
            title="Master ON/OFF (scanner stays running)"
          >
            <span className={`px-2.5 py-1 ${settings.bot_enabled ? "bg-[#00FF66] text-black" : "text-[#475569]"}`}>
              ON
            </span>
            <span className={`px-2.5 py-1 border-l ${!settings.bot_enabled ? "bg-[#FF3333] text-black" : "text-[#475569]"}`}
              style={{ borderColor: settings.bot_enabled ? "#00FF66" : "#FF3333" }}>
              OFF
            </span>
          </button>

          <button
            type="button"
            onClick={() => toggle("paper_mode")}
            data-testid={DASHBOARD.navPaperLiveSwitch}
            className="flex items-center border border-[#1E2229] font-mono text-[10px] uppercase tracking-[0.18em]"
            title="Toggle Paper / Live"
          >
            <span className={`px-2.5 py-1 ${settings.paper_mode ? "bg-[#00D1FF] text-black" : "text-[#475569]"}`}>
              Paper
            </span>
            <span className={`px-2.5 py-1 border-l border-[#1E2229] ${!settings.paper_mode ? "bg-[#FF3333] text-black" : "text-[#475569]"}`}>
              Live
            </span>
          </button>

          <button
            type="button"
            onClick={() => toggle("auto_exec")}
            data-testid={DASHBOARD.navAutoManualSwitch}
            className="flex items-center border border-[#1E2229] font-mono text-[10px] uppercase tracking-[0.18em]"
            title="Toggle Auto / Manual"
          >
            <span className={`px-2.5 py-1 ${!settings.auto_exec ? "bg-[#94A3B8] text-black" : "text-[#475569]"}`}>
              Manual
            </span>
            <span className={`px-2.5 py-1 border-l border-[#1E2229] ${settings.auto_exec ? "bg-[#00FF66] text-black" : "text-[#475569]"}`}>
              Auto
            </span>
          </button>
        </div>
      </div>
    </header>
  );
}
