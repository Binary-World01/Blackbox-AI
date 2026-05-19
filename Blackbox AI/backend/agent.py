from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backtester import StrategyConfig, run_backtest, strategy_to_code
from cascadeflow import CascadeRouter
from market_data import fetch_fundamentals, fetch_ohlc, normalize_symbol


DATA_DIR = Path(__file__).resolve().parent / "data"
MEMORY_PATH = DATA_DIR / "hindsight_memory.json"


def load_memory() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MEMORY_PATH.exists():
        return []
    with MEMORY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_memory(memories: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with MEMORY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(memories[-72:], handle, indent=2)


def append_memory(
    kind: str,
    text: str,
    generation: int,
    asset: str = "",
    strategy: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    timeframe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    memories = load_memory()
    node = {
        "id": f"mem-{len(memories) + 1}",
        "kind": kind,
        "asset": normalize_symbol(asset) if asset else "",
        "generation": generation,
        "text": text,
        "weight": min(1.0, 0.55 + generation * 0.1),
        "strategy": strategy or {},
        "metrics": metrics or {},
        "timeframe": timeframe or {},
    }
    memories.append(node)
    save_memory(memories)
    return node


def _tokens(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "but",
        "into",
        "rate",
        "strategy",
        "return",
    }
    return [token for token in re.findall(r"[a-z0-9_./%-]+", text.lower()) if token not in stop and len(token) > 2]


def _memory_text(memory: dict[str, Any]) -> str:
    strategy = memory.get("strategy") or {}
    metrics = memory.get("metrics") or {}
    timeframe = memory.get("timeframe") or {}
    parts = [
        str(memory.get("asset", "")),
        str(memory.get("kind", "")),
        str(memory.get("text", "")),
        str(strategy.get("name", "")),
        str(strategy.get("family", "")),
        str(timeframe.get("label", "")),
        f"roi {metrics.get('roi', '')}",
        f"win {metrics.get('winRate', '')}",
        f"drawdown {metrics.get('drawdown', '')}",
        f"profit factor {metrics.get('profitFactor', '')}",
    ]
    return " ".join(parts)


def _cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in overlap)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def retrieve_hindsight(asset: str, feedback: str, memories: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    canonical_asset = normalize_symbol(asset)
    query = Counter(_tokens(f"{canonical_asset} {feedback} win rate drawdown roi profit factor strategy"))
    scored: list[tuple[float, dict[str, Any]]] = []
    for memory in memories:
        memory_vector = Counter(_tokens(_memory_text(memory)))
        score = _cosine(query, memory_vector)
        if memory.get("asset") == canonical_asset:
            score += 0.55
        if memory.get("kind") in {"best-strategy", "trader-critique", "win-rate-gate-failure", "user-guidance"}:
            score += 0.12
        metrics = memory.get("metrics") or {}
        if float(metrics.get("winRate") or 0) >= 50:
            score += 0.08
        scored.append((score, memory))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [memory for score, memory in scored[:limit] if score > 0]


def _intent_text(feedback: str, memories: list[dict[str, Any]]) -> str:
    return " ".join([feedback] + [memory["text"] for memory in memories]).lower()


def derive_strategy(generation: int, feedback: str, memories: list[dict[str, Any]]) -> StrategyConfig:
    text = " ".join([feedback] + [memory["text"] for memory in memories]).lower()
    conservative = any(word in text for word in ["conservative", "drawdown", "safer", "risk", "sma filter"])

    if conservative:
        presets = [
            StrategyConfig("Conservative SMA Recovery v4", 8, 34, 0.58, 0.035, 0.12, True),
            StrategyConfig("Drawdown-Capped Momentum v5", 10, 42, 0.52, 0.028, 0.105, True),
            StrategyConfig("Hindsight Conservative Breakout v6", 12, 48, 0.48, 0.024, 0.095, True),
        ]
    else:
        presets = [
            StrategyConfig("Fast SMA Breakout v1", 5, 18, 0.9, 0.02, 0.09, False),
            StrategyConfig("Volatility Aware Crossover v2", 7, 26, 0.78, 0.028, 0.11, False),
            StrategyConfig("Balanced Momentum Ladder v3", 9, 31, 0.68, 0.038, 0.13, False),
        ]

    return presets[min(generation - 1, len(presets) - 1)]


def strategy_candidates(feedback: str, memories: list[dict[str, Any]], count: int) -> list[StrategyConfig]:
    text = _intent_text(feedback, memories)
    conservative = any(word in text for word in ["conservative", "drawdown", "safer", "risk", "capital protection"])
    strict_drawdown = any(phrase in text for phrase in ["much lower", "lower drawdown", "strict", "stricter", "minimum drawdown"])
    aggressive = any(word in text for word in ["aggressive", "higher roi", "maximize return", "more profit"])
    sma_filter = any(word in text for word in ["sma", "trend filter", "filter", "higher-timeframe"])
    resume_seed = len(memories) % 9

    configs: list[StrategyConfig] = [
        StrategyConfig("Professional Micro-Scalper Alpha v1", 9, 18, 0.70, 0.05, 0.004, True),
        StrategyConfig("Professional Micro-Scalper Alpha v2", 9, 18, 0.55, 0.03, 0.004, True),
        StrategyConfig("RSI Mean Reversion Pro v1", 8, 24, 0.55, 0.025, 0.018, False, "rsi_mean_reversion", 32, 58),
        StrategyConfig("RSI Mean Reversion Pro v2", 10, 30, 0.45, 0.02, 0.015, False, "rsi_mean_reversion", 36, 62),
        StrategyConfig("Bollinger Bounce Pro v1", 8, 34, 0.50, 0.025, 0.02, True, "bollinger_bounce", 35, 62, 20, 2.0),
        StrategyConfig("Bollinger Bounce Pro v2", 10, 40, 0.42, 0.018, 0.016, True, "bollinger_bounce", 35, 62, 24, 1.7),
        StrategyConfig("Breakout Retest Pro v1", 6, 28, 0.60, 0.035, 0.032, True, "breakout_retest", 35, 62, 20, 2.0, 18),
        StrategyConfig("Volume Confirmed Trend Pro v1", 7, 30, 0.55, 0.03, 0.028, True, "volume_trend", 35, 62, 20, 2.0, 24, 18),
        StrategyConfig("Win-Rate Scalper Gate v1", 3, 15, 0.55, 0.05, 0.006, True),
        StrategyConfig("Win-Rate Scalper Gate v2", 3, 15, 0.45, 0.03, 0.006, True),
        StrategyConfig("Win-Rate Scalper Gate v3", 4, 20, 0.35, 0.05, 0.01, True),
        StrategyConfig("Win-Rate Scalper Gate v4", 5, 24, 0.35, 0.04, 0.012, True),
    ]
    for idx in range(count):
        step = idx + resume_seed
        if conservative:
            short_window = 6 + (step % 9) * 2
            long_window = 28 + (step % 8) * 7
            start_risk = 0.5 if strict_drawdown else 0.62
            risk = max(0.2, start_risk - idx * 0.04)
            stop_start = 0.032 if strict_drawdown else 0.04
            take_start = 0.105 if strict_drawdown else 0.125
            stop = max(0.012, stop_start - idx * 0.0025)
            take = max(0.045, take_start - idx * 0.004)
            filter_on = True
            name = f"Hindsight Drawdown Search v{idx + 1}"
        elif aggressive:
            short_window = 4 + (step % 8)
            long_window = 16 + (step % 10) * 3
            risk = min(0.92, 0.7 + idx * 0.025)
            stop = min(0.065, 0.028 + idx * 0.003)
            take = min(0.22, 0.11 + idx * 0.012)
            filter_on = idx > 3
            name = f"Return Maximizer Search v{idx + 1}"
        else:
            short_window = 5 + (step % 10)
            long_window = 20 + (step % 9) * 5
            risk = max(0.38, 0.82 - idx * 0.04)
            stop = min(0.06, 0.024 + idx * 0.003)
            take = min(0.18, 0.09 + idx * 0.008)
            filter_on = sma_filter or idx >= 3
            name = f"Adaptive Momentum Search v{idx + 1}"

        if long_window <= short_window + 8:
            long_window = short_window + 12

        configs.append(
            StrategyConfig(
                name=name,
                short_window=short_window,
                long_window=long_window,
                risk_multiplier=round(risk, 3),
                stop_loss=round(stop, 4),
                take_profit=round(take, 4),
                conservative_filter=filter_on,
            )
        )

    for idx in range(max(10, count // 2)):
        configs.extend(
            [
                StrategyConfig(
                    f"RSI Sweep v{idx + 1}",
                    6 + idx % 8,
                    20 + (idx % 8) * 4,
                    round(max(0.28, 0.62 - idx * 0.02), 3),
                    round(0.018 + (idx % 5) * 0.004, 4),
                    round(0.012 + (idx % 6) * 0.004, 4),
                    False,
                    "rsi_mean_reversion",
                    28 + idx % 10,
                    56 + idx % 12,
                ),
                StrategyConfig(
                    f"Bollinger Sweep v{idx + 1}",
                    8 + idx % 6,
                    28 + (idx % 7) * 4,
                    round(max(0.30, 0.58 - idx * 0.018), 3),
                    round(0.018 + (idx % 5) * 0.004, 4),
                    round(0.014 + (idx % 6) * 0.005, 4),
                    True,
                    "bollinger_bounce",
                    35,
                    62,
                    16 + idx % 14,
                    round(1.55 + (idx % 6) * 0.15, 2),
                ),
                StrategyConfig(
                    f"Breakout Sweep v{idx + 1}",
                    4 + idx % 8,
                    18 + (idx % 8) * 5,
                    round(min(0.8, 0.45 + idx * 0.018), 3),
                    round(0.022 + (idx % 6) * 0.005, 4),
                    round(0.02 + (idx % 7) * 0.007, 4),
                    True,
                    "breakout_retest",
                    35,
                    62,
                    20,
                    2.0,
                    12 + idx % 22,
                ),
                StrategyConfig(
                    f"Volume Trend Sweep v{idx + 1}",
                    5 + idx % 8,
                    20 + (idx % 8) * 4,
                    round(min(0.75, 0.42 + idx * 0.016), 3),
                    round(0.02 + (idx % 5) * 0.004, 4),
                    round(0.018 + (idx % 6) * 0.006, 4),
                    True,
                    "volume_trend",
                    35,
                    62,
                    20,
                    2.0,
                    24,
                    12 + idx % 18,
                ),
            ]
        )

    deduped: list[StrategyConfig] = []
    seen: set[tuple[str, int, int, float, float, float, bool, float, float, int, float, int, int]] = set()
    for config in configs:
        key = (
            config.family,
            config.short_window,
            config.long_window,
            config.risk_multiplier,
            config.stop_loss,
            config.take_profit,
            config.conservative_filter,
            config.rsi_buy,
            config.rsi_sell,
            config.band_window,
            config.band_std,
            config.breakout_window,
            config.volume_window,
        )
        if key not in seen:
            seen.add(key)
            deduped.append(config)
    return deduped


def score_metrics(metrics: dict[str, Any], feedback: str, memories: list[dict[str, Any]]) -> float:
    text = _intent_text(feedback, memories)
    conservative = any(word in text for word in ["conservative", "drawdown", "safer", "risk"])
    strict_drawdown = any(phrase in text for phrase in ["much lower", "lower drawdown", "strict", "stricter", "minimum drawdown"])
    roi = float(metrics["roi"])
    drawdown = float(metrics["drawdown"])
    sharpe = float(metrics["sharpe"])
    win_rate = float(metrics["winRate"])
    trades = float(metrics["trades"])
    profit_factor = float(metrics.get("profitFactor", 0))
    alpha = float(metrics.get("alpha", 0))
    drawdown_weight = 2.2 if strict_drawdown else 1.2 if conservative else 0.65
    professional_gate = win_rate >= 50 and trades >= 8 and roi >= 0.08 and profit_factor >= 1.05
    win_gate_bonus = 140 if professional_gate else 35 if win_rate >= 50 else -120
    trade_quality_penalty = 20 if trades < 8 else 0
    return (
        win_gate_bonus
        + roi * 1.8
        + alpha * 0.8
        + sharpe * 3.0
        + win_rate * 0.16
        + min(trades, 18) * 0.28
        + min(profit_factor, 5) * 2.0
        - drawdown * drawdown_weight
        - trade_quality_penalty
    )


def researcher_log(config: StrategyConfig, generation: int, feedback: str, memory_count: int) -> str:
    guidance = "human guidance absorbed" if feedback else "autonomous hypothesis"
    return (
        f"[Q-Researcher:g{generation}] {guidance}; recalled {memory_count} Hindsight nodes. "
        f"Testing {config.name} with SMA {config.short_window}/{config.long_window}, "
        f"risk {config.risk_multiplier:.2f}, stop {config.stop_loss:.1%}."
    )


def trader_critique(metrics: dict[str, Any], generation: int) -> str:
    roi = metrics["roi"]
    drawdown = metrics["drawdown"]
    sharpe = metrics["sharpe"]
    if drawdown > 8:
        verdict = "Drawdown is still too high; reduce sizing and require a higher-timeframe SMA filter."
    elif roi < 6:
        verdict = "Return profile is improving but needs cleaner trend confirmation."
    else:
        verdict = "Strong candidate: positive ROI, controlled drawdown, and acceptable Sharpe."
    return (
        f"[Q-Trader:g{generation}] ROI {roi:+.2f}%, drawdown {drawdown:.2f}%, Sharpe {sharpe:.2f}. "
        f"{verdict}"
    )


def run_optimization(asset: str = "mTSLA", feedback: str = "", generations: int = 3) -> dict[str, Any]:
    asset = normalize_symbol(asset)
    memories = load_memory()
    router = CascadeRouter()
    market = fetch_ohlc(asset, period="1d", interval="1m")
    long_history = fetch_ohlc(asset, period="5y", interval="1d")
    fundamentals = fetch_fundamentals(asset)
    logs: list[dict[str, str]] = []
    generation_results: list[dict[str, Any]] = []
    memory_nodes = memories[:]
    search_count = max(48, generations if generations > 7 else 48)
    best_result: dict[str, Any] | None = None
    best_qualified: dict[str, Any] | None = None
    best_score = float("-inf")

    if feedback.strip():
        memory_nodes.append(append_memory("user-guidance", feedback.strip(), max(1, len(memories) + 1), asset=asset))
        memories = load_memory()

    recalled_memories = retrieve_hindsight(asset, feedback, memories)
    candidates = strategy_candidates(feedback, recalled_memories, search_count)
    frames = [
        ("1d", "1m"),
        ("5d", "5m"),
        ("1mo", "15m"),
        ("6mo", "1d"),
        ("1y", "1d"),
        ("5y", "1d"),
    ]
    frame_data = {(period, interval): fetch_ohlc(asset, period=period, interval=interval) for period, interval in frames}

    logs.append(
        {
            "agent": "system",
            "text": (
                f"[Hindsight] Recalled {len(recalled_memories)} relevant nodes for {asset}; "
                "asset-specific failures, best strategies, and trader critiques are now linked into this run."
            ),
        }
    )
    logs.append(
        {
            "agent": "system",
            "text": f"[Optimizer] Searching {len(candidates)} strategies across {len(frames)} timeframes. Weak intraday-only results will be rejected.",
        }
    )

    generation = 0
    for period, interval in frames:
        candles = frame_data[(period, interval)]["candles"]
        for config in candidates:
            generation += 1
            backtest = run_backtest(config, asset, candles)
            timeframe_label = f"{period}/{interval}"
            backtest["timeframe"] = {"period": period, "interval": interval, "label": timeframe_label}
            scored = {
                "generation": generation,
                "score": round(score_metrics(backtest["metrics"], feedback, recalled_memories), 3),
                **backtest,
            }
            generation_results.append(scored)
            qualified = (
                float(backtest["metrics"]["winRate"]) >= 50
                and float(backtest["metrics"]["trades"]) >= 8
                and float(backtest["metrics"]["roi"]) >= 0.08
                and float(backtest["metrics"].get("profitFactor", 0)) >= 1.05
            )
            if qualified and (
                best_qualified is None or scored["score"] > float(best_qualified["score"])
            ):
                best_qualified = scored

            if scored["score"] > best_score:
                best_score = scored["score"]
                best_result = scored
                if len(logs) < 16 or qualified:
                    logs.append(
                        {
                            "agent": "system",
                            "text": (
                                f"[Optimizer] New best {timeframe_label} g{generation}: {config.family}, "
                                f"ROI {backtest['metrics']['roi']:+.2f}%, win {backtest['metrics']['winRate']:.2f}%, "
                                f"PF {backtest['metrics']['profitFactor']:.2f}, drawdown {backtest['metrics']['drawdown']:.2f}%."
                            ),
                        }
                    )

    assert best_result is not None
    if best_qualified is not None:
        best_result = best_qualified
    else:
        logs.append(
            {
                "agent": "system",
                "text": (
                    "[Optimizer] Warning: no candidate crossed the hard 50% win-rate gate in this search. "
                    "Returning the closest candidate and recording the failure in Hindsight."
                ),
            }
        )
        append_memory(
            "win-rate-gate-failure",
            "No candidate crossed 50% win rate. Increase scalper search range or change asset/timeframe.",
            len(candidates),
            asset=asset,
        )
    best_config = StrategyConfig(**best_result["strategy"])
    code = strategy_to_code(best_config)
    researcher_text = router.chat(
        "q-researcher-final",
        "You are Q-Researcher, a senior quant researcher. Return one concise terminal log line explaining why this selected strategy is best.",
        (
            f"Asset: {asset}. Selected config: {best_config}. Selected metrics: {best_result['metrics']}. "
            f"Selected timeframe: {best_result.get('timeframe')}. Intraday indicators: {market.get('indicators')}. "
            f"Long-history indicators: {long_history.get('indicators')}. Fundamentals: {fundamentals}. Feedback: {feedback}."
            f" Recalled Hindsight: {[memory.get('text', '')[:180] for memory in recalled_memories[:5]]}."
        ),
        researcher_log(best_config, int(best_result["generation"]), feedback, len(recalled_memories)),
    )
    critique = router.chat(
        "q-trader-final-audit",
        "You are Q-Trader, a strict professional backtest auditor. Return one concise terminal log line with ROI, win rate, profit factor, drawdown, and residual risk.",
        f"Asset: {asset}. Selected metrics: {best_result['metrics']}. Selected strategy: {best_config}. Timeframe: {best_result.get('timeframe')}.",
        trader_critique(best_result["metrics"], int(best_result["generation"])),
    )
    logs.append({"agent": "researcher", "text": researcher_text})
    logs.append({"agent": "trader", "text": critique})
    memory_nodes.append(
        append_memory(
            "trader-critique",
            critique,
            int(best_result["generation"]),
            asset=asset,
            strategy=best_result["strategy"],
            metrics=best_result["metrics"],
            timeframe=best_result.get("timeframe") or {},
        )
    )
    append_memory(
        "best-strategy",
        (
            f"Selected {best_config.name}: ROI {best_result['metrics']['roi']:+.2f}%, "
            f"win {best_result['metrics']['winRate']:.2f}%, PF {best_result['metrics']['profitFactor']:.2f}, "
            f"drawdown {best_result['metrics']['drawdown']:.2f}% on {best_result.get('timeframe', {}).get('label', 'unknown')}."
        ),
        int(best_result["generation"]),
        asset=asset,
        strategy=best_result["strategy"],
        metrics=best_result["metrics"],
        timeframe=best_result.get("timeframe") or {},
    )
    logs.append(
        {
            "agent": "system",
            "text": (
                f"[Optimizer] Search complete after {len(candidates)} variants. Returning best strategy "
                f"g{best_result['generation']} on {best_result.get('timeframe', {}).get('label', 'unknown')} with "
                f"ROI {best_result['metrics']['roi']:+.2f}% and win rate {best_result['metrics']['winRate']:.2f}%."
            ),
        }
    )

    cascade_metrics = router.metrics()
    mode = "live-groq" if cascade_metrics["activeRouter"] == "Groq live route" else "deterministic-demo"
    if "API error" in cascade_metrics["activeRouter"]:
        mode = "groq-error-fallback"
    final_recall = retrieve_hindsight(asset, feedback, load_memory())

    return {
        "asset": asset,
        "provider": "groq",
        "mode": mode,
        "marketData": market,
        "longHistory": {"source": long_history.get("source"), "indicators": long_history.get("indicators")},
        "fundamentals": fundamentals,
        "optimizationFrames": frames,
        "logs": logs,
        "code": code,
        "generations": generation_results,
        "latest": best_result,
        "memoryNodes": final_recall,
        "hindsightTelemetry": {
            "mode": "local-vector-recall",
            "asset": asset,
            "recalled": len(final_recall),
            "stored": len(load_memory()),
            "query": feedback or f"{asset} autonomous optimization",
        },
        "cascadeMetrics": cascade_metrics,
    }
