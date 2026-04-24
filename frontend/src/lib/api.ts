export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return (await res.json()) as T;
}

export type Mode = "signals" | "paper" | "live";

export type AutotraderStatus = {
  enabled: boolean;
  entry_position_usdt: number;
  take_profit_pct: number;
  stop_loss_pct: number;
  min_ai_confidence: number;
  cooldown_seconds: number;
  max_concurrent_positions: number;
  trailing_stop_pct?: number;
  trailing_arm_pct?: number;
  max_hold_hours?: number;
  scan_symbols: string[];
  last_trade_at: string | null;
  recent_decisions: string[];
};

export type Status = {
  mode: Mode;
  symbol: string;
  timeframe: string;
  last_scan_at: string | null;
  last_action: string;
  last_price: number;
  scan_interval_seconds: number;
  ai_enabled: boolean;
  ai_provider?: string | null;
  scan_symbols?: string[];
  binance: { has_credentials: boolean; testnet: boolean };
  autotrader?: AutotraderStatus;
  errors: string[];
};

export type AutotraderConfigPatch = Partial<{
  auto_trade_enabled: boolean;
  entry_position_usdt: number;
  take_profit_pct: number;
  stop_loss_pct: number;
  min_ai_confidence: number;
  auto_trade_cooldown_seconds: number;
  max_concurrent_positions: number;
  trailing_stop_pct: number;
  trailing_arm_pct: number;
  max_hold_hours: number;
  scan_symbols: string;
}>;

export type ScanRow = {
  symbol: string;
  price: number;
  action: "buy" | "sell" | "hold";
  score: number;
  conviction: number;
  rsi: number;
  macd: number;
  macd_signal: number;
  ma_fast: number;
  ma_slow: number;
  bb_upper: number;
  bb_lower: number;
  ai_action: string;
  ai_confidence: number;
  ai_rationale: string;
  explanation: string;
};

export type PaperPosition = {
  symbol: string;
  amount: number;
  avg_cost: number;
  mark_price: number;
  value_usdt: number;
  unrealized_pnl: number;
  unrealized_pct: number;
};

export type LiveBalance = {
  symbol: string;
  asset: string;
  amount: number;
  mark_price: number;
  value_usdt: number;
};

export type Ticker = {
  symbol: string;
  last: number;
  bid: number | null;
  ask: number | null;
  high: number | null;
  low: number | null;
  change_pct: number | null;
  quote_volume: number | null;
  timestamp: number | null;
  source?: string;
};

export type Candle = {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type Indicators = {
  price: number;
  rsi: number;
  macd: number;
  macd_signal: number;
  macd_hist: number;
  ma_fast: number;
  ma_slow: number;
  ema_fast: number;
  ema_slow: number;
  bb_upper: number;
  bb_lower: number;
  bb_mid: number;
  rsi_vote: number;
  macd_vote: number;
  ma_vote: number;
  bb_vote: number;
  score: number;
  action: "buy" | "sell" | "hold";
};

export type SignalRow = {
  id: number;
  ts: string;
  symbol: string;
  timeframe: string;
  price: number;
  action: "buy" | "sell" | "hold";
  score: number;
  rsi: number;
  macd: number;
  macd_signal: number;
  ma_fast: number;
  ma_slow: number;
  ai_action: string;
  ai_confidence: number;
  ai_rationale: string;
  explanation: string;
};

export type TradeRow = {
  id: number;
  ts: string;
  mode: "paper" | "live";
  symbol: string;
  side: "buy" | "sell";
  price: number;
  amount: number;
  quote_amount: number;
  fee: number;
  pnl: number;
  note: string;
};

export type Portfolio = {
  paper: {
    usdt: number;
    btc: number;
    avg_cost: number;
    realized_pnl: number;
    mark_price: number;
    equity: number;
    unrealized_pnl: number;
    starting_usdt: number;
    positions: PaperPosition[];
  };
  live: null | {
    usdt?: number;
    btc?: number;
    mark_price?: number;
    equity?: number;
    testnet: boolean;
    error?: string;
    balances?: LiveBalance[];
  };
};

export type PnlDay = { date: string; paper: number; live: number; trades: number };

export type ClosedTrade = {
  mode: "paper" | "live";
  symbol: string;
  amount: number;
  entry_ts: string;
  entry_price: number;
  exit_ts: string;
  exit_price: number;
  quote_invested: number;
  quote_returned: number;
  fees: number;
  pnl: number;
  pnl_pct: number;
  duration_seconds: number;
  entry_note: string;
  exit_note: string;
};

export const api = {
  status: () => request<Status>("/api/control/status"),
  setMode: (mode: Mode) =>
    request<{ mode: Mode }>("/api/control/mode", {
      method: "POST",
      body: JSON.stringify({ mode }),
    }),
  ticker: () => request<Ticker>("/api/market/ticker"),
  candles: (limit = 200) =>
    request<{ candles: Candle[] }>(`/api/market/candles?limit=${limit}`),
  indicators: () => request<Indicators>("/api/market/indicators"),
  scan: () =>
    request<{
      primary: null | {
        symbol: string;
        action: "buy" | "sell" | "hold";
        explanation: string;
        snapshot: Record<string, number | string>;
        ai: { action: string; confidence: number; rationale: string };
      };
      scan: ScanRow[];
    }>("/api/signals/scan", { method: "POST" }),
  signals: (limit = 50, symbol?: string) =>
    request<{ signals: SignalRow[] }>(
      `/api/signals?limit=${limit}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`,
    ),
  marketScan: () =>
    request<{ scan: ScanRow[]; symbols: string[] }>("/api/market/scan"),
  trades: (limit = 100, mode?: string) =>
    request<{ trades: TradeRow[] }>(
      `/api/trades?limit=${limit}${mode ? `&mode=${mode}` : ""}`,
    ),
  closedTrades: (limit = 50, mode?: string) =>
    request<{ closed: ClosedTrade[] }>(
      `/api/trades/closed?limit=${limit}${mode ? `&mode=${mode}` : ""}`,
    ),
  portfolio: () => request<Portfolio>("/api/trades/portfolio"),
  dailyPnl: (days = 14) =>
    request<{ days: PnlDay[] }>(`/api/trades/pnl/daily?days=${days}`),
  executeTrade: (body: {
    side: "buy" | "sell";
    quote_amount: number;
    mode: "paper" | "live";
    note?: string;
  }) =>
    request<TradeRow>("/api/trades/execute", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resetPaper: () =>
    request<{ ok: boolean }>("/api/trades/paper/reset", { method: "POST" }),
  updateAutotrader: (patch: AutotraderConfigPatch) =>
    request<AutotraderStatus>("/api/control/autotrader", {
      method: "POST",
      body: JSON.stringify(patch),
    }),
};
