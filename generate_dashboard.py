import re
import math
import json
import pandas as pd
from pathlib import Path
import sys

# ---------------------------------------------------------
# Handle Arguments
# ---------------------------------------------------------
if len(sys.argv) < 8:
    print(
        "Usage: generate_dashboard.py "
        "<benchstat.txt> <output.html> "
        "<run_date> <baseline_date> <commit> "
        "<state_file> [previous_state_file]"
    )
    sys.exit(1)

INPUT_FILE = Path(sys.argv[1])
OUTPUT_FILE = Path(sys.argv[2])

RUN_DATE = sys.argv[3]
BASELINE_DATE = sys.argv[4]
GO_COMMIT = sys.argv[5][:12]

PREVIOUS_COMMIT = sys.argv[6][:12]

STATE_FILE = Path(sys.argv[7])

PREVIOUS_STATE = None

if len(sys.argv) >= 9 and sys.argv[8]:
    PREVIOUS_STATE = Path(sys.argv[8])

THRESHOLD = 5
ALERT_THRESHOLD = 15

lines = INPUT_FILE.read_text().splitlines()

# ---------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------

def format_percent(val):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "%nan"
    return f"{val:+.2f}%"


def get_color(val, metric):

    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""

    if abs(val) < 1e-9:
        return ""

    return "green" if (val < 0 if metric == "sec/op" else val > 0) else "red"


def render_value(val, metric):

    txt = format_percent(val)
    color = get_color(val, metric)

    if color:
        return f'<span style="color:{color}; font-weight:bold;">{txt}</span>'

    return txt

def extract_geomean(section):

    for ln in section:

        if not ln.startswith("geomean"):
            continue

        m = re.search(r'([+-]?\d+\.\d+)%', ln)

        if m:
            return float(m.group(1))

        return 0.0

    return 0.0

def extract_map(section):
    d = {}

    for ln in section:

        # Normal percentage
        m = re.search(r'^(\S+).*?([+-]\d+\.\d+)%', ln)

        if m:
            d[m.group(1)] = float(m.group(2))
            continue

        # Benchstat "~" means no significant change
        m = re.search(r'^(\S+).*?~\s+\(p=', ln)

        if m:
            d[m.group(1)] = 0.0

    return d


def find_block(block, metric):

    for i, ln in enumerate(block):

        if metric in ln:

            section = []

            for j in range(i + 1, len(block)):

                if any(
                    x in block[j]
                    for x in ["sec/op", "B/op", "allocs/op"]
                ) and j != i + 1:
                    break

                section.append(block[j].strip())

            return section

    return []


def merge(sec, b, alloc):

    keys = set(sec) | set(b) | set(alloc)

    keys.discard("geomean")

    data = []

    for k in sorted(keys):

        data.append({
            "benchmark": k,
            "sec": sec.get(k),
            "b": b.get(k),
            "alloc": alloc.get(k)
        })

    return data


def count_regressions(benchmarks):

    count = 0

    for b in benchmarks:

        if (
            b["sec"] is not None
            and not math.isnan(b["sec"])
            and b["sec"] > 0
        ):
            count += 1

    return count


# ---------------------------------------------------------
# Parse benchstat
# ---------------------------------------------------------

packages = []

current_block = []
all_blocks = []

for line in lines:

    if line.startswith("pkg:"):

        if current_block:
            all_blocks.append(current_block)

        current_block = [line]

    else:
        current_block.append(line)

if current_block:
    all_blocks.append(current_block)

