const state = {
  activeSymbol: "TSLA",
  activeName: "Tesla, Inc.",
  marketData: null,
  lastResult: null,
  tvChart: null,
  candleSeries: null,
  sma20Series: null,
  sma50Series: null,
  pollTimer: null,
  pulseTimer: null,
  activeChartSymbol: null,
  visibleCandles: [],
  lastNetworkFetch: 0,
  marketState: "unknown",
};

const $ = (id) => document.getElementById(id);

function money(value) {
  if (value === undefined || value === null || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(2);
}

function currentQuery() {
  return $("symbolInput").value.trim() || state.activeSymbol;
}

function setBusy(isBusy, label = "Working...") {
  $("startBtn").disabled = isBusy;
  $("loadMarketBtn").disabled = isBusy;
  $("searchBtn").disabled = isBusy;
  if (isBusy) $("startBtn").textContent = label;
  else $("startBtn").textContent = `Optimize ${state.activeSymbol}`;
}

function drawLineChart(canvas, points) {
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#070a0f";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "rgba(148, 163, 184, 0.18)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i += 1) {
    const y = (height / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  if (!points || points.length < 2) return;
  const values = points.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(1, max - min);
  ctx.strokeStyle = values.at(-1) >= values[0] ? "#76f29b" : "#ff6676";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = 10 + (index / (points.length - 1)) * (width - 20);
    const y = height - 12 - ((point.equity - min) / range) * (height - 24);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function drawCandles(candles) {
  const canvas = $("priceChart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#070a0f";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(148, 163, 184, 0.16)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 6; i += 1) {
    const y = (height / 6) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  if (!candles || candles.length < 2) return;

  const visible = candles.slice(-120);
  const highs = visible.map((candle) => candle.high);
  const lows = visible.map((candle) => candle.low);
  const max = Math.max(...highs);
  const min = Math.min(...lows);
  const range = Math.max(0.01, max - min);
  const plotTop = 18;
  const plotHeight = height - 42;
  const step = width / visible.length;
  const candleWidth = Math.max(3, Math.min(10, step * 0.58));

  function y(price) {
    return plotTop + (max - price) / range * plotHeight;
  }

  visible.forEach((candle, index) => {
    const x = index * step + step / 2;
    const up = candle.close >= candle.open;
    const color = up ? "#4ddac7" : "#ff6676";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x, y(candle.high));
    ctx.lineTo(x, y(candle.low));
    ctx.stroke();
    const bodyTop = y(Math.max(candle.open, candle.close));
    const bodyBottom = y(Math.min(candle.open, candle.close));
    ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, Math.max(2, bodyBottom - bodyTop));
  });

  const last = candles.at(-1);
  $("openMetric").textContent = money(last.open);
  $("highMetric").textContent = money(last.high);
  $("lowMetric").textContent = money(last.low);
  $("closeMetric").textContent = money(last.close);
  $("candleCount").textContent = `${candles.length} candles`;
}

function lineData(candles, windowSize) {
  const values = [];
  for (let index = 0; index < candles.length; index += 1) {
    if (index + 1 < windowSize) continue;
    const slice = candles.slice(index + 1 - windowSize, index + 1);
    const value = slice.reduce((sum, candle) => sum + candle.close, 0) / windowSize;
    values.push({ time: candles[index].time, value: Number(value.toFixed(4)) });
  }
  return values;
}

function renderTradingChart(candles, indicators = {}, forceFit = false) {
  state.visibleCandles = candles.map((candle) => ({ ...candle }));
  if (window.LightweightCharts && $("tvChart")) {
    $("tvChart").classList.remove("hidden");
    $("priceChart").classList.add("hidden");
    if (!state.tvChart) {
      state.tvChart = LightweightCharts.createChart($("tvChart"), {
        layout: { background: { color: "#070a0f" }, textColor: "#94a3b8" },
        grid: { vertLines: { color: "#161d28" }, horzLines: { color: "#161d28" } },
        rightPriceScale: { borderColor: "#273241" },
        timeScale: { borderColor: "#273241", timeVisible: true, secondsVisible: false },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
      });
      state.candleSeries = state.tvChart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: "#4ddac7",
        downColor: "#ff6676",
        borderVisible: false,
        wickUpColor: "#4ddac7",
        wickDownColor: "#ff6676",
      });
      state.sma20Series = state.tvChart.addSeries(LightweightCharts.LineSeries, {
        color: "#69a7ff",
        lineWidth: 1,
        priceLineVisible: false,
      });
      state.sma50Series = state.tvChart.addSeries(LightweightCharts.LineSeries, {
        color: "#f6c667",
        lineWidth: 1,
        priceLineVisible: false,
      });
      window.addEventListener("resize", () => {
        state.tvChart?.resize($("tvChart").clientWidth, 430);
      });
    }
    state.tvChart.resize($("tvChart").clientWidth, 430);
    state.candleSeries.setData(candles);
    state.sma20Series.setData(lineData(candles, 20));
    state.sma50Series.setData(lineData(candles, 50));
    if (forceFit) {
      state.tvChart.timeScale().fitContent();
    }
  } else {
    $("tvChart").classList.add("hidden");
    $("priceChart").classList.remove("hidden");
    drawCandles(candles);
  }

  const last = candles.at(-1);
  if (last) {
    $("openMetric").textContent = money(last.open);
    $("highMetric").textContent = money(last.high);
    $("lowMetric").textContent = money(last.low);
    $("closeMetric").textContent = money(last.close);
  }
  $("rsiMetric").textContent = indicators.rsi14 ?? "--";
  $("sma20Metric").textContent = indicators.sma20 ? money(indicators.sma20) : "--";
  $("sma50Metric").textContent = indicators.sma50 ? money(indicators.sma50) : "--";
  $("patternMetric").textContent = indicators.pattern ?? "--";
  $("candleCount").textContent = `${candles.length} candles`;
}

