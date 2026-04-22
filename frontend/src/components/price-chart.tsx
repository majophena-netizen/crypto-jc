"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Candle } from "@/lib/api";
import { formatUsd } from "@/lib/utils";

export function PriceChart({ candles }: { candles: Candle[] }) {
  const data = candles.map((c) => ({
    t: new Date(c.ts).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    close: c.close,
  }));
  const last = candles[candles.length - 1]?.close ?? 0;
  const first = candles[0]?.close ?? 0;
  const up = last >= first;
  const stroke = up ? "var(--success)" : "var(--danger)";

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="t"
            tick={{ fontSize: 11, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={false}
            minTickGap={32}
          />
          <YAxis
            domain={["dataMin", "dataMax"]}
            tick={{ fontSize: 11, fill: "var(--muted)" }}
            tickLine={false}
            axisLine={false}
            width={64}
            tickFormatter={(v: number) => formatUsd(v, 0)}
          />
          <Tooltip
            contentStyle={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--muted)" }}
            formatter={(v) => [`$${formatUsd(Number(v))}`, "Close"]}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke={stroke}
            strokeWidth={2}
            fill="url(#priceGrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
