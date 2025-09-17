"""Builds a compact coverage manifest from bars_download_manifest.jsonl.

Emits bars_coverage_manifest.json with per-symbol, per-bar_size day coverage
and total date range, derived from the append-only manifest.

Usage:
    python -m src.tools.analysis.build_bars_coverage
    python -m src.tools.analysis.build_bars_coverage --from-manifest /path/to/bars_download_manifest.jsonl --out /path/to/bars_coverage_manifest.json

Outputs a JSON with schema_version bars_coverage.v1
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.tools._cli_helpers import emit_describe_early


def tool_describe() -> dict[str, Any]:
    return {
        "name": "build_bars_coverage",
        "description": "Compacts append-only bars download manifest into current coverage per symbol/bar_size/day.",
        "dependencies": [],
        "inputs": {
            "--from-manifest": {"type": "str", "required": False},
            "--out": {"type": "str", "required": False},
        },
        "outputs": {
            "stdout": {
                "type": "json",
                "description": "Write result including path and entry_count",
            },
            "bars_coverage_manifest.json": "Coverage summary JSON",
        },
        "examples": [
            {
                "description": "Build using defaults from config base path",
                "command": "python -m src.tools.analysis.build_bars_coverage",
            },
            {
                "description": "Build from explicit manifest to explicit output",
                "command": "python -m src.tools.analysis.build_bars_coverage --from-manifest ./data/bars_download_manifest.jsonl --out ./data/bars_coverage_manifest.json",
            },
        ],
    }


if emit_describe_early(tool_describe):  # pragma: no cover
    raise SystemExit(0)


@dataclass
class DayCoverage:
    date: str
    time_start: str | None
    time_end: str | None
    path: str
    filename: str
    rows: int


def _infer_date(record: dict[str, Any]) -> str | None:
    ts = record.get("time_start") or record.get("time_end")
    if isinstance(ts, str) and len(ts) >= 10:
        return ts[:10]
    # try to find YYYY-MM-DD in filename
    name = str(record.get("filename") or "")
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", name)
    if m:
        return m.group(1)
    p = str(record.get("path") or "")
    m2 = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", p)
    if m2:
        return m2.group(1)
    return None


def _load_append_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not manifest_path.exists():
        return items
    with manifest_path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("schema_version") and not str(
                rec.get("schema_version")
            ).startswith("bars_manifest."):
                continue
            items.append(rec)
    return items


def _select_best_per_day(
    items: list[dict[str, Any]],
) -> dict[tuple[str, str, str], DayCoverage]:
    best: dict[tuple[str, str, str], DayCoverage] = {}
    for rec in items:
        sym = str(rec.get("symbol") or "").upper()
        size = str(rec.get("bar_size") or "")
        date = _infer_date(rec)
        if not sym or not size or not date:
            continue
        rows = int(rec.get("rows") or 0)
        key = (sym, size, date)
        cur = best.get(key)
        dc = DayCoverage(
            date=date,
            time_start=rec.get("time_start"),
            time_end=rec.get("time_end"),
            path=str(rec.get("path") or ""),
            filename=str(rec.get("filename") or ""),
            rows=rows,
        )
        if cur is None or rows > cur.rows:
            best[key] = dc
        elif rows == (cur.rows if cur else 0):
            # tie-breaker by more complete time range if possible
            if (dc.time_start or "") < (cur.time_start or "") or (dc.time_end or "") > (
                cur.time_end or ""
            ):
                best[key] = dc
    return best


def _group_entries(
    best: dict[tuple[str, str, str], DayCoverage],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[DayCoverage]] = defaultdict(list)
    for (sym, size, _), cov in best.items():
        grouped[(sym, size)].append(cov)
    for covs in grouped.values():
        covs.sort(key=lambda c: c.date)
    entries: list[dict[str, Any]] = []
    for (sym, size), covs in sorted(grouped.items(), key=lambda x: (x[0][0], x[0][1])):
        if not covs:
            continue
        date_start = covs[0].date
        date_end = covs[-1].date
        days = [
            {
                "date": c.date,
                "time_start": c.time_start,
                "time_end": c.time_end,
                "path": c.path,
                "filename": c.filename,
                "rows": c.rows,
            }
            for c in covs
        ]
        entries.append(
            {
                "symbol": sym,
                "bar_size": size,
                "total": {"date_start": date_start, "date_end": date_end},
                "days": days,
            }
        )
    return entries


def build_coverage(manifest_path: Path, out_path: Path | None = None) -> dict[str, Any]:
    items = _load_append_manifest(manifest_path)
    best = _select_best_per_day(items)
    entries = _group_entries(best)
    result = {
        "schema_version": "bars_coverage.v1",
        "generated_at": datetime.now().isoformat(),
        "entries": entries,
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2))
    return result


def main() -> int:
    from src.core.config import get_config

    p = argparse.ArgumentParser()
    p.add_argument("--describe", action="store_true")
    p.add_argument("--from-manifest")
    p.add_argument("--out")
    args = p.parse_args()

    if args.describe:
        print(json.dumps(tool_describe(), indent=2))
        return 0

    cfg = get_config()
    base = cfg.data_paths.base_path
    manifest = (
        Path(args.from_manifest)
        if args.from_manifest
        else (base / "bars_download_manifest.jsonl")
    )
    out = Path(args.out) if args.out else (base / "bars_coverage_manifest.json")
    res = build_coverage(manifest, out)
    print(json.dumps({"wrote": str(out), "entry_count": len(res.get("entries", []))}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
