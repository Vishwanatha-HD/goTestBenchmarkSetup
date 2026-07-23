#!/bin/bash

# ============================================================
# DAILY GO BENCHMARK PIPELINE
# ============================================================
#
# This script performs:
#
# 1. Checkout latest Go master branch
# 2. Build Go toolchain
# 3. Run ALL src micro-benchmarks (6 iterations)
# 4. Compare with previous day's results
# 5. Generate:
#       - benchstat.txt
#       - report.xlsx
#       - report.html
# 6. Store metadata and logs
#
# ============================================================

# ============================================================
# CONFIGURATION
# ============================================================

echo "Installing python3 dependency packages..."
apt-get update -y

apt-get install -y python3-pip
apt-get install -y python3.12-venv
apt-get install -y libjpeg-dev zlib1g-dev

python3 -m venv .venv
source .venv/bin/activate
sudo apt update
sudo apt install libjpeg-dev zlib1g-dev
pip install --no-cache-dir pillow
pip install pandas matplotlib openpyxl
pip install XlsxWriter
pip install jinja2
pip install beautifulsoup4 lxml

BASE_DIR="$HOME/benchmarkTests"

GO_DIR="$HOME/go"
RESULTS_DIR="$BASE_DIR/results"
LOG_DIR="$BASE_DIR/logs"
SCRIPT_DIR="$BASE_DIR/scripts"

TODAY=$(date +%F)
YESTERDAY=$(date -d "yesterday" +%F)

TODAY_DIR="$RESULTS_DIR/$TODAY"
YESTERDAY_DIR="$RESULTS_DIR/$YESTERDAY"

# ================================================================
# Create a "Base" directory for this project, if it doesn't exist
# ================================================================
if [ ! -d "$BASE_DIR" ]; then
    mkdir -p "$BASE_DIR"
    echo "benchmarkTests directory created: $BASE_DIR"
else
    echo "benchmarkTests directory already exists: $BASE_DIR"
fi


