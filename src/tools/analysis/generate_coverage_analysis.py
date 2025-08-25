from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from src.tools._cli_helpers import env_dep, print_json

COVERAGE_XML = Path("coverage.xml")
COVERAGE_JSON = Path("coverage.json")
OUTPUT_JSON = Path("reports/coverage_analysis.json")


def _normalize_src_path(src_root: str, filename: str) -> str:
    if filename.startswith("src/"):
        return filename
    rel_path = (Path(src_root) / filename).resolve()
    try:
        idx = rel_path.parts.index("src")
        return "/".join(rel_path.parts[idx:])
    except ValueError:
        return filename


def _class_metrics(cls: ET.Element) -> tuple[int, int, int, int]:
    lines_elem = cls.find("lines")
    lines_total = lines_missed = branches_total = branches_missed = 0
    if lines_elem is not None:
        for line in lines_elem.findall("line"):
            hits = int(line.attrib.get("hits", "0"))
            lines_total += 1
            if hits == 0:
                lines_missed += 1
            cond_cov = line.attrib.get("condition-coverage")
            if cond_cov:
                try:
                    inside = cond_cov.split("(")[1].split(")")[0]
                    taken, total = inside.split("/")
                    taken_i = int(taken)
                    total_i = int(total)
                    branches_total += total_i
                    branches_missed += total_i - taken_i
                except Exception:
                    pass
    return lines_total, lines_missed, branches_total, branches_missed


def _from_xml() -> dict[str, Any]:
    tree = ET.parse(COVERAGE_XML)
    root = tree.getroot()
    packages: list[dict[str, Any]] = []
    total_lines = total_missed = total_branches = total_br_missed = 0
    source_roots = [
        s.text.rstrip("/") for s in root.findall(".//sources/source") if s.text
    ]
    src_root = source_roots[0] if source_roots else ""

    for cls in root.findall(".//packages/package/classes/class"):
        rel = _normalize_src_path(src_root, cls.attrib.get("filename", ""))
        if not rel.startswith("src/"):
            continue
        lines_total, lines_missed, branches_total, branches_missed = _class_metrics(cls)
        line_cov = (
            0.0
            if lines_total == 0
            else (lines_total - lines_missed) / lines_total * 100
        )
        branch_cov = (
            0.0
            if branches_total == 0
            else (branches_total - branches_missed) / branches_total * 100
        )
        packages.append(
            {
                "module": rel,
                "lines_total": lines_total,
                "lines_missed": lines_missed,
                "line_coverage_pct": round(line_cov, 1),
                "branches_total": branches_total,
                "branches_missed": branches_missed,
                "branch_coverage_pct": round(branch_cov, 1),
            }
        )
        total_lines += lines_total
        total_missed += lines_missed
        total_branches += branches_total
        total_br_missed += branches_missed

    return {
        "packages": packages,
        "totals": (total_lines, total_missed, total_branches, total_br_missed),
    }


def _from_json() -> dict[str, Any]:
    data = json.loads(COVERAGE_JSON.read_text())
    files: dict[str, Any] = data.get("files", {})
    packages: list[dict[str, Any]] = []
    total_lines = total_missed = total_branches = total_br_missed = 0

    for filename, filedata in files.items():
        # filename is absolute path; normalize to src/
        try:
            p = Path(filename).resolve()
            if "src" in p.parts:
                idx = p.parts.index("src")
                rel = "/".join(p.parts[idx:])
            else:
                rel = filename
        except Exception:
            rel = filename
        if not rel.startswith("src/"):
            continue
        summary = filedata.get("summary", {})
        # coverage.py json has: num_statements, missing_lines, excluded_lines,
        # num_branches, missing_branches, partial_branches
        lines_total = int(summary.get("num_statements", 0))
        lines_missed = int(summary.get("missing_lines", 0))
        branches_total = int(summary.get("num_branches", 0))
        branches_missed = int(summary.get("missing_branches", 0))

        line_cov = (
            0.0
            if lines_total == 0
            else (lines_total - lines_missed) / lines_total * 100
        )
        branch_cov = (
            0.0
            if branches_total == 0
            else (branches_total - branches_missed) / branches_total * 100
        )
        packages.append(
            {
                "module": rel,
                "lines_total": lines_total,
                "lines_missed": lines_missed,
                "line_coverage_pct": round(line_cov, 1),
                "branches_total": branches_total,
                "branches_missed": branches_missed,
                "branch_coverage_pct": round(branch_cov, 1),
            }
        )
        total_lines += lines_total
        total_missed += lines_missed
        total_branches += branches_total
        total_br_missed += branches_missed

    return {
        "packages": packages,
        "totals": (
            total_lines,
            total_missed,
            total_branches,
            total_br_missed,
        ),
    }


def _summarize(
    packages: list[dict[str, Any]], totals: tuple[int, int, int, int]
) -> dict[str, Any]:
    total_lines, total_missed, total_branches, total_br_missed = totals
    summary = {
        "summary": {
            "lines_total": total_lines,
            "lines_missed": total_missed,
            "line_coverage_pct": round(
                0.0
                if total_lines == 0
                else (total_lines - total_missed) / total_lines * 100,
                2,
            ),
            "branches_total": total_branches,
            "branches_missed": total_br_missed,
            "branch_coverage_pct": round(
                0.0
                if total_branches == 0
                else (total_branches - total_br_missed) / total_branches * 100,
                2,
            ),
        },
        "modules": packages,
    }
    # Compute the 5 lowest-covered modules by line coverage, then branch
    sorted_mods = sorted(
        packages,
        key=lambda m: (
            m.get("line_coverage_pct", 0),
            m.get("branch_coverage_pct", 0),
        ),
    )
    summary["lowest_modules"] = sorted_mods[:5]
    return summary


def parse() -> dict[str, Any]:
    if COVERAGE_JSON.exists():
        extracted = _from_json()
    elif COVERAGE_XML.exists():
        extracted = _from_xml()
    else:
        raise SystemExit(
            "No coverage report found. Run tests with coverage (json or xml)."
        )
    packages = extracted["packages"]
    totals = extracted["totals"]
    summary = _summarize(packages, totals)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(summary, indent=2))
    return summary


def describe() -> dict[str, Any]:
    return {
        "name": "generate_coverage_analysis",
        "description": "Parse coverage.xml or coverage.json and produce aggregated coverage summary JSON report.",
        "inputs": {
            "--describe": {
                "type": "flag",
                "description": "Print schema metadata and exit",
            }
        },
        "outputs": {
            "stdout": {
                "type": "json",
                "description": "When run normally, prints high-level summary stats; with --describe prints schema",
            },
            "reports/coverage_analysis.json": {
                "type": "file",
                "description": "Full structured coverage analysis written to disk",
            },
        },
        "dependencies": [env_dep("PYTHONPATH")],
        "examples": [
            {
                "description": "Show schema",
                "command": "python -m src.tools.analysis.generate_coverage_analysis --describe",
            },
            {
                "description": "Generate coverage analysis (after running tests with coverage)",
                "command": "python -m src.tools.analysis.generate_coverage_analysis",
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--describe" in args:  # early pure JSON path for schema test
        return print_json(describe())
    data = parse()
    print(json.dumps(data["summary"], indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
