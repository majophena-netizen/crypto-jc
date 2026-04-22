"""Technical indicator computations using pandas / pandas-ta-classic."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.config import settings
from app.exchange import Candle


@dataclass
class IndicatorSnapshot:
    price: float
    rsi: float
    macd: float
    macd_signal: float
    macd_hist: float
    ma_fast: float
    ma_slow: float
    ema_fast: float
    ema_slow: float
    bb_upper: float
    bb_lower: float
    bb_mid: float
    # Discrete directional votes: +1 bullish, -1 bearish, 0 neutral
    rsi_vote: int
    macd_vote: int
    ma_vote: int
    bb_vote: int
    # Aggregate score in [-1, 1]
    score: float
    action: str  # buy | sell | hold


def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": [c.ts for c in candles],
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _macd(close: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    signal_line = _ema(macd, signal)
    hist = macd - signal_line
    return macd, signal_line, hist


def _bollinger(close: pd.Series, length: int = 20, std: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std()
    upper = mid + std * sd
    lower = mid - std * sd
    return upper.fillna(close), mid.fillna(close), lower.fillna(close)


def compute(candles: list[Candle]) -> IndicatorSnapshot:
    if not candles:
        raise ValueError("no candles provided")
    df = _candles_to_df(candles)
    close = df["close"].astype(float)

    rsi_series = _rsi(close, settings.rsi_period)
    macd_line, macd_sig, macd_hist = _macd(
        close, settings.macd_fast, settings.macd_slow, settings.macd_signal
    )
    ma_fast = close.rolling(settings.ma_fast).mean().bfill()
    ma_slow = close.rolling(settings.ma_slow).mean().bfill()
    ema_fast = _ema(close, settings.ma_fast)
    ema_slow = _ema(close, settings.ma_slow)
    bb_upper, bb_mid, bb_lower = _bollinger(close)

    price = float(close.iloc[-1])
    rsi_val = float(rsi_series.iloc[-1])
    macd_val = float(macd_line.iloc[-1])
    macd_sig_val = float(macd_sig.iloc[-1])
    macd_hist_val = float(macd_hist.iloc[-1])
    ma_fast_val = float(ma_fast.iloc[-1])
    ma_slow_val = float(ma_slow.iloc[-1])
    ema_fast_val = float(ema_fast.iloc[-1])
    ema_slow_val = float(ema_slow.iloc[-1])
    bb_upper_val = float(bb_upper.iloc[-1])
    bb_mid_val = float(bb_mid.iloc[-1])
    bb_lower_val = float(bb_lower.iloc[-1])

    # Votes
    if rsi_val <= settings.rsi_oversold:
        rsi_vote = 1
    elif rsi_val >= settings.rsi_overbought:
        rsi_vote = -1
    else:
        rsi_vote = 0

    if macd_val > macd_sig_val and macd_hist_val > 0:
        macd_vote = 1
    elif macd_val < macd_sig_val and macd_hist_val < 0:
        macd_vote = -1
    else:
        macd_vote = 0

    if ma_fast_val > ma_slow_val and price > ma_fast_val:
        ma_vote = 1
    elif ma_fast_val < ma_slow_val and price < ma_fast_val:
        ma_vote = -1
    else:
        ma_vote = 0

    if price <= bb_lower_val:
        bb_vote = 1
    elif price >= bb_upper_val:
        bb_vote = -1
    else:
        bb_vote = 0

    votes = [rsi_vote, macd_vote, ma_vote, bb_vote]
    score = sum(votes) / len(votes)
    if score >= 0.5:
        action = "buy"
    elif score <= -0.5:
        action = "sell"
    else:
        action = "hold"

    return IndicatorSnapshot(
        price=price,
        rsi=rsi_val,
        macd=macd_val,
        macd_signal=macd_sig_val,
        macd_hist=macd_hist_val,
        ma_fast=ma_fast_val,
        ma_slow=ma_slow_val,
        ema_fast=ema_fast_val,
        ema_slow=ema_slow_val,
        bb_upper=bb_upper_val,
        bb_lower=bb_lower_val,
        bb_mid=bb_mid_val,
        rsi_vote=rsi_vote,
        macd_vote=macd_vote,
        ma_vote=ma_vote,
        bb_vote=bb_vote,
        score=score,
        action=action,
    )