for block in all_blocks:

    if not block:
        continue

    if not block[0].startswith("pkg:"):
        continue

    pkg_name = block[0].replace("pkg:", "").strip()

    sec_b = find_block(block, "sec/op")

    b_b = find_block(block, "B/op")
    a_b = find_block(block, "allocs/op")

    sec_map = extract_map(sec_b)
    b_map = extract_map(b_b)
    a_map = extract_map(a_b)

    benchmarks = merge(sec_map, b_map, a_map)

    benchmarks = sorted(
        benchmarks,
        key=lambda x: (
            x["sec"]
            if x["sec"] is not None
            and not math.isnan(x["sec"])
            else -999999
        ),
        reverse=True
    )

    packages.append({
        "package": pkg_name,
        "sec": extract_geomean(sec_b),
        "b": extract_geomean(b_b),
        "alloc": extract_geomean(a_b),
        "benchmarks": benchmarks,
        "benchmark_count": len(benchmarks),
        "regressions": count_regressions(benchmarks)
    })


df = pd.DataFrame(packages)

all_packages = (
    df
    .sort_values("package")
    .to_dict("records")
)

alarming = (
    df[df["regressions"] > ALERT_THRESHOLD]
    .sort_values("regressions", ascending=False)
    .to_dict("records")
)

top_imp = (
    df[
        df["sec"].notna()
        & (df["sec"] < 0)
    ]
    .sort_values("sec")
    .to_dict("records")
)

top_reg = (
    df[
        df["sec"].notna()
        & (df["sec"] > 0)
    ]
    .sort_values("sec", ascending=False)
    .to_dict("records")
)

# ---------------------------------------------------------
# Sort sections
# ---------------------------------------------------------

# ---------------------------------------------------------
# Package summary view
# ---------------------------------------------------------

all_packages = (
    df
    .sort_values("package")
    .to_dict("records")
)

# ---------------------------------------------------------
# Alarming packages
# ---------------------------------------------------------

alarming = (
    df[df["regressions"] > ALERT_THRESHOLD]
    .sort_values("regressions", ascending=False)
    .to_dict("records")
)

# ---------------------------------------------------------
# Load previous state
# ---------------------------------------------------------

prev_improvements = set()
prev_regressions = set()

if PREVIOUS_STATE and PREVIOUS_STATE.exists():

    try:

        state = json.loads(
            PREVIOUS_STATE.read_text()
        )

        prev_improvements = set(
            state.get("improvements", [])
        )

        prev_regressions = set(
            state.get("regressions", [])
        )

    except Exception:
        pass

today_improvements = {
    p["package"]
    for p in top_imp
}

today_regressions = {
    p["package"]
    for p in top_reg
}

new_improvement_pkgs = (
    today_improvements - prev_improvements
)

new_regression_pkgs = (
    today_regressions - prev_regressions
)

new_improvements = [
    p for p in top_imp
    if p["package"] in new_improvement_pkgs
]

new_regressions = [
    p for p in top_reg
    if p["package"] in new_regression_pkgs
]

# ---------------------------------------------------------
# Save state
# ---------------------------------------------------------

dashboard_state = {
    "improvements": sorted(today_improvements),
    "regressions": sorted(today_regressions)
}

STATE_FILE.write_text(
    json.dumps(dashboard_state, indent=2)
)

# ---------------------------------------------------------
# HTML Rendering
# ---------------------------------------------------------

def render_table(benchmarks):

    html = """
    <table>
    <tr>
        <th>Benchmark</th>
        <th>sec/op</th>
        <th>B/op</th>
        <th>allocs/op</th>
    </tr>
    """

    for b in benchmarks:

        html += f"""
        <tr>
            <td>{b['benchmark']}</td>
            <td>{render_value(b['sec'], 'sec/op')}</td>
            <td>{render_value(b['b'], 'B/op')}</td>
            <td>{render_value(b['alloc'], 'allocs/op')}</td>
        </tr>
        """

    html += "</table>"

    return html