function updateLastPriceDisplay(candle) {
  $("openMetric").textContent = money(candle.open);
  $("highMetric").textContent = money(candle.high);
  $("lowMetric").textContent = money(candle.low);
  $("closeMetric").textContent = money(candle.close);
}

function pulseLastCandle() {
  const elapsed = Date.now() - state.lastNetworkFetch;
  const suffix = `${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}.${String(Date.now() % 1000).padStart(3, "0")}`;
  $("liveBadge").textContent = `${state.marketState} | checked ${elapsed}ms ago | ${suffix}`;
}

function addLog(log) {
  const item = document.createElement("p");
  item.className = `log ${log.agent === "trader" ? "trader" : log.agent === "system" ? "system" : "researcher"}`;
  item.textContent = log.text;
  $("debateFeed").appendChild(item);
  $("debateFeed").scrollTop = $("debateFeed").scrollHeight;
}

function renderMemory(nodes) {
  $("memoryCount").textContent = `${nodes.length} nodes`;
  $("memoryWeb").innerHTML = "";
  nodes.slice(-8).reverse().forEach((node) => {
    const item = document.createElement("div");
    item.className = "memory-node";
    item.textContent = `${node.kind} g${node.generation}: ${node.text}`;
    $("memoryWeb").appendChild(item);
  });
}

function setInspectorState(status, name, logic, frame, data) {
  $("strategyStatus").textContent = status;
  $("strategyName").textContent = name;
  $("strategyLogic").textContent = logic;
  $("strategyFrame").textContent = frame;
  $("strategyData").textContent = data;
}

function renderEmptyTables() {
  $("tradeSummary").textContent = "waiting";
  $("candidateSummary").textContent = "waiting";
  renderMiniTable(
    "tradeTable",
    [
      { label: "Side", value: (row) => row.side },
      { label: "Time", value: (row) => row.time },
      { label: "Price", value: (row) => row.price },
      { label: "PnL", value: (row) => row.pnl },
    ],
    [],
    { minWidth: "430px" },
  );
  renderMiniTable(
    "candidateTable",
    [
      { label: "Rank", value: (_row, index) => index + 1 },
      { label: "Strategy", value: (row) => row.strategy },
      { label: "Frame", value: (row) => row.frame },
      { label: "ROI", value: (row) => row.roi },
      { label: "Win", value: (row) => row.win },
      { label: "PF", value: (row) => row.pf },
      { label: "DD", value: (row) => row.dd },
    ],
    [],
    { minWidth: "780px" },
  );
}

