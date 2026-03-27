#!/usr/bin/env bash
# run-go-tools.sh - Run real Go tooling on specified source files
# Usage:
#   find . -name '*.go' | run-go-tools.sh
#   echo "service/user.go" | run-go-tools.sh
#
# Input:  Go file paths via stdin (one per line)
# Output: JSON to stdout with build errors, vet issues, staticcheck issues,
#         and large file metrics.
#
# IMPORTANT: Run this script from the project root (where go.mod lives).

set -euo pipefail

# ---------------------------------------------------------------------------
# Collect Go file paths from stdin
# ---------------------------------------------------------------------------
declare -a GO_FILES=()
while IFS= read -r line; do
    [[ -n "$line" ]] && GO_FILES+=("$line")
done

# Empty output structure
EMPTY_JSON='{"build_errors":[],"vet_issues":[],"staticcheck_issues":[],"cognitive_complexity":[],"large_files":[],"summary":{"build_errors":0,"vet_issues":0,"staticcheck_issues":0,"cognitive_complexity":0}}'

if [[ ${#GO_FILES[@]} -eq 0 ]]; then
    printf '%s\n' "$EMPTY_JSON"
    exit 0
fi

# ---------------------------------------------------------------------------
# Check that go is available
# ---------------------------------------------------------------------------
if ! command -v go &>/dev/null; then
    echo "WARNING: 'go' is not installed; skipping go build/vet analysis" >&2
    printf '%s\n' "$EMPTY_JSON"
    exit 0
fi

# ---------------------------------------------------------------------------
# Validate files and extract unique package directories
# ---------------------------------------------------------------------------
declare -a VALID_FILES=()
declare -A PKG_DIRS=()   # associative set of unique dirs

for f in "${GO_FILES[@]}"; do
    if [[ "$f" = /* ]]; then
        echo "WARNING: absolute path not supported, use relative paths from project root: $f" >&2
        continue
    fi
    if [[ ! -f "$f" ]]; then
        echo "WARNING: file not found, skipping: $f" >&2
        continue
    fi
    VALID_FILES+=("$f")
    dir=$(dirname "$f")
    # Normalise to ./dir form for go tooling
    if [[ "$dir" == "." ]]; then
        PKG_DIRS["./"]=1
    else
        PKG_DIRS["./${dir#./}"]=1
    fi
done

if [[ ${#VALID_FILES[@]} -eq 0 ]]; then
    printf '%s\n' "$EMPTY_JSON"
    exit 0
fi

# Build unique package list as a bash array
declare -a PACKAGES=()
for pkg in "${!PKG_DIRS[@]}"; do
    PACKAGES+=("$pkg")
done

# ---------------------------------------------------------------------------
# Helper: JSON-escape a string
# Use python3 if available for correctness; fall back to sed.
# ---------------------------------------------------------------------------
json_escape() {
    local raw="$1"
    python3 -c "import json,sys; sys.stdout.write(json.dumps(sys.argv[1])[1:-1])" "$raw" 2>/dev/null && return
    # python3 unavailable: use awk as fallback (handles \n, \r, \t, \, ")
    printf '%s' "$raw" | awk '{
        gsub(/\\/, "\\\\")
        gsub(/"/, "\\\"")
        gsub(/\t/, "\\t")
        printf "%s", $0
    }'
}

# ---------------------------------------------------------------------------
# Temporary work area
# ---------------------------------------------------------------------------
TMP_DIR=$(mktemp -d) || { echo "ERROR: cannot create temp directory" >&2; exit 1; }
trap 'rm -rf "$TMP_DIR"' EXIT

BUILD_OUT="$TMP_DIR/build.txt"
VET_OUT="$TMP_DIR/vet.txt"
SC_OUT="$TMP_DIR/staticcheck.txt"
COGNIT_OUT="$TMP_DIR/gocognit.txt"

# ---------------------------------------------------------------------------
# Tier 1 – go build
# Captures compilation errors; non-zero exit is expected when there are errors.
# ---------------------------------------------------------------------------
go build "${PACKAGES[@]}" 2>"$BUILD_OUT" || true

# ---------------------------------------------------------------------------
# Tier 2 – go vet
# ---------------------------------------------------------------------------
go vet "${PACKAGES[@]}" 2>"$VET_OUT" || true

# ---------------------------------------------------------------------------
# Tier 3 – staticcheck (optional)
# ---------------------------------------------------------------------------
touch "$SC_OUT"
if command -v staticcheck &>/dev/null; then
    staticcheck "${PACKAGES[@]}" > "$SC_OUT" 2>&1 || true
fi

# ---------------------------------------------------------------------------
# Tier 4 – gocognit (optional) - Cognitive complexity
# Threshold: >15 reported; score >25 → P1, 16-25 → P2
# Install: go install github.com/uudashr/gocognit/cmd/gocognit@latest
# ---------------------------------------------------------------------------
touch "$COGNIT_OUT"
if command -v gocognit &>/dev/null; then
    gocognit -over 15 "${VALID_FILES[@]}" > "$COGNIT_OUT" 2>&1 || true
fi

# ---------------------------------------------------------------------------
# Count large files (> 800 lines)
# ---------------------------------------------------------------------------
declare -a LARGE_FILES_ENTRIES=()
for f in "${VALID_FILES[@]}"; do
    line_count=$(wc -l < "$f" 2>/dev/null || echo 0)
    if [[ "$line_count" -gt 800 ]]; then
        ESC_FILE=$(json_escape "$f")
        LARGE_FILES_ENTRIES+=("{\"file\":\"${ESC_FILE}\",\"lines\":${line_count}}")
    fi
done

# ---------------------------------------------------------------------------
# Parse output format: filename.go:line:col: message
# Returns severity based on caller context (build vs vet) and message content.
# ---------------------------------------------------------------------------

# Vet severity: escalate certain known-critical messages to P0.
vet_severity() {
    local msg="$1"
    case "$msg" in
        *"assign to entry in nil map"*|*"copylock"*|*"nilness"*)
            echo "P0" ;;
        *)
            echo "P1" ;;
    esac
}

# Staticcheck severity mapping by code prefix.
staticcheck_severity() {
    local code="$1"
    case "$code" in
        SA*)  echo "P0" ;;
        S1*)  echo "P2" ;;
        ST1*) echo "P2" ;;
        *)    echo "P1" ;;
    esac
}

# ---------------------------------------------------------------------------
# Build a JSON array from a raw tool output file.
#
# Arguments:
#   $1 – input file path
#   $2 – "build", "vet", or "staticcheck"
#
# Output: populates the named result arrays and counters via global vars.
# ---------------------------------------------------------------------------
BUILD_COUNT=0
VET_COUNT=0
SC_COUNT=0
COGNIT_COUNT=0
TMP_BUILD_JSON="$TMP_DIR/build_entries.txt"
TMP_VET_JSON="$TMP_DIR/vet_entries.txt"
TMP_SC_JSON="$TMP_DIR/sc_entries.txt"
TMP_COGNIT_JSON="$TMP_DIR/cognit_entries.txt"
touch "$TMP_BUILD_JSON" "$TMP_VET_JSON" "$TMP_SC_JSON" "$TMP_COGNIT_JSON"

# --- parse build errors ---
while IFS= read -r raw_line; do
    [[ -z "$raw_line" ]] && continue
    # Expected format: path/to/file.go:LINE:COL: message
    # Also handle: path/to/file.go:LINE: message (no col)
    if [[ "$raw_line" =~ ^([^:]+\.go):([0-9]+):[0-9]+:[[:space:]](.+)$ ]]; then
        b_file="${BASH_REMATCH[1]}"
        b_line="${BASH_REMATCH[2]}"
        b_msg="${BASH_REMATCH[3]}"
    elif [[ "$raw_line" =~ ^([^:]+\.go):([0-9]+):[[:space:]](.+)$ ]]; then
        b_file="${BASH_REMATCH[1]}"
        b_line="${BASH_REMATCH[2]}"
        b_msg="${BASH_REMATCH[3]}"
    else
        # Non-file-prefixed build error (module/package error) - warn to stderr
        echo "WARNING: go build: $raw_line" >&2
        continue
    fi
    ESC_FILE=$(json_escape "$b_file")
    ESC_MSG=$(json_escape "$b_msg")
    if [[ $BUILD_COUNT -gt 0 ]]; then
        printf ',{"file":"%s","line":%s,"message":"%s","severity":"P0"}' \
            "$ESC_FILE" "$b_line" "$ESC_MSG" >> "$TMP_BUILD_JSON"
    else
        printf '{"file":"%s","line":%s,"message":"%s","severity":"P0"}' \
            "$ESC_FILE" "$b_line" "$ESC_MSG" >> "$TMP_BUILD_JSON"
    fi
    BUILD_COUNT=$((BUILD_COUNT + 1))
done < "$BUILD_OUT"

# --- parse vet issues ---
while IFS= read -r raw_line; do
    [[ -z "$raw_line" ]] && continue
    # go vet prefixes lines with "#" for package headers – skip them
    [[ "$raw_line" == \#* ]] && continue
    if [[ "$raw_line" =~ ^([^:]+\.go):([0-9]+):[0-9]+:[[:space:]](.+)$ ]]; then
        v_file="${BASH_REMATCH[1]}"
        v_line="${BASH_REMATCH[2]}"
        v_msg="${BASH_REMATCH[3]}"
    elif [[ "$raw_line" =~ ^([^:]+\.go):([0-9]+):[[:space:]](.+)$ ]]; then
        v_file="${BASH_REMATCH[1]}"
        v_line="${BASH_REMATCH[2]}"
        v_msg="${BASH_REMATCH[3]}"
    else
        continue
    fi
    v_sev=$(vet_severity "$v_msg")
    ESC_FILE=$(json_escape "$v_file")
    ESC_MSG=$(json_escape "$v_msg")
    if [[ $VET_COUNT -gt 0 ]]; then
        printf ',{"file":"%s","line":%s,"message":"%s","severity":"%s"}' \
            "$ESC_FILE" "$v_line" "$ESC_MSG" "$v_sev" >> "$TMP_VET_JSON"
    else
        printf '{"file":"%s","line":%s,"message":"%s","severity":"%s"}' \
            "$ESC_FILE" "$v_line" "$ESC_MSG" "$v_sev" >> "$TMP_VET_JSON"
    fi
    VET_COUNT=$((VET_COUNT + 1))
done < "$VET_OUT"

# --- parse staticcheck issues ---
# staticcheck output format: path/to/file.go:LINE:COL: CODE message
while IFS= read -r raw_line; do
    [[ -z "$raw_line" ]] && continue
    # Match: file.go:line:col: CODE message
    if [[ "$raw_line" =~ ^([^:]+\.go):([0-9]+):[0-9]+:[[:space:]]([A-Z]+[0-9]+)[[:space:]](.+)$ ]]; then
        s_file="${BASH_REMATCH[1]}"
        s_line="${BASH_REMATCH[2]}"
        s_code="${BASH_REMATCH[3]}"
        s_msg="${BASH_REMATCH[4]}"
    else
        continue
    fi
    s_sev=$(staticcheck_severity "$s_code")
    ESC_FILE=$(json_escape "$s_file")
    ESC_CODE=$(json_escape "$s_code")
    ESC_MSG=$(json_escape "$s_msg")
    if [[ $SC_COUNT -gt 0 ]]; then
        printf ',{"file":"%s","line":%s,"code":"%s","message":"%s","severity":"%s"}' \
            "$ESC_FILE" "$s_line" "$ESC_CODE" "$ESC_MSG" "$s_sev" >> "$TMP_SC_JSON"
    else
        printf '{"file":"%s","line":%s,"code":"%s","message":"%s","severity":"%s"}' \
            "$ESC_FILE" "$s_line" "$ESC_CODE" "$ESC_MSG" "$s_sev" >> "$TMP_SC_JSON"
    fi
    SC_COUNT=$((SC_COUNT + 1))
done < "$SC_OUT"

# --- parse gocognit output ---
# gocognit output format: FunctionName (score) path/to/file.go:line:col
while IFS= read -r raw_line; do
    [[ -z "$raw_line" ]] && continue
    if [[ "$raw_line" =~ ^([^[:space:]]+)[[:space:]]+\(([0-9]+)\)[[:space:]]+([^:]+\.go):([0-9]+):[0-9]+$ ]]; then
        c_func="${BASH_REMATCH[1]}"
        c_score="${BASH_REMATCH[2]}"
        c_file="${BASH_REMATCH[3]}"
        c_line="${BASH_REMATCH[4]}"
    else
        continue
    fi
    if [[ "$c_score" -gt 25 ]]; then
        c_sev="P1"
    else
        c_sev="P2"
    fi
    ESC_FUNC=$(json_escape "$c_func")
    ESC_FILE=$(json_escape "$c_file")
    if [[ $COGNIT_COUNT -gt 0 ]]; then
        printf ',{"function":"%s","score":%s,"file":"%s","line":%s,"severity":"%s"}' \
            "$ESC_FUNC" "$c_score" "$ESC_FILE" "$c_line" "$c_sev" >> "$TMP_COGNIT_JSON"
    else
        printf '{"function":"%s","score":%s,"file":"%s","line":%s,"severity":"%s"}' \
            "$ESC_FUNC" "$c_score" "$ESC_FILE" "$c_line" "$c_sev" >> "$TMP_COGNIT_JSON"
    fi
    COGNIT_COUNT=$((COGNIT_COUNT + 1))
done < "$COGNIT_OUT"

# ---------------------------------------------------------------------------
# Assemble large_files JSON array
# ---------------------------------------------------------------------------
LARGE_FILES_JSON="[]"
if [[ ${#LARGE_FILES_ENTRIES[@]} -gt 0 ]]; then
    # Join entries with comma
    joined=""
    for entry in "${LARGE_FILES_ENTRIES[@]}"; do
        if [[ -z "$joined" ]]; then
            joined="$entry"
        else
            joined="${joined},${entry}"
        fi
    done
    LARGE_FILES_JSON="[${joined}]"
fi

# ---------------------------------------------------------------------------
# Final JSON assembly
# ---------------------------------------------------------------------------
BUILD_CONTENT=$(cat "$TMP_BUILD_JSON")
VET_CONTENT=$(cat "$TMP_VET_JSON")
SC_CONTENT=$(cat "$TMP_SC_JSON")
COGNIT_CONTENT=$(cat "$TMP_COGNIT_JSON")

printf '{"build_errors":[%s],"vet_issues":[%s],"staticcheck_issues":[%s],"cognitive_complexity":[%s],"large_files":%s,"summary":{"build_errors":%d,"vet_issues":%d,"staticcheck_issues":%d,"cognitive_complexity":%d}}\n' \
    "$BUILD_CONTENT" \
    "$VET_CONTENT" \
    "$SC_CONTENT" \
    "$COGNIT_CONTENT" \
    "$LARGE_FILES_JSON" \
    "$BUILD_COUNT" \
    "$VET_COUNT" \
    "$SC_COUNT" \
    "$COGNIT_COUNT"
