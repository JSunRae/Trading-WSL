# scripts/find_unused_code.py
import json
from datetime import datetime
from pathlib import Path

coverage_file = Path("coverage.json")
report_file = Path("reports/unused_code_report.md")

data = json.load(open(coverage_file))
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

lines = [f"# Unused Code Report\nGenerated: {timestamp}\n"]
for file, info in data["files"].items():
    for func, f_info in info.get("functions", {}).items():
        if f_info["summary"]["percent_covered"] == 0.0:
            lines.append(f"- `{func}` in `{file}` — never executed")

report_file.parent.mkdir(exist_ok=True)
report_file.write_text("\n".join(lines))

print(f"Report written to {report_file}")
