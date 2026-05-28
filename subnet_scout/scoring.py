"""Opportunity scoring tuned for a small VPS miner.

The score answers: "would it be cheap and feasible for me to enter, and is
there enough real activity that the alpha actually has a market?"

It is intentionally split into two outputs:
  - opportunity: positive signal (cheap entry, room to enter, real activity)
  - risk:       negative signal (placeholder, no docs, no validators, GPU-only)

This separates "cheap but suspicious" (low opp, high risk) from "actually
promising" (high opp, low risk).
"""
from __future__ import annotations

from .identity import derive_tags

# weights chosen so each component contributes 0-25 to a 0-100 opportunity score.
# tune by editing here, not by sprinkling magic numbers downstream.
W_CHEAP_REG = 25
W_ROOM_TO_ENTER = 20
W_VALIDATOR_ACTIVITY = 20
W_LIQUIDITY = 15
W_MOMENTUM = 10
W_CPU_BONUS = 10

# risk component weights
R_PLACEHOLDER = 35
R_NO_DOCS = 20
R_GHOST = 25
R_NO_VALIDATORS = 25
R_GPU_REQUIRED = 15


def _cheap_reg_score(reg_tao: float | None) -> float:
    if reg_tao is None:
        return 0.0
    if reg_tao <= 0.1:
        return 1.0
    if reg_tao <= 1.0:
        return 0.8
    if reg_tao <= 5.0:
        return 0.5
    if reg_tao <= 20.0:
        return 0.2
    return 0.0


def _room_score(miners: int | None, max_n: int | None) -> float:
    if not miners or not max_n:
        return 0.5
    fill = miners / max_n
    if fill >= 0.95:
        return 0.0
    if fill >= 0.8:
        return 0.3
    if fill >= 0.5:
        return 0.7
    if fill >= 0.1:
        return 1.0
    return 0.4  # very empty - either early or dead, opportunity is mixed


def _validator_score(validators: int | None) -> float:
    v = validators or 0
    if v == 0:
        return 0.0
    if v >= 16:
        return 1.0
    if v >= 8:
        return 0.7
    if v >= 3:
        return 0.4
    return 0.2


def _liquidity_score(volume: float | None, tao_in_pool: float | None) -> float:
    vol = volume or 0.0
    pool = tao_in_pool or 0.0
    # log-ish bucketing - we care about "is there a market" not exact size
    if pool >= 1000 or vol >= 500:
        return 1.0
    if pool >= 100 or vol >= 50:
        return 0.6
    if pool >= 10 or vol >= 5:
        return 0.3
    return 0.0


def _momentum_score(change_24h: float | None) -> float:
    if change_24h is None:
        return 0.5
    if change_24h >= 25:
        return 1.0
    if change_24h >= 5:
        return 0.7
    if change_24h >= -5:
        return 0.5
    if change_24h >= -25:
        return 0.3
    return 0.0


def score_subnet(s: dict) -> dict:
    tags = derive_tags(s)

    opp = (
        _cheap_reg_score(s.get("registration_cost_tao")) * W_CHEAP_REG
        + _room_score(s.get("active_miners"), s.get("max_neurons")) * W_ROOM_TO_ENTER
        + _validator_score(s.get("active_validators")) * W_VALIDATOR_ACTIVITY
        + _liquidity_score(s.get("volume_24h"), s.get("tao_in_pool")) * W_LIQUIDITY
        + _momentum_score(s.get("price_change_24h")) * W_MOMENTUM
    )
    if "CPU_possible" in tags:
        opp += W_CPU_BONUS

    risk = 0.0
    if "placeholder" in tags:
        risk += R_PLACEHOLDER
    if "no_docs" in tags:
        risk += R_NO_DOCS
    if "ghost_subnet" in tags:
        risk += R_GHOST
    if "no_validators" in tags:
        risk += R_NO_VALIDATORS
    if "gpu_required" in tags:
        risk += R_GPU_REQUIRED

    opp = max(0.0, min(100.0, opp))
    risk = max(0.0, min(100.0, risk))
    net = round(opp - risk * 0.6, 1)

    return {
        **s,
        "tags": tags,
        "opportunity": round(opp, 1),
        "risk": round(risk, 1),
        "score": net,
        "verdict": _verdict(opp, risk),
    }


def _verdict(opp: float, risk: float) -> str:
    if risk >= 60:
        return "skip"
    if opp >= 70 and risk < 30:
        return "research-worthy"
    if opp >= 50:
        return "medium-high"
    if opp >= 30:
        return "medium"
    if risk >= 30 and opp < 30:
        return "cheap but suspicious"
    return "low"


def score_all(subnets: list[dict]) -> list[dict]:
    scored = [score_subnet(s) for s in subnets]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored
