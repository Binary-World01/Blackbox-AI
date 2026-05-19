from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    short_window: int
    long_window: int
    risk_multiplier: float
    stop_loss: float
    take_profit: float
    conservative_filter: bool = False
    family: str = "sma_cross"
    rsi_buy: float = 35.0
    rsi_sell: float = 62.0
    band_window: int = 20
    band_std: float = 2.0
    breakout_window: int = 24
    volume_window: int = 20


def generate_market_series(asset: str = "mTSLA", days: int = 180) -> list[dict[str, float]]:
    """Create a deterministic synthetic market with enough movement for demo backtests."""
    seed = sum(ord(c) for c in asset)
    price = 104.0 + (seed % 17)
    rows: list[dict[str, float]] = []

    for day in range(days):
        trend = 0.045 * day
        seasonal = math.sin((day + seed) / 7.0) * 2.8
        shock = math.sin((day + seed) / 2.9) * 1.35
        late_momentum = max(0, day - 92) * 0.075
        price = max(18.0, price + 0.18 + seasonal * 0.05 + shock * 0.08 + late_momentum * 0.01)
        rows.append(
            {
                "day": float(day + 1),
                "close": round(price + trend + seasonal + shock, 4),
            }
        )

    return rows


def moving_average(values: list[float], end: int, window: int) -> float:
    start = max(0, end - window + 1)
    sample = values[start : end + 1]
    return sum(sample) / len(sample)


def rolling_std(values: list[float], end: int, window: int) -> float:
    avg = moving_average(values, end, window)
    start = max(0, end - window + 1)
    sample = values[start : end + 1]
    if len(sample) < 2:
        return 0.0
    variance = sum((item - avg) ** 2 for item in sample) / (len(sample) - 1)
    return math.sqrt(variance)


def rsi(values: list[float], end: int, window: int = 14) -> float:
    if end < 1:
        return 50.0
    start = max(1, end - window + 1)
    gains = 0.0
    losses = 0.0
    periods = 0
    for idx in range(start, end + 1):
        change = values[idx] - values[idx - 1]
        gains += max(0.0, change)
        losses += max(0.0, -change)
        periods += 1
    if periods == 0:
        return 50.0
    avg_gain = gains / periods
    avg_loss = losses / periods
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def rolling_high(values: list[float], end: int, window: int) -> float:
    start = max(0, end - window)
    sample = values[start:end] or [values[end]]
    return max(sample)


def rolling_low(values: list[float], end: int, window: int) -> float:
    start = max(0, end - window)
    sample = values[start:end] or [values[end]]
    return min(sample)


def max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak:
            worst = min(worst, (value - peak) / peak)
    return abs(worst) * 100


def sharpe_ratio(equity: list[float]) -> float:
    returns = []
    for idx in range(1, len(equity)):
        previous = equity[idx - 1]
        if previous:
            returns.append((equity[idx] - previous) / previous)
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    variance = sum((item - avg) ** 2 for item in returns) / (len(returns) - 1)
    stdev = math.sqrt(variance)
    if stdev == 0:
        return 0.0
    return (avg / stdev) * math.sqrt(252)


