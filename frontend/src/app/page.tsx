"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  Bot,
  Brain,
  LineChart as LineChartIcon,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Target,
} from "lucide-react";
import { Card, Stat } from "@/components/card";
import { PnlChart } from "@/components/pnl-chart";
import { ActionBadge } from "@/components/action-badge";
import { ModeSwitcher } from "@/components/mode-switcher";
import { cn, formatBtc, formatPct, formatUsd, timeAgo } from "@/lib/utils";
import {
  api,
  type AutotraderConfigPatch,
  type ClosedTrade,
  type Mode,
  type PaperPosition,
  type PnlDay,
  type Portfolio,
  type ScanRow,
  type SignalRow,
  type Status,
  type Ticker,
} from "@/lib/api";

export default function Page() {
  const [status, setStatus] = useState<Status | null>(null);
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [pnl, setPnl] = useState<PnlDay[]>([]);
  const [marketScan, setMarketScan] = useState<ScanRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [orderBusy, setOrderBusy] = useState(false);
  const [orderAmount, setOrderAmount] = useState("100");

  const refreshAll = useCallback(async () => {
    try {
      const [s, t, sigs, ct, pf, p, ms] = await Promise.all([
        api.status(),
        api.ticker(),
        api.signals(30),
        api.closedTrades(50),
        api.portfolio(),
        api.dailyPnl(14),
        api.marketScan().catch(() => ({ scan: [], symbols: [] })),
      ]);
      setStatus(s);
      setTicker(t);
      setSignals(sigs.signals);
      setClosedTrades(ct.closed);
      setPortfolio(pf);
      setPnl(p.days);
      setMarketScan(ms.scan);
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

      <PositionsCard portfolio={portfolio} />

      <MarketScanCard rows={marketScan} />

      <AutotraderCard
        status={status}
        onUpdate={async (patch) => {
          try {
            await api.updateAutotrader(patch);
            await refreshAll();
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }}
      />

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2" title="Completed trades">
          <ClosedTradeTable rows={closedTrades} />
        </Card>
        <Card title="Daily PnL breakdown">
          <DailyPnlTable days={pnl} />
        </Card>
      </div>

      <Card title="Recent signals">
        <SignalTable signals={signals} />
      </Card>

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

function ClosedTradeTable({ rows }: { rows: ClosedTrade[] }) {
  if (rows.length === 0)
    return (
      <p className="text-xs text-[var(--muted)]">
        No completed trades yet. Trades appear here once the auto-trader exits
        a position (take-profit, stop-loss, or SELL signal).
      </p>
    );
  return (
    <div className="overflow-x-auto -mx-2">
      <table className="w-full text-xs">
        <thead className="text-[var(--muted)]">
          <tr className="[&>th]:text-left [&>th]:font-normal [&>th]:px-2 [&>th]:pb-2">
            <th>Closed</th>
            <th>Pair</th>
            <th>Mode</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>Amount</th>
            <th>Invested</th>
            <th>Duration</th>
            <th>PnL</th>
            <th>PnL %</th>
            <th>Exit reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={`${r.symbol}-${r.entry_ts}-${r.exit_ts}`}
              className="border-t [&>td]:px-2 [&>td]:py-2"
            >
              <td className="text-[var(--muted)] whitespace-nowrap">
                {timeAgo(r.exit_ts)}
              </td>
              <td className="font-medium">{r.symbol}</td>
              <td className="uppercase text-[10px] tracking-wider">
                {r.mode}
              </td>
              <td className="numeric">${formatUsd(r.entry_price)}</td>
              <td className="numeric">${formatUsd(r.exit_price)}</td>
              <td className="numeric">{r.amount.toFixed(4)}</td>
              <td className="numeric">${formatUsd(r.quote_invested)}</td>
              <td className="numeric text-[var(--muted)]">
                {formatDuration(r.duration_seconds)}
              </td>
              <td
                className={cn(
                  "numeric",
                  r.pnl > 0 && "text-[var(--success)]",
                  r.pnl < 0 && "text-[var(--danger)]",
                )}
              >
                ${formatUsd(r.pnl)}
              </td>
              <td
                className={cn(
                  "numeric",
                  r.pnl_pct > 0 && "text-[var(--success)]",
                  r.pnl_pct < 0 && "text-[var(--danger)]",
                )}
              >
                {formatPct(r.pnl_pct)}
              </td>
              <td className="text-[var(--muted)] max-w-[180px] truncate">
                {summarizeExit(r.exit_note)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem === 0 ? `${h}h` : `${h}h${rem}m`;
}

function summarizeExit(note: string): string {
  const n = note.toLowerCase();
  if (n.includes("tp") || n.includes("take profit") || n.includes("take_profit"))
    return "Take profit";
  if (n.includes("sl") || n.includes("stop loss") || n.includes("stop_loss"))
    return "Stop loss";
  if (n.includes("signal") || n.includes("sell")) return "SELL signal";
  return note || "—";
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

function PositionsCard({ portfolio }: { portfolio: Portfolio | null }) {
  if (!portfolio) return null;
  const positions: PaperPosition[] = portfolio.paper.positions ?? [];
  const totalUnrealized = positions.reduce((a, p) => a + p.unrealized_pnl, 0);

  if (positions.length === 0) {
    return (
      <Card
        title={
          <span className="flex items-center gap-2">
            <Target size={14} /> Active positions
          </span>
        }
      >
        <p className="text-sm text-[var(--muted)]">
          No open positions. Auto-trader will enter on the best BUY signal.
        </p>
      </Card>
    );
  }

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Target size={14} /> Active positions ({positions.length})
        </span>
      }
      action={
        <span
          className={cn(
            "text-xs numeric",
            totalUnrealized >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]",
          )}
        >
          Unrealized: ${formatUsd(totalUnrealized)}
        </span>
      }
    >
      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-xs">
          <thead className="text-[var(--muted)]">
            <tr className="[&>th]:text-left [&>th]:font-normal [&>th]:px-2 [&>th]:pb-2">
              <th>Symbol</th>
              <th className="text-right">Qty</th>
              <th className="text-right">Avg cost</th>
              <th className="text-right">Mark</th>
              <th className="text-right">Value</th>
              <th className="text-right">PnL</th>
              <th className="text-right">PnL %</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr key={p.symbol} className="border-t [&>td]:px-2 [&>td]:py-2">
                <td className="font-medium">{p.symbol}</td>
                <td className="numeric text-right">{p.amount.toFixed(6)}</td>
                <td className="numeric text-right">${formatUsd(p.avg_cost)}</td>
                <td className="numeric text-right">${formatUsd(p.mark_price)}</td>
                <td className="numeric text-right">${formatUsd(p.value_usdt)}</td>
                <td
                  className={cn(
                    "numeric text-right",
                    p.unrealized_pnl >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]",
                  )}
                >
                  ${formatUsd(p.unrealized_pnl)}
                </td>
                <td
                  className={cn(
                    "numeric text-right",
                    p.unrealized_pct >= 0 ? "text-[var(--success)]" : "text-[var(--danger)]",
                  )}
                >
                  {formatPct(p.unrealized_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function MarketScanCard({ rows }: { rows: ScanRow[] }) {
  if (!rows || rows.length === 0) {
    return (
      <Card
        title={
          <span className="flex items-center gap-2">
            <LineChartIcon size={14} /> Market scan
          </span>
        }
      >
        <p className="text-sm text-[var(--muted)]">
          Waiting for the first multi-pair scan…
        </p>
      </Card>
    );
  }
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <LineChartIcon size={14} /> Market scan — {rows.length} pairs ranked by conviction
        </span>
      }
      action={
        <span className="text-[10px] uppercase tracking-wider text-[var(--muted)]">
          best signal first
        </span>
      }
    >
      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-xs">
          <thead className="text-[var(--muted)]">
            <tr className="[&>th]:text-left [&>th]:font-normal [&>th]:px-2 [&>th]:pb-2">
              <th>Symbol</th>
              <th className="text-right">Price</th>
              <th className="text-right">Tech score</th>
              <th className="text-right">AI</th>
              <th className="text-right">Conf.</th>
              <th className="text-right">Conviction</th>
              <th>Final</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.symbol} className="border-t [&>td]:px-2 [&>td]:py-2">
                <td className="font-medium">{r.symbol}</td>
                <td className="numeric text-right">${formatUsd(r.price)}</td>
                <td
                  className={cn(
                    "numeric text-right",
                    r.score > 0 && "text-[var(--success)]",
                    r.score < 0 && "text-[var(--danger)]",
                  )}
                >
                  {r.score.toFixed(2)}
                </td>
                <td className="text-right uppercase text-[10px]">
                  {r.ai_action}
                </td>
                <td className="numeric text-right">
                  {(r.ai_confidence * 100).toFixed(0)}%
                </td>
                <td
                  className={cn(
                    "numeric text-right font-medium",
                    r.conviction > 0 && "text-[var(--success)]",
                    r.conviction < 0 && "text-[var(--danger)]",
                  )}
                >
                  {r.conviction.toFixed(2)}
                </td>
                <td>
                  <ActionBadge action={r.action} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function AutotraderCard({
  status,
  onUpdate,
}: {
  status: Status | null;
  onUpdate: (patch: AutotraderConfigPatch) => Promise<void>;
}) {
  const auto = status?.autotrader;
  const [entry, setEntry] = useState("");
  const [tp, setTp] = useState("");
  const [sl, setSl] = useState("");
  const [minConf, setMinConf] = useState("");
  const [maxPos, setMaxPos] = useState("");
  const [symbolsCsv, setSymbolsCsv] = useState("");

  useEffect(() => {
    if (!auto) return;
    queueMicrotask(() => {
      setEntry(String(auto.entry_position_usdt));
      setTp(String(auto.take_profit_pct));
      setSl(String(auto.stop_loss_pct));
      setMinConf(String(auto.min_ai_confidence));
      setMaxPos(String(auto.max_concurrent_positions ?? 1));
      setSymbolsCsv((auto.scan_symbols ?? []).join(","));
    });
  }, [auto]);

  if (!auto) return null;
  const enabled = auto.enabled;
  const lastDecision = auto.recent_decisions[auto.recent_decisions.length - 1];

  const toggle = () =>
    onUpdate({ auto_trade_enabled: !enabled });

  const save = () => {
    const patch: AutotraderConfigPatch = {};
    const e = Number(entry);
    const t = Number(tp);
    const s = Number(sl);
    const m = Number(minConf);
    const mp = Number(maxPos);
    if (Number.isFinite(e) && e > 0) patch.entry_position_usdt = e;
    if (Number.isFinite(t) && t > 0) patch.take_profit_pct = t;
    if (Number.isFinite(s) && s > 0) patch.stop_loss_pct = s;
    if (Number.isFinite(m) && m >= 0 && m <= 1) patch.min_ai_confidence = m;
    if (Number.isFinite(mp) && mp >= 1) patch.max_concurrent_positions = Math.floor(mp);
    const trimmed = symbolsCsv.trim();
    if (trimmed && trimmed !== (auto.scan_symbols ?? []).join(",")) {
      patch.scan_symbols = trimmed;
    }
    if (Object.keys(patch).length > 0) void onUpdate(patch);
  };

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <Bot size={14} /> Auto-trader
          <span
            className={cn(
              "ml-1 text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded",
              enabled
                ? "bg-[var(--success)]/15 text-[var(--success)]"
                : "bg-[var(--muted)]/20 text-[var(--muted)]",
            )}
          >
            {enabled ? "ON" : "OFF"}
          </span>
        </span>
      }
      action={
        <button
          onClick={toggle}
          className={cn(
            "text-xs border rounded-md px-2 py-1",
            enabled
              ? "border-[var(--danger)]/40 text-[var(--danger)] hover:bg-[var(--danger)]/10"
              : "border-[var(--success)]/40 text-[var(--success)] hover:bg-[var(--success)]/10",
          )}
        >
          {enabled ? "Disable" : "Enable"}
        </button>
      }
    >
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <NumField label="Entry (USDT)" value={entry} onChange={setEntry} step="50" />
        <NumField label="Take profit %" value={tp} onChange={setTp} step="0.1" />
        <NumField label="Stop loss %" value={sl} onChange={setSl} step="0.1" />
        <NumField label="Min AI conf." value={minConf} onChange={setMinConf} step="0.05" />
        <NumField label="Max positions" value={maxPos} onChange={setMaxPos} step="1" />
      </div>
      <div className="mt-3">
        <div className="text-[10px] uppercase tracking-wide text-[var(--muted)] mb-1">
          Scan symbols (comma-separated, e.g. BTC/USDT,ETH/USDT,SOL/USDT)
        </div>
        <input
          type="text"
          value={symbolsCsv}
          onChange={(e) => setSymbolsCsv(e.target.value)}
          className="w-full rounded-md border bg-transparent px-2 py-1.5 text-sm numeric outline-none focus:ring-2 focus:ring-[var(--foreground)]/20"
        />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={save}
          className="text-xs rounded-md border px-3 py-1.5 bg-[var(--foreground)] text-[var(--background)] hover:opacity-90"
        >
          Save
        </button>
        <span className="text-[11px] text-[var(--muted)]">
          cooldown {auto.cooldown_seconds}s
          {auto.last_trade_at && ` · last trade ${timeAgo(auto.last_trade_at)}`}
        </span>
      </div>
      {lastDecision && (
        <div className="mt-3 pt-3 border-t text-[11px] text-[var(--muted)]">
          <div className="uppercase tracking-wide mb-1">Recent auto decisions</div>
          <ul className="space-y-0.5 max-h-28 overflow-auto">
            {[...auto.recent_decisions].reverse().map((d, i) => (
              <li key={i} className="numeric">{d}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

function NumField({
  label,
  value,
  onChange,
  step,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)] mb-1">
        {label}
      </div>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="numeric w-full rounded-md border bg-transparent px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-[var(--foreground)]/20"
      />
    </div>
  );
}

function DailyPnlTable({ days }: { days: PnlDay[] }) {
  const rows = [...days].reverse().filter((d) => d.trades > 0 || d.paper !== 0);
  if (rows.length === 0)
    return (
      <p className="text-xs text-[var(--muted)]">
        No realized PnL yet. Sells will populate this.
      </p>
    );
  return (
    <div className="overflow-x-auto -mx-2">
      <table className="w-full text-xs">
        <thead className="text-[var(--muted)]">
          <tr className="[&>th]:text-left [&>th]:font-normal [&>th]:px-2 [&>th]:pb-2">
            <th>Date</th>
            <th className="text-right">Trades</th>
            <th className="text-right">Paper PnL</th>
            <th className="text-right">Live PnL</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.date} className="border-t [&>td]:px-2 [&>td]:py-2">
              <td className="text-[var(--muted)] numeric whitespace-nowrap">
                {d.date}
              </td>
              <td className="numeric text-right">{d.trades}</td>
              <td
                className={cn(
                  "numeric text-right",
                  d.paper > 0 && "text-[var(--success)]",
                  d.paper < 0 && "text-[var(--danger)]",
                )}
              >
                {d.paper ? `$${formatUsd(d.paper)}` : "—"}
              </td>
              <td
                className={cn(
                  "numeric text-right",
                  d.live > 0 && "text-[var(--success)]",
                  d.live < 0 && "text-[var(--danger)]",
                )}
              >
                {d.live ? `$${formatUsd(d.live)}` : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