function algorithmCopy(strategy) {
  const family = strategy.family || "sma_cross";
  const copy = {
    sma_cross:
      `Buy when short SMA ${strategy.short_window} is above long SMA ${strategy.long_window}. Exit on bearish cross, stop loss ${(strategy.stop_loss * 100).toFixed(1)}%, or take profit ${(strategy.take_profit * 100).toFixed(1)}%.`,
    rsi_mean_reversion:
      `Buy oversold pullbacks when RSI is at or below ${strategy.rsi_buy} near the recent low. Exit when RSI reaches ${strategy.rsi_sell}, price mean-reverts, stop loss, or take profit triggers.`,
    bollinger_bounce:
      `Buy lower-band mean reversion using a ${strategy.band_window}-candle Bollinger window at ${strategy.band_std} standard deviations. Exit near the basis/upper band or risk stops.`,
    breakout_retest:
      `Buy confirmed breakouts above the prior ${strategy.breakout_window}-candle high when SMA ${strategy.short_window}/${strategy.long_window} trend agrees. Exit under short SMA, prior low, stop loss, or take profit.`,
    volume_trend:
      `Buy trend continuation when SMA ${strategy.short_window}/${strategy.long_window} is bullish and volume is at least 5% above its ${strategy.volume_window}-candle average. Exit on trend failure, filter failure, stop loss, or take profit.`,
  };
  return copy[family] || copy.sma_cross;
}

function signedClass(value) {
  return Number(value) >= 0 ? "positive" : "negative";
}

function renderMiniTable(target, columns, rows, options = {}) {
  const table = $(target);
  table.innerHTML = "";
  const head = document.createElement("div");
  head.className = "mini-row head";
  head.style.setProperty("--cols", columns.length);
  head.style.setProperty("--min-width", options.minWidth || "420px");
  columns.forEach((column) => {
    const cell = document.createElement("span");
    cell.textContent = column.label;
    head.appendChild(cell);
  });
  table.appendChild(head);

  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "mini-row";
    empty.style.setProperty("--cols", columns.length);
    empty.style.setProperty("--min-width", options.minWidth || "420px");
    const cell = document.createElement("span");
    cell.textContent = "No rows yet";
    cell.style.gridColumn = `span ${columns.length}`;
    empty.appendChild(cell);
    table.appendChild(empty);
    return;
  }

  rows.forEach((row, index) => {
    const line = document.createElement("div");
    line.className = "mini-row";
    line.style.setProperty("--cols", columns.length);
    line.style.setProperty("--min-width", options.minWidth || "420px");
    columns.forEach((column) => {
      const cell = document.createElement("span");
      const value = column.value(row, index);
      cell.textContent = value;
      if (column.className) cell.className = column.className(row);
      line.appendChild(cell);
    });
    table.appendChild(line);
  });
}

