"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  Brain,
  LineChart as LineChartIcon,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Card, Stat } from "@/components/card";
import { PriceChart } from "@/components/price-chart";
import { PnlChart } from "@/components/pnl-chart";
import { ActionBadge } from "@/components/action-badge";
import { ModeSwitcher } from "@/components/mode-switcher";
import { cn, formatBtc, formatPct, formatUsd, timeAgo } from "@/lib/utils";
import {
  api,
  type Candle,
  type Indicators,
  type Mode,
  type PnlDay,
  type Portfolio,
  type SignalRow,
  type Status,
  type Ticker,
  type TradeRow,
} from "@/lib/api";

export default function Page() {
  const [status, setStatus] = useState<Status | null>(null);
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [indicators, setIndicators] = useState<Indicators | null>(null);
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [pnl, setPnl] = useState<PnlDay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [orderBusy, setOrderBusy] = useState(false);
  const [orderAmount, setOrderAmount] = useState("100");

  const refreshAll = useCallback(async () => {
    try {
      const [s, t, c, ind, sigs, tr, pf, p] = await Promise.all([
        api.status(),
        api.ticker(),
        api.candles(150),
        api.indicators(),
        api.signals(30),
        api.trades(40),
        api.portfolio(),
        api.dailyPnl(14),
      ]);
      setStatus(s);
      setTicker(t);
      setCandles(c.candles);
      setIndicators(ind);
      setSignals(sigs.signals);
      setTrades(tr.trades);
      setPortfolio(pf);
      setPnl(p.days);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    // Initial fetch is deferred to a microtask so we don't call setState
    // synchronously inside the effect body (react-hooks/set-state-in-effect).
    const initial = queueMicrotask(() => void refreshAll()) as unknown as number;
    const id = setInterval(() => void refreshAll(), 15_000);
    return () => {
      clearInterval(id);
      void initial;
    };
  }, [refreshAll]);

  const doScan = useCallback(async () => {
    setScanning(true);
    try {
      await api.scan();
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setScanning(false);
    }
  }, [refreshAll]);

  const doSetMode = useCallback(
    async (m: Mode) => {
      try {
        await api.setMode(m);
        await refreshAll();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [refreshAll],
  );

  const doOrder = useCallback(
    async (side: "buy" | "sell") => {
      if (!status) return;
      const mode = status.mode === "live" ? "live" : "paper";
      const amount = Number(orderAmount);
      if (!Number.isFinite(amount) || amount <= 0) {
        setError("Enter a positive USDT amount");
        return;
      }
      setOrderBusy(true);
      try {
        await api.executeTrade({
          side,
          quote_amount: amount,
          mode,
          note: "manual order",
        });
        await refreshAll();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setOrderBusy(false);
      }
    },
    [orderAmount, refreshAll, status],
  );

  const doReset = useCallback(async () => {
    if (!confirm("Reset paper wallet? This deletes all paper trades."))
      return;
    try {
      await api.resetPaper();
      await refreshAll();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [refreshAll]);

  const totalDailyPnl = useMemo(
    () =>
      pnl.reduce(
        (acc, d) => {
          acc.paper += d.paper;
          acc.live += d.live;
          return acc;
        },
        { paper: 0, live: 0 },
      ),
    [pnl],
  );

  const last24h = pnl[pnl.length - 1];

  return (
    <main className="mx-auto w-full max-w-7xl p-4 sm:p-6 lg:p-8 space-y-6">
      <Header
        ticker={ticker}
        status={status}
        onScan={doScan}
        scanning={scanning}
        onSetMode={doSetMode}
      />

      {error && (
        <div className="rounded-lg border border-[var(--danger)]/40 bg-[var(--danger)]/10 px-4 py-2 text-sm text-[var(--danger)] flex items-center gap-2">
          <ShieldAlert size={14} /> {error}
          <button
            onClick={() => setError(null)}
            className="ml-auto text-[var(--muted)] hover:text-[var(--foreground)] text-xs"
          >
            dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          className="lg:col-span-2"
          title={
            <span className="flex items-center gap-2">
              <LineChartIcon size={14} /> Price — {status?.symbol ?? "BTC/USDT"} ({status?.timeframe ?? "15m"})
            </span>
          }
          action={
            ticker?.source && (
              <span className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
                source: {ticker.source}
              </span>
            )
          }
        >
          <PriceChart candles={candles} />
        </Card>
        <Card title="Indicators">
          {indicators ? <IndicatorsPanel indicators={indicators} /> : <Skeleton />}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          title={
            <span className="flex items-center gap-2">
              <Brain size={14} /> Portfolio
            </span>
          }
          action={
            status?.mode === "paper" && (
              <button
                onClick={doReset}
                className="text-xs text-[var(--muted)] hover:text-[var(--foreground)] inline-flex items-center gap-1"
              >
                <RotateCcw size={12} /> Reset paper
              </button>
            )
          }
        >
          <PortfolioPanel portfolio={portfolio} />
          <OrderPanel
            mode={status?.mode ?? "paper"}
            hasLiveCreds={status?.binance.has_credentials ?? false}
            orderAmount={orderAmount}
            setOrderAmount={setOrderAmount}
            onOrder={doOrder}
            busy={orderBusy}
          />
        </Card>

        <Card
          className="lg:col-span-2"
          title="Daily P&L (14 days)"
          action={
            <div className="flex items-center gap-3 text-xs">
              <span>
                Paper:{" "}
                <span
                  className={cn(
                    "numeric",
                    totalDailyPnl.paper >= 0
                      ? "text-[var(--success)]"
                      : "text-[var(--danger)]",
                  )}
                >
                  ${formatUsd(totalDailyPnl.paper)}
                </span>
              </span>
              <span>
                Today:{" "}
                <span
                  className={cn(
                    "numeric",
                    (last24h?.paper ?? 0) >= 0
                      ? "text-[var(--success)]"
                      : "text-[var(--danger)]",
                  )}
                >
                  ${formatUsd(last24h?.paper ?? 0)}
                </span>
              </span>
            </div>
          }
        >
          <PnlChart days={pnl} field="paper" />
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Recent signals">
          <SignalTable signals={signals} />
        </Card>
        <Card title="Recent trades">
          <TradeTable trades={trades} />
        </Card>
      </div>

      <footer className="text-[11px] text-[var(--muted)] pt-4 border-t flex flex-wrap items-center gap-3">
        <span>Built with FastAPI + Next.js. Indicators: RSI, MACD, MA, Bollinger. AI: Claude.</span>
        {status?.binance.testnet ? (
          <span className="inline-flex items-center gap-1 text-[var(--warn)]">
            <ShieldCheck size={12} /> Binance TESTNET
          </span>
        ) : (
          status?.binance.has_credentials && (
            <span className="inline-flex items-center gap-1 text-[var(--danger)]">
              <ShieldAlert size={12} /> Binance MAINNET
            </span>
          )
        )}
        <span className="ml-auto">
          Last scan: {timeAgo(status?.last_scan_at)}
        </span>
      </footer>
    </main>
  );
}

function Header({
  ticker,
  status,
  onScan,
  scanning,
  onSetMode,
}: {
  ticker: Ticker | null;
  status: Status | null;
  onScan: () => void;
  scanning: boolean;
  onSetMode: (m: Mode) => void;
}) {
  const price = ticker?.last ?? 0;
  const change = ticker?.change_pct ?? 0;
  const up = change >= 0;
  return (
    <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div>
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--muted)]">
          {status?.symbol ?? "BTC/USDT"}
        </div>
        <div className="flex items-baseline gap-3 mt-1">
          <div className="numeric text-4xl font-semibold tracking-tight">
            ${formatUsd(price)}
          </div>
          <div
            className={cn(
              "numeric text-sm font-medium inline-flex items-center gap-1",
              up ? "text-[var(--success)]" : "text-[var(--danger)]",
            )}
          >
            <ArrowUpRight
              size={14}
              className={cn("transition-transform", !up && "rotate-90")}
            />
            {formatPct(change)}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {status && (
          <ModeSwitcher current={status.mode} onChange={onSetMode} />
        )}
        <button
          type="button"
          onClick={onScan}
          disabled={scanning}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium bg-[var(--foreground)] text-[var(--background)] hover:opacity-90",
            scanning && "opacity-60 cursor-wait",
          )}
        >
          {scanning ? <RefreshCw size={14} className="animate-spin" /> : <PlayCircle size={14} />}
          Scan now
        </button>
      </div>
    </div>
  );
}

function IndicatorsPanel({ indicators }: { indicators: Indicators }) {
  const voteColor = (v: number) =>
    v > 0
      ? "text-[var(--success)]"
      : v < 0
        ? "text-[var(--danger)]"
        : "text-[var(--muted)]";
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--muted)]">Aggregate</span>
        <div className="flex items-center gap-2">
          <span className="numeric text-sm">{indicators.score.toFixed(2)}</span>
          <ActionBadge action={indicators.action} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <Row
          label="RSI(14)"
          value={indicators.rsi.toFixed(1)}
          extra={voteLabel(indicators.rsi_vote)}
          extraCls={voteColor(indicators.rsi_vote)}
        />
        <Row
          label="MACD"
          value={indicators.macd.toFixed(1)}
          extra={`sig ${indicators.macd_signal.toFixed(1)}`}
          extraCls={voteColor(indicators.macd_vote)}
        />
        <Row
          label="MA fast/slow"
          value={`${indicators.ma_fast.toFixed(0)} / ${indicators.ma_slow.toFixed(0)}`}
          extra={voteLabel(indicators.ma_vote)}
          extraCls={voteColor(indicators.ma_vote)}
        />
        <Row
          label="Bollinger"
          value={`${indicators.bb_lower.toFixed(0)}–${indicators.bb_upper.toFixed(0)}`}
          extra={voteLabel(indicators.bb_vote)}
          extraCls={voteColor(indicators.bb_vote)}
        />
      </div>
    </div>
  );
}

