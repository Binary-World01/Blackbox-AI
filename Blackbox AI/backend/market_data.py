from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Any

from backtester import generate_market_series

_MARKET_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
_FUNDAMENTALS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

_SYMBOL_ALIASES = {
    "BTC": ("BTC-USD", "Bitcoin USD"),
    "BTCUSD": ("BTC-USD", "Bitcoin USD"),
    "BTC/USD": ("BTC-USD", "Bitcoin USD"),
    "BTC USD": ("BTC-USD", "Bitcoin USD"),
    "BITCOIN": ("BTC-USD", "Bitcoin USD"),
    "BITCOIN USD": ("BTC-USD", "Bitcoin USD"),
    "ETH": ("ETH-USD", "Ethereum USD"),
    "ETHUSD": ("ETH-USD", "Ethereum USD"),
    "ETH/USD": ("ETH-USD", "Ethereum USD"),
    "ETH USD": ("ETH-USD", "Ethereum USD"),
    "ETHEREUM": ("ETH-USD", "Ethereum USD"),
    "SOL": ("SOL-USD", "Solana USD"),
    "SOLUSD": ("SOL-USD", "Solana USD"),
    "DOGE": ("DOGE-USD", "Dogecoin USD"),
    "DOGEUSD": ("DOGE-USD", "Dogecoin USD"),
}


def normalize_symbol(symbol: str) -> str:
    clean = " ".join(str(symbol or "").strip().upper().replace("-", " ").split())
    compact = clean.replace(" ", "")
    if symbol and "-" in str(symbol):
        compact = str(symbol).strip().upper()
    if compact in _SYMBOL_ALIASES:
        return _SYMBOL_ALIASES[compact][0]
    if clean in _SYMBOL_ALIASES:
        return _SYMBOL_ALIASES[clean][0]
    if compact.endswith("USD") and len(compact) > 3:
        base = compact[:-3]
        if base in {"BTC", "ETH", "SOL", "DOGE", "BNB", "ADA", "XRP", "AVAX", "LINK", "LTC"}:
            return f"{base}-USD"
    return str(symbol or "").strip().upper()


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 4)


def _rsi(values: list[float], window: int = 14) -> float | None:
    if len(values) <= window:
        return None
    gains = []
    losses = []
    for idx in range(len(values) - window, len(values)):
        change = values[idx] - values[idx - 1]
        if change >= 0:
            gains.append(change)
        else:
            losses.append(abs(change))
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _indicators(candles: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(candle["close"]) for candle in candles]
    if not closes:
        return {}
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    rsi14 = _rsi(closes, 14)
    pattern = "range-bound"
    if sma20 and sma50 and closes[-1] > sma20 > sma50:
        pattern = "bullish trend"
    elif sma20 and sma50 and closes[-1] < sma20 < sma50:
        pattern = "bearish trend"
    elif len(closes) > 2 and closes[-1] > closes[-2] > closes[-3]:
        pattern = "short momentum"
    elif len(closes) > 2 and closes[-1] < closes[-2] < closes[-3]:
        pattern = "short pullback"
    return {"sma20": sma20, "sma50": sma50, "rsi14": rsi14, "pattern": pattern}


def _market_state(candles: list[dict[str, Any]], interval: str) -> dict[str, Any]:
    if not candles:
        return {"state": "unknown", "reason": "no candles"}
    last_time = candles[-1]["time"]
    if isinstance(last_time, int):
        age_seconds = max(0, int(datetime.now(timezone.utc).timestamp()) - last_time)
        if interval.endswith("m") and age_seconds <= 180:
            return {"state": "live", "ageSeconds": age_seconds, "reason": "latest intraday candle is recent"}
        return {"state": "closed-or-delayed", "ageSeconds": age_seconds, "reason": "latest candle is not recent"}
    return {"state": "session-close", "reason": "daily candle data"}

def _synthetic_ohlc(symbol: str) -> dict[str, Any]:
    closes = generate_market_series(symbol, 220)
    candles = []
    for row in closes:
        close = row["close"]
        open_price = close * 0.992
        high = max(open_price, close) * 1.012
        low = min(open_price, close) * 0.988
        candles.append(
            {
                "time": int(row["day"]),
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close, 2),
                "volume": 0,
            }
        )
    return {
        "symbol": symbol,
        "source": "synthetic-fallback",
        "candles": candles,
        "indicators": _indicators(candles),
        "marketState": {"state": "demo", "reason": "synthetic fallback data"},
    }


