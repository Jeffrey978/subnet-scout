"""Subnet identity enrichment + tag derivation.

Merges raw subnet rows from Taostats with the chain's SubnetIdentity records
(name/symbol/url/github_repo/description/subnet_contact) into a single
normalized dict per netuid.
"""
from __future__ import annotations

import re
from typing import Any

# heuristic keywords for tag derivation. Conservative — better to under-tag
# than to mislead a miner about hardware needs.
NO_GPU_RE = re.compile(r"\b(no\s*gpu|cpu[- ]?only|without\s*gpu|vps[- ]?friendly)\b", re.I)
CPU_HINT_RE = re.compile(
    r"\b(vps|browserless|scraping|api[- ]?call|ad[- ]?optim|"
    r"text\s*classif|prompt|ranking|leaderboard|crawl|index|fetch)\b",
    re.I,
)
GPU_HINT_RE = re.compile(
    r"\b(gpu|cuda|h100|a100|3090|4090|llm\s*training|fine[- ]?tune|"
    r"diffusion|inference\s*servers?|tensor[- ]?core)\b",
    re.I,
)
PLACEHOLDER_NAMES = {"", "subnet", "test", "tbd", "placeholder", "none", "n/a"}


def _pick(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return default


def normalize_subnet(row: dict, identity: dict | None = None, pool: dict | None = None) -> dict:
    netuid = _pick(row, "netuid", "net_uid", "id")
    ident = identity or {}
    pool = pool or {}
    name = _pick(ident, "subnet_name", "name") or _pick(row, "name", "subnet_name") or _pick(pool, "name") or ""
    symbol = _pick(ident, "symbol", "ticker") or _pick(row, "symbol") or _pick(pool, "symbol") or ""
    website = _pick(ident, "url", "website", "subnet_url") or ""
    github = _pick(ident, "github_repo", "github", "github_url") or ""
    summary = _pick(ident, "description", "summary", "subnet_contact") or ""
    contact = _pick(ident, "subnet_contact", "discord", "contact") or ""

    # Taostats pool volumes come in rao (1e-9 TAO).
    tao_vol_24h = _to_tao(_pick(pool, "tao_volume_24_hr"))
    tao_in_pool = _to_tao(_pick(pool, "total_tao", "tao_in", "tao_in_pool"))

    return {
        "netuid": netuid,
        "name": str(name).strip(),
        "symbol": str(symbol).strip(),
        "website": str(website).strip(),
        "github": str(github).strip(),
        "summary": str(summary).strip(),
        "contact": str(contact).strip(),
        "registration_cost_tao": _to_tao(_pick(row, "neuron_registration_cost", "registration_cost", "burn")),
        "emission": _to_float(_pick(row, "emission", "emission_pct", "alpha_emission")),
        "active_miners": _to_int(_pick(row, "active_miners", "active_keys", "neurons", "subnet_size")),
        "active_validators": _to_int(_pick(row, "active_validators", "validators")),
        "max_neurons": _to_int(_pick(row, "max_neurons", "max_n")),
        "price_tao": _to_float(_pick(pool, "price", "last_price") or _pick(row, "price", "alpha_price", "price_in_tao")),
        "price_change_24h": _to_float(_pick(pool, "price_change_1_day", "price_change_24h")),
        "price_change_7d": _to_float(_pick(pool, "price_change_1_week")),
        "volume_24h": tao_vol_24h,
        "tao_in_pool": tao_in_pool,
        "buyers_24h": _to_int(_pick(pool, "buyers_24_hr")),
        "market_cap_tao": _to_tao(_pick(pool, "market_cap")),
        "tao_flow_1d": _to_tao(_pick(row, "net_flow_1_day", "tao_flow")),
        "fng": _to_int(_pick(pool, "fear_and_greed_index")),
        "raw": row,
    }


def merge(subnets: list[dict], identities: list[dict] | None, pools: list[dict] | None = None) -> list[dict]:
    ident_by_uid: dict[int, dict] = {}
    for i in identities or []:
        uid = _pick(i, "netuid", "net_uid", "id")
        if uid is not None:
            ident_by_uid[int(uid)] = i
    pool_by_uid: dict[int, dict] = {}
    for p in pools or []:
        uid = _pick(p, "netuid", "net_uid", "id")
        if uid is not None:
            pool_by_uid[int(uid)] = p
    out: list[dict] = []
    for row in subnets:
        netuid = _pick(row, "netuid", "net_uid", "id")
        if netuid is None:
            continue
        out.append(normalize_subnet(
            row,
            ident_by_uid.get(int(netuid)),
            pool_by_uid.get(int(netuid)),
        ))
    out.sort(key=lambda s: s["netuid"] if s["netuid"] is not None else 9999)
    return out


def derive_tags(s: dict) -> list[str]:
    tags: list[str] = []
    name = s["name"].lower()
    summary = s["summary"]
    text = f"{name} {summary}".strip()

    if s["netuid"] is not None and s["netuid"] >= 90:
        tags.append("early")

    miners = s["active_miners"] or 0
    max_n = s["max_neurons"] or 256
    if miners <= 1:
        tags.append("ghost_subnet")
    elif miners >= max_n * 0.9:
        tags.append("crowded")

    if not name or name in PLACEHOLDER_NAMES:
        tags.append("placeholder")
    if not s["website"] and not s["github"] and not s["summary"]:
        tags.append("no_docs")
    elif s["github"] or s["website"]:
        tags.append("docs_found")

    if text:
        if NO_GPU_RE.search(text):
            tags.append("CPU_possible")
        elif GPU_HINT_RE.search(text):
            tags.append("gpu_required")
        elif CPU_HINT_RE.search(text):
            tags.append("CPU_possible")

    if "placeholder" in tags or ("no_docs" in tags and "ghost_subnet" in tags):
        tags.append("high_risk")

    if (s["active_validators"] or 0) == 0:
        tags.append("no_validators")

    return tags


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_tao(v: Any) -> float | None:
    """Reg cost often arrives in rao (1e-9 TAO). Heuristic: any value > 1e6 is rao."""
    f = _to_float(v)
    if f is None:
        return None
    return f / 1e9 if f > 1e6 else f