# =================================================================================
# Create a "Scripts" directory and copy all the scripts, if it not done previously
# =================================================================================
if [ ! -d "$SCRIPT_DIR" ]; then
    mkdir -p "$SCRIPT_DIR"
    echo "scripts directory created: $SCRIPT_DIR"
    find / -type f -name "daily_go_benchmark_pipeline.sh" -exec cp {} "$SCRIPT_DIR/" \; 2>/dev/null
    find / -type f -name "generate_dashboard.py" -exec cp {} "$SCRIPT_DIR/" \; 2>/dev/null
    find / -type f -name "generate_excel.py" -exec cp {} "$SCRIPT_DIR/" \; 2>/dev/null
    chmod 0755 -R "$SCRIPT_DIR/"/*
else
    echo "scripts directory already exists: $SCRIPT_DIR"
fi

# ==================================================
# Create a "Results" directory, if it doesn't exist
# ==================================================
if [ ! -d "$RESULTS_DIR" ]; then
    mkdir -p "$RESULTS_DIR"
    echo "results directory created: $RESULTS_DIR"
else
    echo "results directory already exists: $RESULTS_DIR"
fi

mkdir -p "$TODAY_DIR"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/daily_pipeline_$TODAY.log"

# ============================================================
# LOGGING
# ============================================================

exec > >(tee -a "$LOG_FILE") 2>&1

echo ""
echo "=========================================================="
echo "🚀 STARTING DAILY GO BENCHMARK PIPELINE"
echo "=========================================================="
echo "DATE            : $TODAY"
echo "BASE DIRECTORY  : $BASE_DIR"
echo "GO DIRECTORY    : $GO_DIR"
echo "RESULT DIRECTORY: $TODAY_DIR"
echo "LOG FILE        : $LOG_FILE"
echo "=========================================================="
echo ""

START_TIME=$(date +%s)

# ============================================================
# STEP 1: UPDATE GO MASTER
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 1: CHECKOUT LATEST GO MASTER"
echo "=========================================================="

if [ ! -d "$GO_DIR" ]; then
    mkdir -p "$GO_DIR"
    echo "go directory created: $GO_DIR"
else
    echo "go directory already exists: $GO_DIR"
fi

cd "$GO_DIR"

echo "Checking out master branch..."
git checkout master

echo "Pulling latest changes..."
git pull origin master

CURRENT_COMMIT=$(git rev-parse HEAD)

echo ""
echo "Current Commit:"
echo "$CURRENT_COMMIT"

# ============================================================
# STEP 2: BUILD GO
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 2: BUILDING GO TOOLCHAIN"
echo "=========================================================="

cd "$GO_DIR/src"

echo "Running make.bash..."
./make.bash

echo ""
echo "✅ Go build completed successfully"

# ============================================================
# STEP 3: RUN ALL SRC MICRO-BENCHMARKS
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 3: RUNNING ALL SRC MICRO-BENCHMARKS"
echo "=========================================================="

cd "$GO_DIR/src"

RAW_BENCH="$TODAY_DIR/benchmark_raw.txt"

echo ""
echo "Benchmark output file:"
echo "$RAW_BENCH"

echo ""
echo "Running all src benchmarks..."
echo "Benchmark count: 6"
echo ""

# ------------------------------------------------------------
# IMPORTANT:
# taskset is used for CPU affinity to reduce benchmark noise
# ------------------------------------------------------------

    # Adjust the "test.count" & "test.benchtime" values accordingly
    ./../bin/go test ./... -run=^$ -bench=. -benchmem -test.count=6 -test.benchtime=2s > "$RAW_BENCH"

echo ""
echo "✅ Benchmark execution completed"

# ============================================================
# STEP 4: GENERATE BENCHSTAT
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 4: GENERATING BENCHSTAT"
echo "=========================================================="


# ============================================================
# FIND PREVIOUS BENCHMARK RESULT
# ============================================================

echo ""
echo "Searching for previous benchmark results..."

CURRENT_RAW="$TODAY_DIR/benchmark_raw.txt"

PREV_RAW=$(
    find "$RESULTS_DIR" \
        -name benchmark_raw.txt \
        ! -path "$CURRENT_RAW" \
        | sort \
        | tail -1
)

if [ -z "$PREV_RAW" ]; then

    echo ""
    echo "⚠️ No previous benchmark result found"

    echo ""
    echo "Skipping benchstat comparison"
    echo "Skipping Excel generation"
    echo "Skipping Dashboard generation"

    exit 0
fi

echo ""
echo "Using previous benchmark:"
echo "$PREV_RAW"

BENCHSTAT_FILE="$TODAY_DIR/benchstat.txt"

echo ""
echo "Previous benchmark:"
echo "$PREV_RAW"

echo ""
echo "Current benchmark:"
echo "$RAW_BENCH"

echo ""
echo "Generating benchstat..."

# Ensure benchstat exists
command -v benchstat >/dev/null 2>&1 || {
    echo "benchstat not found. Installing...."
    go install golang.org/x/perf/cmd/benchstat@latest
    echo "done."
}

benchstat -format=text \
    "$PREV_RAW" \
    "$RAW_BENCH" \
    > "$BENCHSTAT_FILE"

echo ""
echo "✅ benchstat.txt generated"

# ============================================================
# STEP 5: GENERATE EXCEL REPORT
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 5: GENERATING EXCEL REPORT"
echo "=========================================================="

EXCEL_REPORT="$TODAY_DIR/report.xlsx"

python3 "$SCRIPT_DIR/generate_excel.py" \
    "$BENCHSTAT_FILE" \
    "$EXCEL_REPORT"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Excel report generation failed"
    exit 1
fi

echo ""
echo "✅ Excel report generated"

# ============================================================
# STEP 6: GENERATE HTML DASHBOARD
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 6: GENERATING HTML DASHBOARD"
echo "=========================================================="

HTML_REPORT="$TODAY_DIR/report.html"

# ------------------------------------------------------------
# Dashboard state tracking
#
# dashboard_state.json stores:
#   - packages classified as improvements
#   - packages classified as regressions
#
# This allows the dashboard to identify:
#   - NEW improvements
#   - NEW regressions
# compared to the previous run.
# ------------------------------------------------------------

STATE_FILE="$TODAY_DIR/dashboard_state.json"

PREV_STATE=""

if [ -f "$(dirname "$PREV_RAW")/dashboard_state.json" ]; then
    PREV_STATE="$(dirname "$PREV_RAW")/dashboard_state.json"

    echo ""
    echo "Previous dashboard state:"
    echo "$PREV_STATE"
else
    echo ""
    echo "No previous dashboard state found"
    echo "New improvement/regression sections will be based on an empty baseline"
fi

BASELINE_DATE=$(basename "$(dirname "$PREV_RAW")")

PREVIOUS_COMMIT="Unknown"

PREV_METADATA="$(dirname "$PREV_RAW")/metadata.txt"

if [ -f "$PREV_METADATA" ]; then

    PREVIOUS_COMMIT=$(grep "^Commit:" "$PREV_METADATA" \
        | head -1 \
        | cut -d' ' -f2)

fi

echo ""
echo "Generating HTML dashboard..."

python3 "$SCRIPT_DIR/generate_dashboard.py" \
    "$BENCHSTAT_FILE" \
    "$HTML_REPORT" \
    "$TODAY" \
    "$BASELINE_DATE" \
    "$CURRENT_COMMIT" \
    "$PREVIOUS_COMMIT" \
    "$STATE_FILE" \
    "$PREV_STATE"

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Dashboard generation failed"
    exit 1
fi

echo ""
echo "✅ HTML dashboard generated"

echo ""
echo "Dashboard State:"
echo "$STATE_FILE"

# ============================================================
# STEP 7: STORE METADATA
# ============================================================

echo ""
echo "=========================================================="
echo "STEP 7: STORING METADATA"
echo "=========================================================="

METADATA_FILE="$TODAY_DIR/metadata.txt"

cat <<EOF > "$METADATA_FILE"
Date: $TODAY
Commit: $CURRENT_COMMIT

Raw Benchmark File: $RAW_BENCH
Benchstat File: $BENCHSTAT_FILE

Excel Report: $EXCEL_REPORT
HTML Report: $HTML_REPORT

Dashboard State: $STATE_FILE
EOF

echo ""
echo "✅ Metadata stored"

# ============================================================
# STEP 8: PIPELINE COMPLETE
# ============================================================

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))

echo ""
echo "=========================================================="
echo "✅ DAILY GO BENCHMARK PIPELINE COMPLETED"
echo "=========================================================="

echo ""
echo "Artifacts Generated:"
echo "----------------------------------------------------------"
echo "Raw Benchmarks : $RAW_BENCH"
echo "Benchstat      : $BENCHSTAT_FILE"
echo "Excel Report   : $EXCEL_REPORT"
echo "HTML Dashboard : $HTML_REPORT"
echo "Metadata       : $METADATA_FILE"
echo "DashboardState : $STATE_FILE"

echo ""
echo "Go Commit:"
echo "$CURRENT_COMMIT"

echo ""
echo "Total Execution Time: ${TOTAL_TIME} seconds"

echo ""
echo "=========================================================="
echo "🚀 PIPELINE FINISHED SUCCESSFULLY"
echo "=========================================================="
echo ""
