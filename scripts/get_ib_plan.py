#!/usr/bin/env python3
"""
Get IB connection plan for shell scripts.
Outputs JSON to stdout for consumption by bash scripts.
"""

import json
import sys

try:
    from src.infra.ib_conn import get_ib_connect_plan
except ImportError as e:
    print(f"Cannot import canonical connection functions: {e}", file=sys.stderr)
    sys.exit(1)


def main():
    try:
        plan = get_ib_connect_plan()
        print(json.dumps(plan))
    except Exception as e:
        print(f"Failed to get connection plan: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