def run_backtest(config: StrategyConfig, asset: str = "mTSLA", market_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = market_rows if market_rows else generate_market_series(asset)
    closes = [row["close"] for row in rows]
    volumes = [float(row.get("volume", 0) or 0) for row in rows]
    cash = 10_000.0
    position = 0.0
    entry_price = 0.0
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, float]] = []

    for idx, close in enumerate(closes):
        short_ma = moving_average(closes, idx, config.short_window)
        long_ma = moving_average(closes, idx, config.long_window)
        macro_filter = close > moving_average(closes, idx, 80) if config.conservative_filter else True
        buy_signal = False
        sell_signal = False

        if config.family == "sma_cross":
            buy_signal = short_ma > long_ma and macro_filter and position == 0
            sell_signal = position > 0 and short_ma < long_ma
        elif config.family == "rsi_mean_reversion":
            current_rsi = rsi(closes, idx)
            buy_signal = current_rsi <= config.rsi_buy and close >= rolling_low(closes, idx, config.short_window) and position == 0
            sell_signal = position > 0 and (current_rsi >= config.rsi_sell or close >= moving_average(closes, idx, config.long_window))
        elif config.family == "bollinger_bounce":
            basis = moving_average(closes, idx, config.band_window)
            deviation = rolling_std(closes, idx, config.band_window)
            lower = basis - config.band_std * deviation
            upper = basis + config.band_std * deviation
            buy_signal = close <= lower and macro_filter and position == 0
            sell_signal = position > 0 and (close >= basis or close >= upper)
        elif config.family == "breakout_retest":
            prior_high = rolling_high(closes, idx, config.breakout_window)
            prior_low = rolling_low(closes, idx, config.breakout_window)
            buy_signal = close > prior_high and short_ma > long_ma and position == 0
            sell_signal = position > 0 and (close < short_ma or close < prior_low)
        elif config.family == "volume_trend":
            avg_volume = moving_average(volumes, idx, config.volume_window) if any(volumes) else 0
            volume_ok = volumes[idx] >= avg_volume * 1.05 if avg_volume else True
            buy_signal = short_ma > long_ma and volume_ok and macro_filter and position == 0
            sell_signal = position > 0 and (short_ma < long_ma or not macro_filter)

        if position > 0:
            change = (close - entry_price) / entry_price
            sell_signal = sell_signal or change <= -config.stop_loss or change >= config.take_profit

        if buy_signal:
            allocation = cash * min(0.92, max(0.25, config.risk_multiplier))
            position = allocation / close
            cash -= allocation
            entry_price = close
            trades.append({"day": idx + 1, "side": "BUY", "price": round(close, 2)})
        elif sell_signal:
            cash += position * close
            pnl = ((close - entry_price) / entry_price) * 100 if entry_price else 0
            trades.append({"day": idx + 1, "side": "SELL", "price": round(close, 2), "pnl": round(pnl, 2)})
            position = 0.0
            entry_price = 0.0

        equity = cash + position * close
        equity_curve.append({"day": float(idx + 1), "time": rows[idx].get("time", idx + 1), "equity": round(equity, 2)})

    if position:
        close = closes[-1]
        cash += position * close
        pnl = ((close - entry_price) / entry_price) * 100 if entry_price else 0
        trades.append({"day": len(closes), "side": "SELL", "price": round(close, 2), "pnl": round(pnl, 2)})
        equity_curve[-1]["equity"] = round(cash, 2)

    sells = [trade for trade in trades if trade["side"] == "SELL"]
    wins = [trade for trade in sells if trade.get("pnl", 0) > 0]
    losses = [abs(trade.get("pnl", 0)) for trade in sells if trade.get("pnl", 0) < 0]
    gross_wins = sum(trade.get("pnl", 0) for trade in wins)
    gross_losses = sum(losses)
    final_equity = equity_curve[-1]["equity"]
    roi = ((final_equity - 10_000.0) / 10_000.0) * 100
    benchmark_roi = ((closes[-1] - closes[0]) / closes[0]) * 100 if closes and closes[0] else 0
    invested_points = sum(1 for point in equity_curve if point["equity"] != 10_000.0)

    return {
        "asset": asset,
        "strategy": config.__dict__,
        "metrics": {
            "roi": round(roi, 2),
            "drawdown": round(max_drawdown([point["equity"] for point in equity_curve]), 2),
            "sharpe": round(sharpe_ratio([point["equity"] for point in equity_curve]), 2),
            "winRate": round((len(wins) / len(sells)) * 100, 2) if sells else 0.0,
            "trades": len(sells),
            "profitFactor": round(gross_wins / gross_losses, 2) if gross_losses else round(gross_wins, 2),
            "averageTrade": round(sum(trade.get("pnl", 0) for trade in sells) / len(sells), 2) if sells else 0.0,
            "benchmarkRoi": round(benchmark_roi, 2),
            "alpha": round(roi - benchmark_roi, 2),
            "exposure": round((invested_points / len(equity_curve)) * 100, 2) if equity_curve else 0.0,
        },
        "equityCurve": equity_curve,
        "trades": trades[-10:],
    }