def fetch_ohlc(symbol: str, period: str = "1y", interval: str = "1d") -> dict[str, Any]:
    """Fetch real market candles with yfinance, falling back to deterministic demo data."""
    symbol = normalize_symbol(symbol)
    key = (symbol.upper(), period, interval)
    ttl = 5.0 if interval.endswith("m") else 300.0
    cached = _MARKET_CACHE.get(key)
    if cached and monotonic() - cached[0] < ttl:
        payload = dict(cached[1])
        payload["cache"] = "hit"
        return payload

    try:
        import yfinance as yf

        frame = yf.download(
            tickers=symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        if frame is None or frame.empty:
            return _synthetic_ohlc(symbol)

        if hasattr(frame.columns, "nlevels") and frame.columns.nlevels > 1:
            frame.columns = [column[0] for column in frame.columns]

        frame = frame.dropna(subset=["Open", "High", "Low", "Close"])
        candles = []
        for index, row in frame.iterrows():
            if hasattr(index, "to_pydatetime"):
                stamp = index.to_pydatetime()
            elif isinstance(index, datetime):
                stamp = index
            else:
                stamp = datetime.fromisoformat(str(index))
            volume = row["Volume"] if "Volume" in row else 0
            if interval.endswith("m") or interval.endswith("h"):
                candle_time: str | int = int(stamp.timestamp())
            else:
                candle_time = stamp.date().isoformat()
            candles.append(
                {
                    "time": candle_time,
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(volume) if volume == volume else 0,
                }
            )

        if not candles:
            return _synthetic_ohlc(symbol)
        result = {
            "symbol": symbol,
            "source": "yfinance",
            "candles": candles[-420:],
            "indicators": _indicators(candles),
            "marketState": _market_state(candles, interval),
            "cache": "miss",
            "upstreamTtlSeconds": ttl,
        }
        _MARKET_CACHE[key] = (monotonic(), result)
        return result
    except Exception as exc:
        fallback = _synthetic_ohlc(symbol)
        fallback["warning"] = str(exc)
        return fallback


def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    symbol = normalize_symbol(symbol)
    key = symbol.upper()
    cached = _FUNDAMENTALS_CACHE.get(key)
    if cached and monotonic() - cached[0] < 1800:
        payload = dict(cached[1])
        payload["cache"] = "hit"
        return payload

    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info
        result = {
            "symbol": symbol,
            "source": "yfinance",
            "cache": "miss",
            "marketCap": info.get("marketCap"),
            "trailingPE": info.get("trailingPE"),
            "forwardPE": info.get("forwardPE"),
            "beta": info.get("beta"),
            "profitMargins": info.get("profitMargins"),
            "revenueGrowth": info.get("revenueGrowth"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "longName": info.get("longName") or info.get("shortName") or symbol,
        }
        _FUNDAMENTALS_CACHE[key] = (monotonic(), result)
        return result
    except Exception as exc:
        return {"symbol": symbol, "source": "fundamentals-fallback", "warning": str(exc)}


def search_symbols(query: str, max_results: int = 8) -> dict[str, Any]:
    clean = query.strip()
    if not clean:
        return {"query": query, "results": []}

    normalized = normalize_symbol(clean)
    alias_key = " ".join(clean.upper().replace("-", " ").split())
    compact_key = alias_key.replace(" ", "")
    alias = _SYMBOL_ALIASES.get(alias_key) or _SYMBOL_ALIASES.get(compact_key)
    if alias or normalized.endswith("-USD"):
        return {
            "query": query,
            "source": "symbol-normalizer",
            "results": [
                {
                    "symbol": normalized,
                    "name": alias[1] if alias else normalized,
                    "exchange": "CCC",
                    "type": "CRYPTOCURRENCY",
                }
            ],
        }

    try:
        import yfinance as yf

        search = yf.Search(clean, max_results=max_results)
        results = []
        for quote in search.quotes[:max_results]:
            symbol = quote.get("symbol")
            if not symbol:
                continue
            results.append(
                {
                    "symbol": symbol,
                    "name": quote.get("shortname") or quote.get("longname") or symbol,
                    "exchange": quote.get("exchange") or quote.get("exchDisp") or "",
                    "type": quote.get("quoteType") or "",
                }
            )
        if results:
            return {"query": query, "results": results, "source": "yfinance-search"}
    except Exception as exc:
        return {
            "query": query,
            "source": "symbol-fallback",
            "warning": str(exc),
            "results": [{"symbol": clean.upper(), "name": clean.upper(), "exchange": "", "type": ""}],
        }

    return {
        "query": query,
        "source": "symbol-fallback",
        "results": [{"symbol": clean.upper(), "name": clean.upper(), "exchange": "", "type": ""}],
    }
