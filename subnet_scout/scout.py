"""Subnet Scout CLI.

Usage:
  python3 -m subnet_scout.scout                  # default: ranked report (live)
  python3 -m subnet_scout.scout leads            # practical VPS/CPU shortlist
  python3 -m subnet_scout.scout --offline        # use bundled fixtures
  python3 -m subnet_scout.scout inspect 46       # one-subnet deep view
  python3 -m subnet_scout.scout snapshot         # pull + save dated JSON
  python3 -m subnet_scout.scout export --format csv --out out.csv
  python3 -m subnet_scout.scout export --format md --out out.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import identity, report, scoring, taostats


def _fetch(client: taostats.TaostatsClient) -> list[dict]:
    subnets = client.subnets(limit=256)
    try:
        idents = client.subnet_identities()
    except taostats.TaostatsError:
        idents = []
    try:
        pools = client.dtao_pools(limit=256)
    except taostats.TaostatsError:
        pools = []
    merged = identity.merge(subnets, idents, pools)
    if not client.offline:
        taostats.save_live_cache({"subnets": subnets, "identities": idents, "pools": pools})
    return merged


def _fetch_with_cache(client: taostats.TaostatsClient) -> tuple[list[dict], str | None]:
    try:
        return _fetch(client), None
    except taostats.TaostatsError as e:
        cached = taostats.load_live_cache()
        if cached:
            merged = identity.merge(cached.get("subnets", []), cached.get("identities", []), cached.get("pools", []))
            age = cached.get("created_at", "unknown time")
            return merged, f"live fetch failed ({e}); using cached data from {age}"
        raise


def cmd_report(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged, warning = _fetch_with_cache(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    scored = scoring.score_all(merged)
    if args.filter_cpu:
        scored = [s for s in scored if "CPU_possible" in s["tags"]]
    if args.no_dead:
        scored = [s for s in scored if "ghost_subnet" not in s["tags"] and "placeholder" not in s["tags"]]
    report.print_table(scored, top=args.top)
    return 0


def _lead_reason(s: dict) -> str:
    bits: list[str] = []
    reg = s.get("registration_cost_tao")
    miners = s.get("active_miners")
    vals = s.get("active_validators")
    flow = s.get("flow_1d_tao")
    if reg is not None and reg <= 0.01:
        bits.append("cheap reg")
    if miners is not None and miners <= 25:
        bits.append("low miners")
    if vals is not None and vals >= 8:
        bits.append("validator coverage")
    if flow is not None and flow > 0:
        bits.append("positive 1d flow")
    if "CPU_possible" in s.get("tags", []):
        bits.append("CPU/VPS plausible")
    if not bits:
        bits.append("needs manual review")
    return ", ".join(bits[:4])


def _lead_next_action(s: dict) -> str:
    tags = set(s.get("tags", []))
    if "no_docs" in tags:
        return "find repo/docs first"
    if s.get("github"):
        return "read repo + run setup smoke test"
    if s.get("website"):
        return "open docs/site and verify miner path"
    return "inspect manually before registering"


def cmd_leads(args) -> int:
    """Opinionated shortlist for Jeffrey-style VPS subnet hunting."""
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged, warning = _fetch_with_cache(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    scored = scoring.score_all(merged)
    leads = []
    for s in scored:
        tags = set(s.get("tags", []))
        if tags & {"placeholder", "high_risk", "gpu_required", "no_validators"}:
            continue
        if args.cpu and "CPU_possible" not in tags:
            continue
        if args.max_reg is not None and (s.get("registration_cost_tao") is None or s["registration_cost_tao"] > args.max_reg):
            continue
        if args.no_crowded and "crowded" in tags:
            continue
        if s.get("risk", 0) >= args.max_risk:
            continue
        s = {**s, "reason": _lead_reason(s), "next_action": _lead_next_action(s)}
        leads.append(s)

    print(report.render_leads(leads, top=args.top))
    return 0


def cmd_inspect(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged, warning = _fetch_with_cache(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    target = next((s for s in merged if s["netuid"] == args.netuid), None)
    if not target:
        print(f"no subnet with netuid {args.netuid} in current data", file=sys.stderr)
        return 1
    scored = scoring.score_subnet(target)
    print(report.render_inspect(scored))
    return 0


def cmd_snapshot(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        subnets = client.subnets(limit=256)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        idents = client.subnet_identities()
    except taostats.TaostatsError as e:
        idents = []
        print(f"warning: identity fetch failed; saving subnet snapshot only ({e})", file=sys.stderr)
    try:
        pools = client.dtao_pools(limit=256)
    except taostats.TaostatsError as e:
        pools = []
        print(f"warning: dTAO pool fetch failed; saving without pool data ({e})", file=sys.stderr)
    payload = {"subnets": subnets, "identities": idents, "pools": pools}
    path = taostats.save_snapshot(payload)
    taostats.save_live_cache(payload)
    print(f"saved {path}")
    return 0


def cmd_export(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged, warning = _fetch_with_cache(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    scored = scoring.score_all(merged)
    out = Path(args.out)
    if args.format == "csv":
        report.export_csv(scored, out)
    elif args.format == "md":
        report.export_markdown(scored, out, top=args.top)
    else:
        print(f"unknown format: {args.format}", file=sys.stderr)
        return 2
    print(f"wrote {out} ({len(scored)} rows)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="subnet_scout", description="Bittensor subnet discovery for small VPS miners.")
    p.add_argument("--offline", action="store_true", help="use bundled fixtures instead of the Taostats API")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("report", help="ranked CLI table (default)")
    r.add_argument("--top", type=int, default=25)
    r.add_argument("--filter-cpu", action="store_true", help="only subnets tagged CPU_possible")
    r.add_argument("--no-dead", action="store_true", help="hide placeholder/ghost subnets")
    r.set_defaults(func=cmd_report)

    l = sub.add_parser("leads", help="practical VPS/CPU shortlist with reason + next action")
    l.add_argument("--top", type=int, default=15)
    l.add_argument("--cpu", action="store_true", default=True, help="only CPU/VPS-plausible subnets (default)")
    l.add_argument("--all-hardware", dest="cpu", action="store_false", help="include non-CPU-tagged subnets")
    l.add_argument("--max-reg", type=float, default=1.0, help="maximum registration cost in TAO")
    l.add_argument("--max-risk", type=float, default=50.0)
    l.add_argument("--no-crowded", action="store_true", default=True, help="hide crowded subnets (default)")
    l.add_argument("--include-crowded", dest="no_crowded", action="store_false")
    l.set_defaults(func=cmd_leads)

    i = sub.add_parser("inspect", help="single-subnet research view")
    i.add_argument("netuid", type=int)
    i.set_defaults(func=cmd_inspect)

    s = sub.add_parser("snapshot", help="pull and save dated JSON snapshot")
    s.set_defaults(func=cmd_snapshot)

    e = sub.add_parser("export", help="export ranked report to CSV or Markdown")
    e.add_argument("--format", choices=("csv", "md"), required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--top", type=int, default=50)
    e.set_defaults(func=cmd_export)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # default = report with default args
        ns = parser.parse_args(["report"] + (["--offline"] if args.offline else []))
        return ns.func(ns)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
