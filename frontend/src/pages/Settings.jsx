import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { SETTINGS } from "@/constants/testIds";
import { toast } from "sonner";
import { Save as FloppyDisk, Send as PaperPlaneTilt, Lock, Eye, EyeOff as EyeSlash } from "lucide-react";

function Field({ label, hint, children }) {
  return (
    <label className="block">
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#94A3B8] mb-1.5">
        {label}
      </div>
      {children}
      {hint && (
        <div className="mt-1 text-[10px] font-mono text-[#475569]">{hint}</div>
      )}
    </label>
  );
}

function SecretInput({ value, onChange, placeholder, testId, currentMasked }) {
  const [reveal, setReveal] = useState(false);
  return (
    <div className="flex items-stretch border border-[#1E2229] focus-within:border-[#333A45]">
      <input
        data-testid={testId}
        type={reveal ? "text" : "password"}
        value={value}
        onChange={onChange}
        placeholder={currentMasked ? `Current: ${currentMasked} · enter to replace` : placeholder}
        className="flex-1 bg-transparent border-0 px-3 py-2 font-mono text-sm placeholder:text-[#475569]"
        style={{ borderRadius: 0 }}
      />
      <button
        type="button"
        onClick={() => setReveal((r) => !r)}
        className="px-2 border-l border-[#1E2229] text-[#94A3B8] hover:bg-[#13161C]"
      >
        {reveal ? <EyeSlash size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
}

export default function Settings() {
  const [s, setS] = useState({
    binance_api_key: "",
    binance_api_secret: "",
    phantom_private_key: "",
    telegram_bot_token: "",
    telegram_chat_id: "",
    trade_modal_usd: 100,
    threshold_pct: 0.5,
    slippage_pct: 0.3,
    paper_mode: true,
    auto_exec: false,
    enabled_coins: [],
    daily_loss_limit_usd: 0,
    max_daily_trades: 0,
  });
  const [current, setCurrent] = useState({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const load = async () => {
    try {
      const data = await api.settings();
      setCurrent(data);
      setS((prev) => ({
        ...prev,
        trade_modal_usd: data.trade_modal_usd ?? 100,
        threshold_pct: data.threshold_pct ?? 0.5,
        slippage_pct: data.slippage_pct ?? 0.3,
        paper_mode: data.paper_mode ?? true,
        auto_exec: data.auto_exec ?? false,
        telegram_chat_id: data.telegram_chat_id ?? "",
        enabled_coins: data.enabled_coins ?? data.all_coins ?? [],
        daily_loss_limit_usd: data.daily_loss_limit_usd ?? 0,
        max_daily_trades: data.max_daily_trades ?? 0,
      }));
    } catch (e) {
      toast.error("Could not load settings");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async (e) => {
    e?.preventDefault();
    setSaving(true);
    try {
      // Only send non-empty secret fields
      const payload = {
        trade_modal_usd: parseFloat(s.trade_modal_usd) || 0,
        threshold_pct: parseFloat(s.threshold_pct) || 0,
        slippage_pct: parseFloat(s.slippage_pct) || 0,
        paper_mode: !!s.paper_mode,
        auto_exec: !!s.auto_exec,
        enabled_coins: s.enabled_coins,
        daily_loss_limit_usd: parseFloat(s.daily_loss_limit_usd) || 0,
        max_daily_trades: parseInt(s.max_daily_trades) || 0,
      };
      if (s.binance_api_key) payload.binance_api_key = s.binance_api_key;
      if (s.binance_api_secret) payload.binance_api_secret = s.binance_api_secret;
      if (s.phantom_private_key) payload.phantom_private_key = s.phantom_private_key;
      if (s.telegram_bot_token) payload.telegram_bot_token = s.telegram_bot_token;
      payload.telegram_chat_id = s.telegram_chat_id || "";

      await api.saveSettings(payload);
      toast.success("Settings saved & encrypted");
      setS((prev) => ({
        ...prev,
        binance_api_key: "",
        binance_api_secret: "",
        phantom_private_key: "",
        telegram_bot_token: "",
      }));
      load();
    } catch (e) {
      toast.error("Save failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    try {
      await api.testTelegram();
      toast.success("Test message sent");
    } catch (e) {
      toast.error("Telegram test failed: " + (e?.response?.data?.detail || e.message));
    } finally {
      setTesting(false);
    }
  };

  const setField = (k) => (e) => setS({ ...s, [k]: e.target.value });
  const setBool = (k) => (e) => setS({ ...s, [k]: e.target.checked });

  const toggleCoin = (coin) => {
    const enabled = new Set(s.enabled_coins);
    if (enabled.has(coin)) enabled.delete(coin);
    else enabled.add(coin);
    setS({ ...s, enabled_coins: Array.from(enabled) });
  };

  const setAllCoins = (on) => {
    setS({ ...s, enabled_coins: on ? (current.all_coins || []) : [] });
  };

  const allCoins = current.all_coins || [];

  return (
    <div className="w-full max-w-[1100px] mx-auto px-4 md:px-6 py-6">
      <div className="space-y-1 mb-6">
        <div className="text-[10px] font-mono uppercase tracking-[0.25em] text-[#475569]">
          //  CONFIGURATION
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
          Settings <span className="text-[#00FF66]">·</span>{" "}
          <span className="text-[#94A3B8] text-base font-normal align-middle">
            Keys & Risk Controls
          </span>
        </h1>
      </div>

      <form onSubmit={save} className="space-y-6">
        {/* Credentials */}
        <section className="border border-[#1E2229] bg-[#0C0E12]">
          <header className="px-4 py-3 border-b border-[#1E2229] flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
              <Lock size={14} weight="bold" /> CEX & DEX Credentials
            </div>
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#475569]">
              Encrypted with Fernet · Stored in MongoDB
            </div>
          </header>
          <div className="p-4 md:p-6 grid md:grid-cols-2 gap-5">
            <Field label="Binance API Key" hint={current.has_binance_key ? "Currently set" : "Required for live mode"}>
              <SecretInput
                testId={SETTINGS.formApiBinanceKey}
                value={s.binance_api_key}
                onChange={setField("binance_api_key")}
                placeholder="enter binance api key"
                currentMasked={current.binance_api_key_masked}
              />
            </Field>
            <Field label="Binance API Secret" hint="Use spot-trading scope only">
              <SecretInput
                testId={SETTINGS.formApiBinanceSecret}
                value={s.binance_api_secret}
                onChange={setField("binance_api_secret")}
                placeholder="enter binance api secret"
                currentMasked={current.binance_api_secret_masked}
              />
            </Field>
            <Field label="Phantom Private Key (Base58)" hint={current.has_phantom_key ? "Currently set" : "Required for live DEX swaps"}>
              <SecretInput
                testId={SETTINGS.formPhantomKey}
                value={s.phantom_private_key}
                onChange={setField("phantom_private_key")}
                placeholder="enter solana wallet private key"
                currentMasked={current.phantom_private_key_masked}
              />
            </Field>
            <Field label="Telegram Bot Token" hint="From @BotFather">
              <SecretInput
                testId={SETTINGS.formTelegramToken}
                value={s.telegram_bot_token}
                onChange={setField("telegram_bot_token")}
                placeholder="123456:ABC-DEF..."
                currentMasked={current.telegram_bot_token_masked}
              />
            </Field>
            <Field label="Telegram Chat ID" hint="From @userinfobot">
              <input
                data-testid={SETTINGS.formTelegramChatId}
                type="text"
                value={s.telegram_chat_id}
                onChange={setField("telegram_chat_id")}
                placeholder="e.g. 123456789"
                className="w-full px-3 py-2 font-mono text-sm border border-[#1E2229]"
                style={{ borderRadius: 0 }}
              />
            </Field>
            <div className="flex items-end">
              <button
                type="button"
                onClick={test}
                disabled={testing || !current.has_telegram}
                data-testid={SETTINGS.btnTestTelegram}
                className="inline-flex items-center gap-2 px-4 py-2 border border-[#00D1FF] text-[#00D1FF] font-mono text-xs uppercase tracking-[0.15em] hover:bg-[#00D1FF] hover:text-black disabled:opacity-40"
              >
                <PaperPlaneTilt size={13} weight="bold" />
                {testing ? "Sending…" : "Test Telegram"}
              </button>
            </div>
          </div>
        </section>

        {/* Risk Controls */}
        <section className="border border-[#1E2229] bg-[#0C0E12]">
          <header className="px-4 py-3 border-b border-[#1E2229] text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
            Risk & Execution
          </header>
          <div className="p-4 md:p-6 grid md:grid-cols-3 gap-5">
            <Field label="Trade Modal (USD)" hint="Capital per trade">
              <input
                data-testid={SETTINGS.formTradeModal}
                type="number"
                step="0.01"
                value={s.trade_modal_usd}
                onChange={setField("trade_modal_usd")}
                className="w-full px-3 py-2 font-mono text-sm border border-[#1E2229]"
                style={{ borderRadius: 0 }}
              />
            </Field>
            <Field label="Threshold (%)" hint="Min net profit % to trigger">
              <input
                data-testid={SETTINGS.formTradeThreshold}
                type="number"
                step="0.01"
                value={s.threshold_pct}
                onChange={setField("threshold_pct")}
                className="w-full px-3 py-2 font-mono text-sm border border-[#1E2229]"
                style={{ borderRadius: 0 }}
              />
            </Field>
            <Field label="Slippage (%)" hint="DEX swap tolerance">
              <input
                data-testid={SETTINGS.formTradeSlippage}
                type="number"
                step="0.01"
                value={s.slippage_pct}
                onChange={setField("slippage_pct")}
                className="w-full px-3 py-2 font-mono text-sm border border-[#1E2229]"
                style={{ borderRadius: 0 }}
              />
            </Field>

            <label className="flex items-center gap-3 border border-[#1E2229] px-3 py-2 cursor-pointer hover:bg-[#13161C]">
              <input
                type="checkbox"
                checked={!!s.paper_mode}
                onChange={setBool("paper_mode")}
                className="accent-[#00D1FF]"
              />
              <div>
                <div className="text-xs font-mono uppercase tracking-[0.18em]">Paper Mode</div>
                <div className="text-[10px] text-[#475569] font-mono">No real orders sent</div>
              </div>
            </label>

            <label className="flex items-center gap-3 border border-[#1E2229] px-3 py-2 cursor-pointer hover:bg-[#13161C]">
              <input
                type="checkbox"
                checked={!!s.auto_exec}
                onChange={setBool("auto_exec")}
                className="accent-[#00FF66]"
              />
              <div>
                <div className="text-xs font-mono uppercase tracking-[0.18em]">Auto Execute</div>
                <div className="text-[10px] text-[#475569] font-mono">Bot trades on threshold hit</div>
              </div>
            </label>
          </div>
        </section>

        {/* Risk Caps */}
        <section className="border border-[#1E2229] bg-[#0C0E12]">
          <header className="px-4 py-3 border-b border-[#1E2229] text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
            Risk Caps · Safety Switches
          </header>
          <div className="p-4 md:p-6 grid md:grid-cols-2 gap-5">
            <Field label="Daily Loss Limit (USD)" hint="Halt auto-exec when daily PnL ≤ -limit. 0 = no cap.">
              <input
                type="number"
                step="0.01"
                value={s.daily_loss_limit_usd}
                onChange={setField("daily_loss_limit_usd")}
                className="w-full px-3 py-2 font-mono text-sm border border-[#1E2229]"
                style={{ borderRadius: 0 }}
              />
            </Field>
            <Field label="Max Daily Trades" hint="Halt auto-exec after N trades today. 0 = no cap.">
              <input
                type="number"
                step="1"
                value={s.max_daily_trades}
                onChange={setField("max_daily_trades")}
                className="w-full px-3 py-2 font-mono text-sm border border-[#1E2229]"
                style={{ borderRadius: 0 }}
              />
            </Field>
          </div>
        </section>

        {/* Coin Selector */}
        <section className="border border-[#1E2229] bg-[#0C0E12]">
          <header className="px-4 py-3 border-b border-[#1E2229] flex items-center justify-between">
            <div className="text-xs font-mono uppercase tracking-[0.2em] text-[#CBD5E1]">
              Coin Universe · {s.enabled_coins.length}/{allCoins.length} active
            </div>
            <div className="flex gap-1 text-[10px] font-mono uppercase tracking-[0.15em]">
              <button
                type="button"
                onClick={() => setAllCoins(true)}
                className="px-2 py-1 border border-[#1E2229] text-[#94A3B8] hover:bg-[#13161C]"
              >
                Enable all
              </button>
              <button
                type="button"
                onClick={() => setAllCoins(false)}
                className="px-2 py-1 border border-[#1E2229] text-[#94A3B8] hover:bg-[#13161C]"
              >
                Clear
              </button>
            </div>
          </header>
          <div className="p-4 md:p-6 grid grid-cols-3 md:grid-cols-6 gap-2">
            {allCoins.map((coin) => {
              const on = s.enabled_coins.includes(coin);
              return (
                <button
                  key={coin}
                  type="button"
                  data-testid={`coin-toggle-${coin}`}
                  onClick={() => toggleCoin(coin)}
                  className={`px-3 py-2 border font-mono text-xs uppercase tracking-[0.15em] ${
                    on
                      ? "border-[#00FF66] text-[#00FF66] bg-[#0C0E12]"
                      : "border-[#1E2229] text-[#475569] hover:bg-[#13161C]"
                  }`}
                >
                  {coin}
                </button>
              );
            })}
          </div>
        </section>

        <div className="flex items-center justify-end gap-3">
          <button
            type="submit"
            disabled={saving}
            data-testid={SETTINGS.formSettingsSave}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[#00FF66] text-black font-mono text-xs uppercase tracking-[0.2em] hover:opacity-90 disabled:opacity-50"
          >
            <FloppyDisk size={14} weight="bold" />
            {saving ? "Saving…" : "Save Configuration"}
          </button>
        </div>
      </form>
    </div>
  );
}