function renderInspector(result) {
  const latest = result.latest;
  const strategy = latest.strategy || {};
  const metrics = latest.metrics || {};
  const frame = latest.timeframe?.label || "selected frame";
  const trades = latest.trades || [];
  const topCandidates = [...(result.generations || [])]
    .sort((a, b) => Number(b.score) - Number(a.score))
    .slice(0, 6);

  $("strategyStatus").textContent = `${result.mode} | g${latest.generation}`;
  $("strategyName").textContent = strategy.name || "Generated strategy";
  $("strategyLogic").textContent = algorithmCopy(strategy);
  $("strategyFrame").textContent = `${latest.asset || result.asset} on ${frame}`;
  $("strategyData").textContent =
    `${result.marketData?.source || "market data"} feed; tested ${result.generations?.length || 0} candidate-timeframe runs. ` +
    `Selected ROI ${metrics.roi > 0 ? "+" : ""}${metrics.roi}%, win rate ${metrics.winRate}%, PF ${metrics.profitFactor}.`;

  const params = [
    ["family", strategy.family],
    ["short SMA", strategy.short_window],
    ["long SMA", strategy.long_window],
    ["risk", strategy.risk_multiplier],
    ["stop", `${(strategy.stop_loss * 100).toFixed(2)}%`],
    ["take", `${(strategy.take_profit * 100).toFixed(2)}%`],
    ["RSI buy", strategy.rsi_buy],
    ["RSI sell", strategy.rsi_sell],
    ["breakout", strategy.breakout_window],
    ["volume", strategy.volume_window],
    ["Bollinger", `${strategy.band_window} / ${strategy.band_std}`],
    ["filter", strategy.conservative_filter ? "on" : "off"],
  ];
  $("strategyParams").innerHTML = "";
  params.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.innerHTML = `<span>${label}</span><strong>${value ?? "--"}</strong>`;
    $("strategyParams").appendChild(item);
  });

  $("tradeSummary").textContent = `${trades.length} shown`;
  renderMiniTable(
    "tradeTable",
    [
      { label: "Side", value: (row) => row.side },
      { label: "Time", value: (row) => row.time || row.day || "--" },
      { label: "Price", value: (row) => money(row.price) },
      {
        label: "PnL",
        value: (row) => (row.pnl === undefined ? "--" : `${row.pnl > 0 ? "+" : ""}${row.pnl}%`),
        className: (row) => (row.pnl === undefined ? "" : signedClass(row.pnl)),
      },
    ],
    trades,
    { minWidth: "430px" },
  );

  $("candidateSummary").textContent = `${topCandidates.length} of ${result.generations?.length || 0}`;
  renderMiniTable(
    "candidateTable",
    [
      { label: "Rank", value: (_row, index) => index + 1 },
      { label: "Strategy", value: (row) => row.strategy?.name || "--" },
      { label: "Frame", value: (row) => row.timeframe?.label || "--" },
      {
        label: "ROI",
        value: (row) => `${row.metrics.roi > 0 ? "+" : ""}${row.metrics.roi}%`,
        className: (row) => signedClass(row.metrics.roi),
      },
      { label: "Win", value: (row) => `${row.metrics.winRate}%` },
      { label: "PF", value: (row) => row.metrics.profitFactor },
      { label: "DD", value: (row) => `${row.metrics.drawdown}%` },
    ],
    topCandidates.map((row, index) => ({ ...row, rank: index + 1 })),
    { minWidth: "780px" },
  );
}

function renderMetrics(result) {
  const metrics = result.latest.metrics;
  $("roiBadge").textContent = `ROI ${metrics.roi > 0 ? "+" : ""}${metrics.roi}%`;
  $("drawdownMetric").textContent = `${metrics.drawdown}%`;
  $("sharpeMetric").textContent = metrics.sharpe;
  $("winMetric").textContent = `${metrics.winRate}%`;
  $("tradeMetric").textContent = metrics.trades;
  $("profitFactorMetric").textContent = metrics.profitFactor;
  $("alphaMetric").textContent = `${metrics.alpha > 0 ? "+" : ""}${metrics.alpha}%`;
  $("avgTradeMetric").textContent = `${metrics.averageTrade > 0 ? "+" : ""}${metrics.averageTrade}%`;
  $("exposureMetric").textContent = `${metrics.exposure}%`;
  $("codeCanvas").textContent = result.code;
  $("modePill").textContent = result.mode;
  $("providerLabel").textContent = result.cascadeMetrics.activeRouter;
  drawLineChart($("yieldChart"), result.latest.equityCurve);
  renderInspector(result);

  const cascade = result.cascadeMetrics;
  $("savingsMetric").textContent = `${cascade.savingsPct}%`;
  $("costCopy").textContent =
    `$${cascade.estimatedCost.toFixed(4)} via Groq lane vs $${cascade.flatPremiumCost.toFixed(2)} flat premium routing.`;
}

async function resolveQuery(showSuggestions = true) {
  const query = currentQuery();
  const response = await fetch(`/api/search-symbols?q=${encodeURIComponent(query)}`);
  const payload = await response.json();
  $("suggestions").innerHTML = "";
  if (showSuggestions) {
    payload.results.forEach((result) => {
      const button = document.createElement("button");
      button.className = "suggestion";
      button.type = "button";
      button.innerHTML = `<strong>${result.symbol}</strong><span>${result.name}</span>`;
      button.addEventListener("click", () => {
        state.activeSymbol = result.symbol;
        state.activeName = result.name;
        $("symbolInput").value = result.name;
        $("activeSymbol").textContent = result.symbol;
        $("suggestions").innerHTML = "";
        loadMarket();
      });
      $("suggestions").appendChild(button);
    });
  }
  if (payload.results[0]) {
    state.activeSymbol = payload.results[0].symbol;
    state.activeName = payload.results[0].name;
    $("activeSymbol").textContent = state.activeSymbol;
  }
  return payload.results[0] || null;
}

