"""Taostats API client with offline-fixture fallback."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.taostats.io"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "subnet_scout"
FIXTURE_DIR = DATA_DIR / "fixtures"


class TaostatsError(RuntimeError):
    pass


class TaostatsClient:
    def __init__(self, api_key: str | None = None, *, offline: bool = False, timeout: int = 20):
        self.api_key = api_key or os.environ.get("TAOSTATS_API_KEY")
        self.offline = offline
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        if self.offline:
            return self._load_fixture(path, params)
        if not self.api_key:
            raise TaostatsError(
                "TAOSTATS_API_KEY not set. Run with --offline to use bundled fixtures."
            )
        url = f"{API_BASE}{path}"
        if params:
            url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
        req = Request(url, headers={"Authorization": self.api_key, "accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            raise TaostatsError(f"HTTP {e.code} on {path}: {e.reason}") from e
        except URLError as e:
            raise TaostatsError(f"network error on {path}: {e.reason}") from e

    def _load_fixture(self, path: str, params: dict | None) -> dict:
        slug = path.strip("/").replace("/", "_") or "root"
        candidates = [FIXTURE_DIR / f"{slug}.json", FIXTURE_DIR / f"{slug}_default.json"]
        for c in candidates:
            if c.exists():
                return json.loads(c.read_text(encoding="utf-8"))
        raise TaostatsError(f"no offline fixture for {path} (looked in {FIXTURE_DIR})")

    # endpoints
    def subnets(self, limit: int = 100, page: int = 1) -> list[dict]:
        data = self._get("/api/subnet/latest/v1", {"limit": limit, "page": page})
        return data.get("data", data) if isinstance(data, dict) else data

    def subnet_identities(self) -> list[dict]:
        data = self._get("/api/subnet/identity/v1", {"limit": 256})
        return data.get("data", data) if isinstance(data, dict) else data

    def subnet_detail(self, netuid: int) -> dict:
        data = self._get(f"/api/subnet/latest/v1", {"netuid": netuid})
        rows = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(rows, list) and rows:
            return rows[0]
        if isinstance(rows, dict):
            return rows
        raise TaostatsError(f"no data for netuid {netuid}")


def save_snapshot(payload: dict, *, label: str = "subnets") -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = DATA_DIR / f"{label}_{ts}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def latest_snapshot(label: str = "subnets") -> Path | None:
    if not DATA_DIR.exists():
        return None
    matches = sorted(DATA_DIR.glob(f"{label}_*.json"))
    return matches[-1] if matches else None


def load_snapshot(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
