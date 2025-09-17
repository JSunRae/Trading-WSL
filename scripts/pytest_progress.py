#!/usr/bin/env python3
"""
pytest_progress.py

Wraps pytest to provide a progress bar with ETA and expected finish time.
- Pre-collects tests to determine total count
- Streams live output from pytest while printing a single-line progress indicator
- Computes ETA based on exponential moving average of per-test durations

Usage:
  ./scripts/pytest_progress.py [pytest args...]

This script is lightweight and has no external dependencies.
"""

from __future__ import annotations

import subprocess
import sys
import time


def _run_collect(py_args: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "--collect-only"] + py_args
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as e:
        # Fallback: if collect fails, assume unknown and proceed
        sys.stderr.write(e.output)
        return 0
    count = 0
    for line in out.splitlines():
        # Common pattern: <Module> <Function> items
        if line.strip().startswith("<") and line.strip().endswith(">"):
            continue
        if "::" in line:
            count += 1
    # If pytest prints summary like 'collected N items', prefer that
    for line in out.splitlines():
        if "collected " in line and " items" in line:
            try:
                n = int(line.split("collected ")[1].split(" items")[0].strip())
                count = max(count, n)
            except Exception:
                pass
    return count


def _fmt_eta(elapsed_s: float, remaining_s: float) -> str:
    end_ts = time.time() + remaining_s
    end = time.localtime(end_ts)
    end_str = time.strftime("%H:%M:%S", end)
    return f"ETA {end_str}"


def main(argv: list[str]) -> int:
    # Separate our flags vs pytest args (we just pass-through)
    py_args = argv

    total = _run_collect(py_args)
    total = total if total > 0 else 0

    # Start pytest run
    cmd = [sys.executable, "-m", "pytest"] + py_args
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )

    start = time.time()
    done = 0
    ema = None  # exponential moving average per-test duration
    alpha = 0.15

    width = 30

    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        # Detect test progress from pytest verbose lines when available
        # Heuristic: lines like 'test_x.py::test_y PASSED'
        if (
            " PASSED" in line
            or " FAILED" in line
            or " SKIPPED" in line
            or " XFAIL" in line
            or " XPASS" in line
        ):
            done += 1
            now = time.time()
            per = (now - start) / max(done, 1)
            ema = per if ema is None else (alpha * per + (1 - alpha) * ema)
            # Compute remaining
            remaining_tests = max(total - done, 0) if total else 0
            remaining_s = (ema or per) * remaining_tests
            progress = (done / total) if total else 0.0
            bar = "#" * int(width * progress) + "-" * (width - int(width * progress))
            eta = _fmt_eta(now - start, remaining_s) if total else "ETA --:--:--"
            prefix = (
                f"[{bar}] {done}/{total if total else '?'} {int(progress * 100):3d}%"
                if total
                else f"[{bar}] {done}"
            )
            sys.stdout.write(f"\r{prefix}  {eta}  running…")
            sys.stdout.flush()
        # Always forward original pytest output
        sys.stdout.write("\n" + line)
        sys.stdout.flush()

    rc = proc.wait()
    # Final newline after our progress line
    sys.stdout.write("\n")
    sys.stdout.flush()
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