async function loadMarket() {
  setBusy(true, "Loading...");
  await resolveQuery(false);
  setInspectorState(
    "market loading",
    state.activeSymbol,
    "Fetching yfinance candles. After the chart loads, press Optimize to generate and test the strategy.",
    "waiting for candles",
    "The strategy inspector fills after the optimizer runs.",
  );
  $("dataSource").textContent = `loading ${state.activeSymbol}...`;
  $("liveBadge").textContent = "fetching yfinance";
  const response = await fetch(`/api/market-data?symbol=${encodeURIComponent(state.activeSymbol)}&period=1d&interval=1m`);
  const market = await response.json();
  state.lastNetworkFetch = Date.now();
  const symbolChanged = state.activeChartSymbol !== market.symbol;
  state.activeChartSymbol = market.symbol;
  state.marketData = market;
  state.marketState = market.marketState?.state || "unknown";
  $("activeSymbol").textContent = market.symbol;
  $("dataSource").textContent = `${market.source} 1m ${state.marketState}${market.warning ? " fallback" : ""}`;
  renderTradingChart(market.candles || [], market.indicators || {}, symbolChanged);
  if (!state.lastResult) {
    setInspectorState(
      "ready to optimize",
      market.symbol,
      "Market data is loaded. Press Optimize to let Q-Researcher generate candidates and Q-Trader audit the selected strategy.",
      `${market.candles?.length || 0} x 1m candles`,
      `${market.source} ${state.marketState}; latest close ${market.candles?.at(-1)?.close ?? "--"}.`,
    );
    renderEmptyTables();
  }
  startPolling();
  startPulse();
  setBusy(false);
}

async function refreshMarket() {
  if (!state.activeSymbol) return;
  $("dataSource").textContent = `fetching ${state.activeSymbol}...`;
  const response = await fetch(`/api/market-data?symbol=${encodeURIComponent(state.activeSymbol)}&period=1d&interval=1m`);
  const market = await response.json();
  state.lastNetworkFetch = Date.now();
  state.marketData = market;
  state.marketState = market.marketState?.state || "unknown";
  $("dataSource").textContent = `${market.source} 1m ${market.cache === "hit" ? "cached" : "fresh"} ${state.marketState}`;
  renderTradingChart(market.candles || [], market.indicators || {}, false);
  $("liveBadge").textContent = `tick ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

function startPolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = setInterval(refreshMarket, 500);
}

function startPulse() {
  clearInterval(state.pulseTimer);
  state.pulseTimer = setInterval(pulseLastCandle, 1);
}

async function runLoop(feedback = "") {
  setBusy(true, "Optimizing...");
  await resolveQuery(false);
  setInspectorState(
    "optimizer running",
    state.activeSymbol,
    "Q-Researcher is generating strategy candidates. Local backtester is testing them across intraday and long-history frames.",
    "searching frames",
    "This usually takes a few seconds because it pulls yfinance data and scores hundreds of candidate-timeframe runs.",
  );
  if (!feedback) $("debateFeed").innerHTML = "";
  const response = await fetch("/api/start-optimization", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ asset: state.activeSymbol, feedback, generations: 3 }),
  });
  const result = await response.json();
  state.lastResult = result;
  renderMetrics(result);
  renderMemory(result.memoryNodes);
  if (result.marketData?.candles) {
    $("dataSource").textContent = `${state.marketData?.source || result.marketData.source} 1m`;
  }
  result.logs.forEach((log, index) => setTimeout(() => addLog(log), index * 120));
  setBusy(false);
}

$("searchBtn").addEventListener("click", () => resolveQuery(true));
$("symbolInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter") resolveQuery(true);
});
$("loadMarketBtn").addEventListener("click", loadMarket);
$("startBtn").addEventListener("click", () => runLoop());
$("feedbackForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const feedback = $("feedbackInput").value.trim();
  if (feedback) runLoop(feedback);
});

renderMemory([]);
drawLineChart($("yieldChart"), []);
resolveQuery(false).then(loadMarket);
