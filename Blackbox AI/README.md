# BlackBox AI Quant Lab

Hackathon-ready multi-agent quantitative strategy lab with real market data,
Groq-routed research agents, local backtesting, TradingView Lightweight Charts,
and a retrieval-linked Hindsight memory loop.

## Features

- Dark quant terminal UI with market chart, strategy inspector, agent debate,
  generated Python strategy code, Hindsight memory, and backtest analytics.
- yfinance adapter for real OHLC candles, including stock symbols and crypto
  aliases such as `BTCUSD`, `BTC USD`, and `bitcoin` -> `BTC-USD`.
- TradingView Lightweight Charts frontend using our yfinance candles.
- Q-Researcher / Q-Trader optimization loop routed through Groq when
  `GROQ_API_KEY` is available.
- Local multi-family backtester covering SMA crossover, RSI mean reversion,
  Bollinger bounce, breakout retest, and volume trend strategies.
- Metrics: ROI, drawdown, Sharpe, win rate, trades, profit factor, alpha,
  average trade, exposure, and equity curve.
- Hindsight memory with local vector-style recall. Past failures, user feedback,
  best strategies, metrics, timeframe, and asset metadata are retrieved and fed
  into future optimization runs.
- cascadeflow-style router telemetry for AI route status and estimated cost
  comparison.

## Architecture

```text
frontend/
  index.html       Dark quant terminal UI
  app.js           Charting, polling, optimization calls, inspector rendering
  styles.css       Responsive dark workstation design

backend/
  server.py        Stdlib HTTP API/server
  market_data.py   yfinance candles, symbol normalization, fundamentals
  agent.py         Q-Researcher/Q-Trader loop, optimizer, Hindsight recall
  backtester.py    Strategy engine and generated strategy code
  cascadeflow.py   Groq router with deterministic fallback
  env_loader.py    .env loader
```

## Setup

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Add your Groq key:

```text
GROQ_API_KEY=your_key_here
GROQ_MODEL=qwen/qwen3-32b
```

Install runtime packages if needed:

```powershell
pip install yfinance pandas requests
```

## Run

```powershell
python backend/server.py
```

Open:

```text
http://127.0.0.1:8000
```

## Demo Flow

1. Enter an asset such as `TSLA`, `AAPL`, `RELIANCE.NS`, `BTCUSD`, or `bitcoin`.
2. Click `Load Market` to pull yfinance candles.
3. Click `Optimize`.
4. Inspect the generated algorithm, parameters, trades, top candidates, and
   metrics in Strategy Inspector.
5. Add feedback such as `lower drawdown and use stricter trend confirmation`.
6. Click `Resume Loop`.
7. Hindsight recalls relevant past critiques/results and changes the next search.

## Hindsight Memory

This project uses a local Hindsight implementation in `backend/agent.py`.
It stores memory nodes with:

- asset
- memory kind
- generation
- strategy metadata
- metrics
- timeframe
- critique or guidance text

On every optimization run, it builds a lightweight text vector and recalls the
most relevant nodes for the current asset and feedback. Those recalled nodes are
used in strategy candidate generation, scoring, and final Q-Researcher review.

The persisted memory file is intentionally gitignored:

```text
backend/data/hindsight_memory.json
```

## Security

Do not commit `.env` or API keys. The repository ignores:

```text
.env
backend/data/hindsight_memory.json
__pycache__/
*.pyc
```

## Notes

yfinance is not a true tick-streaming market data provider. The UI can poll
quickly, but upstream data freshness depends on Yahoo/yfinance availability and
market session state.