def strategy_to_code(config: StrategyConfig) -> str:
    return f'''def run_backtest(df):
    family = "{config.family}"
    short_window = {config.short_window}
    long_window = {config.long_window}
    risk_multiplier = {config.risk_multiplier}
    stop_loss = {config.stop_loss}
    take_profit = {config.take_profit}
    conservative_filter = {config.conservative_filter}
    rsi_buy = {config.rsi_buy}
    rsi_sell = {config.rsi_sell}
    band_window = {config.band_window}
    band_std = {config.band_std}
    breakout_window = {config.breakout_window}
    volume_window = {config.volume_window}

    # Strategy: {config.name}
    # Family: {config.family}
    # This is the selected executable logic used by the local backtest engine.
    # df rows must contain: close, and optionally open/high/low/volume/time.

    def ma(values, end, window):
        start = max(0, end - window + 1)
        sample = values[start:end + 1]
        return sum(sample) / len(sample)

    def std(values, end, window):
        avg = ma(values, end, window)
        start = max(0, end - window + 1)
        sample = values[start:end + 1]
        if len(sample) < 2:
            return 0.0
        variance = sum((value - avg) ** 2 for value in sample) / (len(sample) - 1)
        return variance ** 0.5

    def rsi(values, end, window=14):
        if end < 1:
            return 50.0
        start = max(1, end - window + 1)
        gains = 0.0
        losses = 0.0
        periods = 0
        for idx in range(start, end + 1):
            change = values[idx] - values[idx - 1]
            gains += max(0.0, change)
            losses += max(0.0, -change)
            periods += 1
        if periods == 0 or losses == 0:
            return 100.0 if gains else 50.0
        rs = (gains / periods) / (losses / periods)
        return 100 - (100 / (1 + rs))

    def rolling_high(values, end, window):
        start = max(0, end - window)
        return max(values[start:end] or [values[end]])

    def rolling_low(values, end, window):
        start = max(0, end - window)
        return min(values[start:end] or [values[end]])

    closes = [float(row["close"]) for row in df]
    volumes = [float(row.get("volume", 0) or 0) for row in df]
    cash = 10000.0
    position = 0.0
    entry_price = 0.0
    trades = []
    equity_curve = []

    for idx, row in enumerate(df):
        close = closes[idx]
        short_ma = ma(closes, idx, short_window)
        long_ma = ma(closes, idx, long_window)
        macro_filter = close > ma(closes, idx, 80) if conservative_filter else True
        buy_signal = False
        sell_signal = False

        if family == "sma_cross":
            buy_signal = short_ma > long_ma and macro_filter and position == 0
            sell_signal = position > 0 and short_ma < long_ma

        elif family == "rsi_mean_reversion":
            current_rsi = rsi(closes, idx)
            buy_signal = current_rsi <= rsi_buy and close >= rolling_low(closes, idx, short_window) and position == 0
            sell_signal = position > 0 and (current_rsi >= rsi_sell or close >= ma(closes, idx, long_window))

        elif family == "bollinger_bounce":
            basis = ma(closes, idx, band_window)
            deviation = std(closes, idx, band_window)
            lower = basis - band_std * deviation
            upper = basis + band_std * deviation
            buy_signal = close <= lower and macro_filter and position == 0
            sell_signal = position > 0 and (close >= basis or close >= upper)

        elif family == "breakout_retest":
            prior_high = rolling_high(closes, idx, breakout_window)
            prior_low = rolling_low(closes, idx, breakout_window)
            buy_signal = close > prior_high and short_ma > long_ma and position == 0
            sell_signal = position > 0 and (close < short_ma or close < prior_low)

        elif family == "volume_trend":
            avg_volume = ma(volumes, idx, volume_window) if any(volumes) else 0
            volume_ok = volumes[idx] >= avg_volume * 1.05 if avg_volume else True
            buy_signal = short_ma > long_ma and volume_ok and macro_filter and position == 0
            sell_signal = position > 0 and (short_ma < long_ma or not macro_filter)

        if position > 0:
            trade_return = (close - entry_price) / entry_price
            sell_signal = sell_signal or trade_return <= -stop_loss or trade_return >= take_profit

        if buy_signal:
            allocation = cash * min(0.92, max(0.25, risk_multiplier))
            position = allocation / close
            cash -= allocation
            entry_price = close
            trades.append({{"side": "BUY", "time": row.get("time", idx + 1), "price": round(close, 2)}})

        elif sell_signal:
            cash += position * close
            pnl = ((close - entry_price) / entry_price) * 100 if entry_price else 0
            trades.append({{"side": "SELL", "time": row.get("time", idx + 1), "price": round(close, 2), "pnl": round(pnl, 2)}})
            position = 0.0
            entry_price = 0.0

        equity_curve.append({{"time": row.get("time", idx + 1), "equity": round(cash + position * close, 2)}})

    return {{"trades": trades, "equity_curve": equity_curve}}
'''
