# Subnet Scout

Bittensor subnet discovery for small VPS miners. Pulls live subnet data from
Taostats, scores each subnet on **opportunity** (cheap entry, room to enter,
real activity) vs **risk** (placeholder, no docs, no validators, GPU-only),
and prints a ranked CLI report.

## What it answers

> Where should a small miner look next?

Separates *cheap but suspicious* (low opp, high risk) from *actually
promising* (high opp, low risk).

## Install

Requires Python 3.10+. No third-party dependencies — stdlib only.

```bash
git clone <this-repo> subnet_scout
cd subnet_scout
cp .env.example .env
# put your Taostats key in .env
```

## Usage

```bash
# default: ranked report (live)
python3 -m subnet_scout.scout

# practical VPS/CPU shortlist with reason + next action
python3 -m subnet_scout.scout leads
python3 -m subnet_scout.scout leads --json

# one-subnet practical due-diligence checklist
python3 -m subnet_scout.scout deep 124
python3 -m subnet_scout.scout deep 124 --json

# only CPU-friendly subnets, no dead ones
python3 -m subnet_scout.scout report --filter-cpu --no-dead --top 30

# deep view of one subnet
python3 -m subnet_scout.scout inspect 21

# pull + save dated JSON snapshot to data/subnet_scout/
python3 -m subnet_scout.scout snapshot

# export ranked report
python3 -m subnet_scout.scout export --format csv --out scout.csv
python3 -m subnet_scout.scout export --format md  --out scout.md

# no API key? run against bundled fixtures
python3 -m subnet_scout.scout --offline
```

## Deploy on a VPS

```bash
# one-off
ssh user@vps
git clone <repo> ~/subnet_scout
cd ~/subnet_scout
export TAOSTATS_API_KEY=...
python3 -m subnet_scout.scout report --top 50

# daily snapshot via cron (writes JSON to data/subnet_scout/)
crontab -e
# add:
0 6 * * * cd /home/USER/subnet_scout && TAOSTATS_API_KEY=... /usr/bin/python3 -m subnet_scout.scout snapshot >> snapshot.log 2>&1
```

## Layout

```
subnet_scout/
  scout.py         # CLI entry, subcommands
  taostats.py      # API client + offline fixtures
  identity.py      # enrichment + tag derivation
  scoring.py       # opportunity / risk / verdict
  report.py        # CLI table, inspect, CSV/MD export
data/subnet_scout/
  fixtures/        # offline fallback data
  subnets_*.json   # daily snapshots
```

## Tags

| tag | meaning |
|---|---|
| `CPU_possible` | identity/docs mention CPU-only, VPS-friendly, no GPU, etc. |
| `gpu_required` | unnegated GPU mention — assume GPU needed |
| `docs_found` | has website or GitHub repo on chain |
| `no_docs` | no website, GitHub, or summary |
| `placeholder` | empty or placeholder name |
| `ghost_subnet` | ≤1 active miner |
| `crowded` | ≥90% of max neurons registered |
| `early` | netuid ≥ 90 |
| `no_validators` | zero active validators |
| `high_risk` | placeholder OR (no_docs AND ghost_subnet) |