function voteLabel(v: number) {
  return v > 0 ? "bullish" : v < 0 ? "bearish" : "neutral";
}

function Row({
  label,
  value,
  extra,
  extraCls,
}: {
  label: string;
  value: string;
  extra?: string;
  extraCls?: string;
}) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">
        {label}
      </div>
      <div className="numeric font-medium">{value}</div>
      {extra && (
        <div className={cn("text-[11px] mt-0.5", extraCls)}>{extra}</div>
      )}
    </div>
  );
}

function PortfolioPanel({ portfolio }: { portfolio: Portfolio | null }) {
  if (!portfolio) return <Skeleton />;
  const p = portfolio.paper;
  const totalPnl = p.realized_pnl + p.unrealized_pnl;
  const pctVsStart = p.starting_usdt > 0 ? ((p.equity - p.starting_usdt) / p.starting_usdt) * 100 : 0;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Stat
          label="Paper equity"
          value={`$${formatUsd(p.equity)}`}
          sub={`start $${formatUsd(p.starting_usdt, 0)} (${formatPct(pctVsStart)})`}
          tone={p.equity >= p.starting_usdt ? "success" : "danger"}
        />
        <Stat
          label="Total PnL"
          value={`$${formatUsd(totalPnl)}`}
          sub={`realized $${formatUsd(p.realized_pnl)} / unreal $${formatUsd(p.unrealized_pnl)}`}
          tone={totalPnl >= 0 ? "success" : "danger"}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Stat label="USDT" value={formatUsd(p.usdt)} />
        <Stat
          label="BTC"
          value={formatBtc(p.btc)}
          sub={p.avg_cost ? `avg $${formatUsd(p.avg_cost)}` : "no position"}
        />
      </div>
      {portfolio.live && (
        <div className="mt-2 rounded-lg border p-3 bg-[var(--background)]/40">
          <div className="flex items-center justify-between mb-2">
            <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">
              Live Binance {portfolio.live.testnet ? "(testnet)" : "(mainnet)"}
            </div>
          </div>
          {portfolio.live.error ? (
            <div className="text-xs text-[var(--danger)]">{portfolio.live.error}</div>
          ) : (
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <div className="text-[11px] text-[var(--muted)]">USDT</div>
                <div className="numeric">{formatUsd(portfolio.live.usdt ?? 0)}</div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--muted)]">BTC</div>
                <div className="numeric">{formatBtc(portfolio.live.btc ?? 0)}</div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--muted)]">Equity</div>
                <div className="numeric">${formatUsd(portfolio.live.equity ?? 0)}</div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function OrderPanel({
  mode,
  hasLiveCreds,
  orderAmount,
  setOrderAmount,
  onOrder,
  busy,
}: {
  mode: Mode;
  hasLiveCreds: boolean;
  orderAmount: string;
  setOrderAmount: (v: string) => void;
  onOrder: (side: "buy" | "sell") => void;
  busy: boolean;
}) {
  const isLive = mode === "live";
  const disabled = mode === "signals" || (isLive && !hasLiveCreds) || busy;
  return (
    <div className="mt-4 pt-4 border-t space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">
          Manual order ({mode === "signals" ? "disabled in signals mode" : mode})
        </div>
      </div>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-xs text-[var(--muted)]">
            USDT
          </span>
          <input
            type="number"
            min={1}
            value={orderAmount}
            onChange={(e) => setOrderAmount(e.target.value)}
            className="numeric w-full rounded-md border bg-transparent pl-12 pr-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-[var(--foreground)]/20"
          />
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onOrder("buy")}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium border",
            "border-[var(--success)]/40 text-[var(--success)] hover:bg-[var(--success)]/10",
            disabled && "opacity-40 cursor-not-allowed",
          )}
        >
          Buy
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onOrder("sell")}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium border",
            "border-[var(--danger)]/40 text-[var(--danger)] hover:bg-[var(--danger)]/10",
            disabled && "opacity-40 cursor-not-allowed",
          )}
        >
          Sell
        </button>
      </div>
      {isLive && !hasLiveCreds && (
        <p className="text-[11px] text-[var(--warn)]">
          Live trading requires BINANCE_API_KEY / BINANCE_API_SECRET in backend .env.
        </p>
      )}
    </div>
  );
}

