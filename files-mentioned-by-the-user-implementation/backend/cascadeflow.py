from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import requests

from env_loader import load_env_file


GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
load_env_file()
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


@dataclass
class RouteEvent:
    stage: str
    model: str
    provider: str
    reason: str
    estimated_cost: float
    premium_cost: float


class CascadeRouter:
    """Small local cascadeflow layer: cheap Groq path first, deterministic fallback for demos."""

    def __init__(self) -> None:
        self.events: list[RouteEvent] = []
        self.live_enabled = bool(os.getenv("GROQ_API_KEY"))

    def route(self, stage: str, reason: str, premium_cost: float = 0.06) -> RouteEvent:
        event = RouteEvent(
            stage=stage,
            model=DEFAULT_GROQ_MODEL,
            provider="groq" if self.live_enabled else "groq-demo",
            reason=reason,
            estimated_cost=0.002 if self.live_enabled else 0.0,
            premium_cost=premium_cost,
        )
        self.events.append(event)
        return event

    def chat(self, stage: str, system: str, user: str, fallback: str) -> str:
        event = self.route(stage, "route cheap research/audit prompt to Groq free-tier lane")
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return fallback

        payload = {
            "model": DEFAULT_GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.35,
            "max_tokens": 320,
        }
        try:
            response = requests.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "BlackBoxAIQuantLab/1.0",
                },
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            event.provider = "groq-error-fallback"
            event.reason = f"Groq call failed; using deterministic fallback ({type(exc).__name__})"
            event.estimated_cost = 0.0
            return fallback

    def metrics(self) -> dict[str, Any]:
        estimated = sum(event.estimated_cost for event in self.events)
        premium = sum(event.premium_cost for event in self.events)
        savings = (1 - estimated / premium) * 100 if premium else 0
        if any(event.provider == "groq" for event in self.events):
            active_router = "Groq live route"
        elif self.live_enabled:
            active_router = "Groq configured but falling back after API error"
        else:
            active_router = "Groq deterministic demo route"
        return {
            "groqCalls": len(self.events),
            "premiumCallsAvoided": len(self.events),
            "estimatedCost": round(estimated, 4),
            "flatPremiumCost": round(premium, 4),
            "savingsPct": round(savings, 1),
            "activeRouter": active_router,
            "budgetCap": 1.0,
            "events": [event.__dict__ for event in self.events],
        }
