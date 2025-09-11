"""Guardrail test to prevent legacy imports from being reintroduced.

This test scans the project for imports of deprecated modules/classes and
fails if found. It is intentionally fast and simple.
"""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_IMPORT_PATTERNS = (
    # Any direct import of the legacy monolith
    ("import ", " MasterPy_Trading"),
    ("from MasterPy_Trading", " import "),
    ("from src.MasterPy_Trading", " import "),
    # Any import bringing the deprecated wrapper into scope
    ("import ", " MarketDepthCls"),
    ("from ", " import MarketDepthCls"),
)


def test_no_legacy_imports() -> None:
    root = Path(__file__).parents[1]
    search_dirs = [root / "src", root / "tools", root / "examples"]
    offenders: list[str] = []
    for d in search_dirs:
        if not d.exists():
            continue
        for p in d.rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                ls = line.lstrip()
                if not (ls.startswith("import ") or ls.startswith("from ")):
                    continue
                for prefix, suffix in FORBIDDEN_IMPORT_PATTERNS:
                    if ls.startswith(prefix) and suffix in ls:
                        offenders.append(f"{p}: '{ls.strip()}'")

    assert not offenders, "Legacy imports found:\n" + "\n".join(offenders)