function SignalTable({ signals }: { signals: SignalRow[] }) {
  if (signals.length === 0)
    return (
      <p className="text-xs text-[var(--muted)]">
        No signals yet. Press <em>Scan now</em> to generate one.
      </p>
    );
  return (
    <div className="overflow-x-auto -mx-2">
      <table className="w-full text-xs">
        <thead className="text-[var(--muted)]">
          <tr className="[&>th]:text-left [&>th]:font-normal [&>th]:px-2 [&>th]:pb-2">
            <th>Time</th>
            <th>Action</th>
            <th>Price</th>
            <th>RSI</th>
            <th>AI</th>
            <th>Rationale</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr
              key={s.id}
              className="border-t [&>td]:px-2 [&>td]:py-2 align-top"
            >
              <td className="text-[var(--muted)] whitespace-nowrap">
                {timeAgo(s.ts)}
              </td>
              <td>
                <ActionBadge action={s.action} />
              </td>
              <td className="numeric">${formatUsd(s.price)}</td>
              <td className="numeric">{s.rsi.toFixed(0)}</td>
              <td>
                <ActionBadge action={s.ai_action} />
                <div className="text-[10px] text-[var(--muted)] numeric">
                  {(s.ai_confidence * 100).toFixed(0)}%
                </div>
              </td>
              <td className="text-[var(--muted)] max-w-[22rem]">
                <div className="line-clamp-2">{s.explanation}</div>
                {s.ai_rationale && (
                  <div className="italic line-clamp-2 mt-0.5">
                    “{s.ai_rationale}”
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeTable({ trades }: { trades: TradeRow[] }) {
  if (trades.length === 0)
    return <p className="text-xs text-[var(--muted)]">No trades yet.</p>;
  return (
    <div className="overflow-x-auto -mx-2">
      <table className="w-full text-xs">
        <thead className="text-[var(--muted)]">
          <tr className="[&>th]:text-left [&>th]:font-normal [&>th]:px-2 [&>th]:pb-2">
            <th>Time</th>
            <th>Mode</th>
            <th>Side</th>
            <th>Price</th>
            <th>Amount</th>
            <th>USDT</th>
            <th>PnL</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} className="border-t [&>td]:px-2 [&>td]:py-2">
              <td className="text-[var(--muted)] whitespace-nowrap">
                {timeAgo(t.ts)}
              </td>
              <td className="uppercase text-[10px] tracking-wider">
                {t.mode}
              </td>
              <td>
                <ActionBadge action={t.side} />
              </td>
              <td className="numeric">${formatUsd(t.price)}</td>
              <td className="numeric">{formatBtc(t.amount)}</td>
              <td className="numeric">${formatUsd(t.quote_amount)}</td>
              <td
                className={cn(
                  "numeric",
                  t.pnl > 0 && "text-[var(--success)]",
                  t.pnl < 0 && "text-[var(--danger)]",
                )}
              >
                {t.pnl ? `$${formatUsd(t.pnl)}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2 animate-pulse">
      <div className="h-4 rounded bg-[var(--border)] w-1/2" />
      <div className="h-4 rounded bg-[var(--border)] w-1/3" />
      <div className="h-4 rounded bg-[var(--border)] w-2/3" />
    </div>
  );
}
