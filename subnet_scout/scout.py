"""Subnet Scout CLI.

Usage:
  python3 -m subnet_scout.scout                  # default: ranked report (live)
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
    return identity.merge(subnets, idents)


def cmd_report(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged = _fetch(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    scored = scoring.score_all(merged)
    if args.filter_cpu:
        scored = [s for s in scored if "CPU_possible" in s["tags"]]
    if args.no_dead:
        scored = [s for s in scored if "ghost_subnet" not in s["tags"] and "placeholder" not in s["tags"]]
    report.print_table(scored, top=args.top)
    return 0


def cmd_inspect(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged = _fetch(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
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
        idents = client.subnet_identities()
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    path = taostats.save_snapshot({"subnets": subnets, "identities": idents})
    print(f"saved {path}")
    return 0


def cmd_export(args) -> int:
    client = taostats.TaostatsClient(offline=args.offline)
    try:
        merged = _fetch(client)
    except taostats.TaostatsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
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