def render_pkg(pkgs, alarming_mode=False):

    html = ""

    if not pkgs:
        return "<p>No entries.</p>"

    for p in pkgs:

        reg_text = ""

        if p["regressions"] > 0:
            reg_text = f"⚠️ {p['regressions']} regressions"

        if alarming_mode:

            summary = f"""
            <b>{p['package']}</b> | {reg_text}
            """

        else:

            summary = f"""
            <b>{p['package']} (geomean)</b> |
            sec/op: {render_value(p['sec'], 'sec/op')} |
            B/op: {render_value(p['b'], 'B/op')} |
            allocs/op: {render_value(p['alloc'], 'allocs/op')} |
            {p['benchmark_count']} benchmarks
            """

            if reg_text:
                summary += f" | {reg_text}"

        html += f"""
        <div class="pkg-block">
        <details>
        <summary>{summary}</summary>

        <div class="indented">
        {render_table(p['benchmarks'])}
        </div>

        </details>
        </div>
        """

    return html


html_content = f"""
<html>
<head>

<meta charset="UTF-8">

<title>Go Benchmark Dashboard</title>

<style>

body {{
    font-family: Arial;
    margin: 40px;
    font-size: 16px;
}}

summary {{
    font-weight: bold;
    cursor: pointer;
    font-size: 20px;
}}

table {{
    border-collapse: collapse;
    width: 100%;
    margin-top: 10px;
}}

th, td {{
    border: 1px solid #ddd;
    padding: 6px;
    text-align: left;
    font-size: 15px;
}}

th {{
    background-color: #f2f2f2;
}}

.indented {{
    margin-left: 30px;
}}

.pkg-block {{
    margin-bottom: 14px;
}}

.section-spacing {{
    margin-top: 40px;
}}

.header-box {{
    background-color: #f7f7f7;
    border: 1px solid #cccccc;
    padding: 15px;
    margin-bottom: 30px;
    font-size: 18px;
    line-height: 1.8;
}}

.comparison-box {{
    background-color: #eef5ff;
    border-left: 6px solid #2f6fed;
    padding: 15px;
    margin-top: 15px;
    margin-bottom: 20px;

    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 17px;
    line-height: 1.8;

    color: #1d3f91;
}}

.rules-box {{
    background-color: #f4fff0;
    border-left: 6px solid #2e8b57;
    padding: 15px;
    margin-top: 15px;
    margin-bottom: 20px;

    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 17px;
    line-height: 1.8;

    color: #1f6b43;
}}

.box-title {{
    font-weight: bold;
    font-size: 18px;
}}

</style>

</head>

<body>

<h1>
🚀 Go Daily Benchmark Dashboard
(Run Date : {RUN_DATE})
</h1>

<details>

<summary>
📊 Newly Introduced Improvements / Regressions
</summary>

<div class="indented">

<div class="comparison-box">

<span class="box-title">
Comparison Window
</span>

<br>

{BASELINE_DATE} → {RUN_DATE}

<br><br>

<span class="box-title">
Commit Range
</span>

<br>

{PREVIOUS_COMMIT} → {GO_COMMIT}

</div>

<details>

<summary>
🆕 🟢 Performance Improvements
</summary>

<div class="indented">
{render_pkg(new_improvements)}
</div>

</details>

<div class="section-spacing"></div>

<details>

<summary>
🆕 🔴 Performance Regressions
</summary>

<div class="indented">
{render_pkg(new_regressions)}
</div>

</details>

</div>

</details>

<div class="section-spacing"></div>

<div class="section-spacing"></div>

<details>

<summary>
📈 Overall Package Benchmark Summary
</summary>

<div class="indented">

<div class="rules-box">

<span class="box-title">
Alarming Threshold
</span>

<br>

&gt; 15 benchmark regressions per package

</div>

<details>

<summary>
🔥 Alarming Changes
</summary>

<div class="indented">
{render_pkg(alarming, alarming_mode=True)}
</div>

</details>

<div class="section-spacing"></div>

<details>

<summary>
📦 Package Benchmark Results
</summary>

<div class="indented">
{render_pkg(all_packages)}
</div>

</details>

</div>

</details>

</body>
</html>
"""

OUTPUT_FILE.write_text(
    html_content,
    encoding="utf-8"
)

print(f"Dashboard generated: {OUTPUT_FILE}")
print(f"Dashboard state saved: {STATE_FILE}")
