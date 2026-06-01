"""Rendering: CLI table, inspect view, CSV/Markdown export."""
from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Iterable

COLS = [
    ("netuid", "SN", 4),
    ("name", "Name", 18),
    ("registration_cost_tao", "Reg", 7),
    ("active_miners", "Miners", 7),
    ("active_validators", "Vals", 5),
    ("flow_1d_tao", "Flow1d", 8),
    ("opportunity", "Opp", 6),
    ("risk", "Risk", 6),
    ("score", "Score", 7),
    ("verdict", "Verdict", 22),
]


def _fmt(v, width: int, key: str | None = None) -> str:
    if v is None:
        s = "-"
    elif isinstance(v, float):
        if key == "registration_cost_tao":
            s = _num(v)
        elif key and key.startswith("flow_"):
            s = f"{v:.2f}"
        else:
            s = f"{v:.2f}"
    else:
        s = str(v)
    if len(s) > width:
        s = s[: max(1, width - 1)] + "~"
    return s.ljust(width)


def render_table(scored: Iterable[dict], *, top: int | None = 25) -> str:
    rows = list(scored)
    if top is not None:
        rows = rows[:top]
    header = "  ".join(label.ljust(w) for _, label, w in COLS)
    sep = "  ".join("-" * w for _, _, w in COLS)
    lines = [header, sep]
    for r in rows:
        lines.append("  ".join(_fmt(r.get(k), w, k) for k, _, w in COLS))
    return "\n".join(lines)


def render_inspect(s: dict) -> str:
    tags = ", ".join(s.get("tags", [])) or "-"
    lines = [
        f"SN{s['netuid']}  {s.get('name') or '(unnamed)'}"
        + (f"  [{s['symbol']}]" if s.get("symbol") else ""),
        "-" * 60,
        f"Verdict        : {s.get('verdict', '-')}",
        f"Score          : {s.get('score', '-')}  (opp {s.get('opportunity', '-')} / risk {s.get('risk', '-')})",
        f"Tags           : {tags}",
        "",
        f"Reg cost (TAO) : {_num(s.get('registration_cost_tao'))}",
        f"Active miners  : {_num(s.get('active_miners'))} / {_num(s.get('max_neurons')) or '?'}",
        f"Validators     : {_num(s.get('active_validators'))}",
        f"Price (TAO)    : {_num(s.get('price_tao'))}",
        f"24h change %   : {_num(s.get('price_change_24h'))}",
        f"1d flow (TAO)  : {_num(s.get('flow_1d_tao'))}",
        f"7d flow (TAO)  : {_num(s.get('flow_7d_tao'))}",
        f"24h volume     : {_num(s.get('volume_24h'))}",
        f"TAO in pool    : {_num(s.get('tao_in_pool'))}",
        "",
        f"Website        : {s.get('website') or '-'}",
        f"GitHub         : {s.get('github') or '-'}",
        f"Contact        : {s.get('contact') or '-'}",
        "",
        "Summary:",
        _wrap(s.get("summary") or "(no description published on chain)"),
    ]
    return "\n".join(lines)


def _num(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") or "0"
    return str(v)


def _wrap(text: str, width: int = 72) -> str:
    words = text.split()
    if not words:
        return ""
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join("  " + l for l in lines)


EXPORT_FIELDS = [
    "netuid", "name", "symbol", "verdict", "score", "opportunity", "risk",
    "registration_cost_tao", "active_miners", "active_validators",
    "price_tao", "price_change_24h", "flow_1d_tao", "flow_7d_tao", "volume_24h",
    "website", "github", "tags", "summary",
]


def export_csv(scored: list[dict], path: Path) -> Path:
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=EXPORT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for s in scored:
            row = {k: s.get(k) for k in EXPORT_FIELDS}
            row["tags"] = ";".join(s.get("tags", []))
            w.writerow(row)
    return path


def export_markdown(scored: list[dict], path: Path, *, top: int | None = 50) -> Path:
    path = Path(path)
    rows = scored[:top] if top else scored
    md = ["# Subnet Scout report", "", "| SN | Name | Reg | Miners | Vals | Flow1d | Opp | Risk | Score | Verdict | Tags |",
          "|---:|------|----:|------:|-----:|------:|----:|----:|------:|---------|------|"]
    for s in rows:
        md.append(
            "| {netuid} | {name} | {reg} | {miners} | {vals} | {ch} | {opp} | {risk} | {score} | {verdict} | {tags} |".format(
                netuid=s.get("netuid"),
                name=(s.get("name") or "").replace("|", "/")[:24],
                reg=_num(s.get("registration_cost_tao")),
                miners=_num(s.get("active_miners")),
                vals=_num(s.get("active_validators")),
                ch=_num(s.get("flow_1d_tao")),
                opp=s.get("opportunity"),
                risk=s.get("risk"),
                score=s.get("score"),
                verdict=s.get("verdict"),
                tags=" ".join(s.get("tags", [])),
            )
        )
    path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return path


def print_table(scored, *, top=25, stream=sys.stdout) -> None:
    print(render_table(scored, top=top), file=stream)
