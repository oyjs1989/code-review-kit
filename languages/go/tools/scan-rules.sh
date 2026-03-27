#!/usr/bin/env bash
# scan-rules.sh - Scan Go source files against YAML rule definitions
# Usage:
#   find . -name '*.go' | scan-rules.sh [rules_dir]
#   echo "service/user.go" | scan-rules.sh ./rules
#
# Arguments:
#   $1  (optional) Path to the rules/ directory.
#       Defaults to: $(dirname "$0")/../rules
#
# Input:  Go file paths via stdin (one per line)
# Output: JSON to stdout with all rule hits and a severity summary.

set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve rules directory
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RULES_DIR="${1:-${SCRIPT_DIR}/../rules}"

if [[ ! -d "$RULES_DIR" ]]; then
    echo "ERROR: rules directory not found: $RULES_DIR" >&2
    echo '{"hits":[],"summary":{"total":0,"P0":0,"P1":0,"P2":0}}' >&1
    exit 1
fi

# ---------------------------------------------------------------------------
# Collect Go file paths from stdin
# ---------------------------------------------------------------------------
declare -a GO_FILES=()
while IFS= read -r line; do
    [[ -n "$line" ]] && GO_FILES+=("$line")
done

if [[ ${#GO_FILES[@]} -eq 0 ]]; then
    echo '{"hits":[],"summary":{"total":0,"P0":0,"P1":0,"P2":0}}' >&1
    exit 0
fi

# ---------------------------------------------------------------------------
# Helper: parse a single YAML rule file
# Outputs tab-separated lines: id <TAB> severity <TAB> pattern <TAB> message
# Uses a heredoc for the awk program to avoid quoting issues.
# ---------------------------------------------------------------------------

# Write the awk program to a temp file so shell quoting cannot corrupt it.
AWK_PARSE_PROG=$(mktemp)
trap 'rm -f "$AWK_PARSE_PROG"' EXIT

cat > "$AWK_PARSE_PROG" << 'AWKPROG'
BEGIN {
    id = ""; severity = ""; pattern = ""; message = ""
    in_pattern_block = 0
    SQUOTE = "\047"
}

function trim(s,    r) {
    r = s
    gsub(/^[ \t]+|[ \t]+$/, "", r)
    return r
}

function strip_quotes(s,    r, first, last) {
    r = trim(s)
    if (length(r) >= 2) {
        first = substr(r, 1, 1)
        last  = substr(r, length(r), 1)
        if ((first == "\"" && last == "\"") || (first == SQUOTE && last == SQUOTE)) {
            r = substr(r, 2, length(r) - 2)
        }
    }
    return r
}

function flush_rule() {
    if (id != "" && severity != "" && pattern != "") {
        gsub(/\t/, " ", id)
        gsub(/\t/, " ", severity)
        gsub(/\t/, " ", message)
        printf "%s\t%s\t%s\t%s\n", id, severity, pattern, message
    }
    id = ""; severity = ""; pattern = ""; message = ""
    in_pattern_block = 0
}

# Detect start of a new rule block: "  - id: SAFE-001"
/^[[:space:]]*-[[:space:]]+id[[:space:]]*:/ {
    flush_rule()
    val = $0
    sub(/^[[:space:]]*-[[:space:]]+id[[:space:]]*:[[:space:]]*/, "", val)
    id = strip_quotes(trim(val))
    next
}

/^[[:space:]]*id[[:space:]]*:/ {
    val = $0
    sub(/^[[:space:]]*id[[:space:]]*:[[:space:]]*/, "", val)
    id = strip_quotes(trim(val))
    next
}

/^[[:space:]]*severity[[:space:]]*:/ {
    val = $0
    sub(/^[[:space:]]*severity[[:space:]]*:[[:space:]]*/, "", val)
    severity = strip_quotes(trim(val))
    next
}

/^[[:space:]]*pattern[[:space:]]*:/ {
    in_pattern_block = 1
    next
}

in_pattern_block && /^[[:space:]]*match[[:space:]]*:/ {
    val = $0
    sub(/^[[:space:]]*match[[:space:]]*:[[:space:]]*/, "", val)
    pattern = strip_quotes(trim(val))
    in_pattern_block = 0
    next
}

in_pattern_block && /^[^[:space:]]/ {
    in_pattern_block = 0
}

/^[[:space:]]*message[[:space:]]*:/ {
    val = $0
    sub(/^[[:space:]]*message[[:space:]]*:[[:space:]]*/, "", val)
    message = strip_quotes(trim(val))
    next
}

END {
    flush_rule()
}
AWKPROG

parse_rule_file() {
    local yaml_file="$1"
    awk -f "$AWK_PARSE_PROG" "$yaml_file" 2>/dev/null
}

# ---------------------------------------------------------------------------
# Load all rules from rules/*.yaml and rules/*.yml
# ---------------------------------------------------------------------------
declare -a RULE_IDS=()
declare -a RULE_SEVERITIES=()
declare -a RULE_PATTERNS=()
declare -a RULE_MESSAGES=()

RULE_COUNT=0
shopt -s nullglob
YAML_FILES=("$RULES_DIR"/*.yaml "$RULES_DIR"/*.yml)
shopt -u nullglob

if [[ ${#YAML_FILES[@]} -eq 0 ]]; then
    echo "WARNING: no YAML rule files found in: $RULES_DIR" >&2
    echo '{"hits":[],"summary":{"total":0,"P0":0,"P1":0,"P2":0}}' >&1
    exit 0
fi

for yaml_file in "${YAML_FILES[@]}"; do
    [[ -f "$yaml_file" ]] || continue

    parsed=$(parse_rule_file "$yaml_file") || {
        echo "WARNING: failed to parse rule file, skipping: $yaml_file" >&2
        continue
    }

    if [[ -z "$parsed" ]]; then
        echo "WARNING: no valid rule parsed from: $yaml_file" >&2
        continue
    fi

    # A single YAML file may define multiple rules (one TSV line each)
    while IFS=$'\t' read -r r_id r_sev r_pat r_msg; do
        [[ -z "$r_id" || -z "$r_pat" ]] && continue
        RULE_IDS+=("$r_id")
        RULE_SEVERITIES+=("$r_sev")
        RULE_PATTERNS+=("$r_pat")
        RULE_MESSAGES+=("$r_msg")
        RULE_COUNT=$((RULE_COUNT + 1))
    done <<< "$parsed"
done

if [[ $RULE_COUNT -eq 0 ]]; then
    echo "WARNING: no rules loaded from: $RULES_DIR" >&2
    echo '{"hits":[],"summary":{"total":0,"P0":0,"P1":0,"P2":0}}' >&1
    exit 0
fi

# ---------------------------------------------------------------------------
# Helper: escape a string for JSON (uses awk, no external deps)
# ---------------------------------------------------------------------------
json_escape() {
    printf '%s' "$1" | awk '
    {
        gsub(/\\/, "\\\\")
        gsub(/"/, "\\\"")
        gsub(/\n/, "\\n")
        gsub(/\r/, "\\r")
        gsub(/\t/, "\\t")
        printf "%s", $0
    }'
}

# ---------------------------------------------------------------------------
# Scan each Go file against each rule
# ---------------------------------------------------------------------------
TOTAL_HITS=0
P0_HITS=0
P1_HITS=0
P2_HITS=0

# Temporary file to accumulate JSON hit objects
TMP_HITS=$(mktemp)
# Append to trap for cleanup (AWK_PARSE_PROG already registered)
trap 'rm -f "$AWK_PARSE_PROG" "$TMP_HITS"' EXIT

FIRST_HIT=1

for go_file in "${GO_FILES[@]}"; do
    if [[ ! -f "$go_file" ]]; then
        echo "WARNING: file not found, skipping: $go_file" >&2
        continue
    fi
    if [[ ! -r "$go_file" ]]; then
        echo "WARNING: file not readable, skipping: $go_file" >&2
        continue
    fi

    for (( i=0; i<RULE_COUNT; i++ )); do
        r_id="${RULE_IDS[$i]}"
        r_sev="${RULE_SEVERITIES[$i]}"
        r_pat="${RULE_PATTERNS[$i]}"
        r_msg="${RULE_MESSAGES[$i]}"

        # Try perl-compatible regex first (richer syntax), fall back to extended
        GREP_OUT=""
        if grep -qP '' /dev/null 2>/dev/null; then
            GREP_OUT=$(grep -nP "$r_pat" "$go_file" 2>/dev/null || true)
        else
            GREP_OUT=$(grep -nE "$r_pat" "$go_file" 2>/dev/null || true)
        fi

        [[ -z "$GREP_OUT" ]] && continue

        # Each matching line is "lineno:matched_text"
        # Use a temp file to avoid issues with subshell variable scoping
        while IFS= read -r grep_line; do
            [[ -z "$grep_line" ]] && continue

            lineno="${grep_line%%:*}"
            matched_text="${grep_line#*:}"

            # Validate lineno is numeric
            [[ "$lineno" =~ ^[0-9]+$ ]] || continue

            TOTAL_HITS=$((TOTAL_HITS + 1))
            case "$r_sev" in
                P0) P0_HITS=$((P0_HITS + 1)) ;;
                P1) P1_HITS=$((P1_HITS + 1)) ;;
                P2) P2_HITS=$((P2_HITS + 1)) ;;
            esac

            ESC_FILE=$(json_escape "$go_file")
            ESC_MATCHED=$(json_escape "$matched_text")
            ESC_ID=$(json_escape "$r_id")
            ESC_SEV=$(json_escape "$r_sev")
            ESC_MSG=$(json_escape "$r_msg")

            HIT=$(printf '{"rule_id":"%s","severity":"%s","file":"%s","line":%d,"matched":"%s","message":"%s"}' \
                "$ESC_ID" "$ESC_SEV" "$ESC_FILE" "$lineno" "$ESC_MATCHED" "$ESC_MSG")

            if [[ $FIRST_HIT -eq 1 ]]; then
                printf '%s' "$HIT" >> "$TMP_HITS"
                FIRST_HIT=0
            else
                printf ',%s' "$HIT" >> "$TMP_HITS"
            fi
        done <<< "$GREP_OUT"
    done
done

# ---------------------------------------------------------------------------
# Assemble final JSON output
# ---------------------------------------------------------------------------
HITS_CONTENT=$(cat "$TMP_HITS")

printf '{"hits":[%s],"summary":{"total":%d,"P0":%d,"P1":%d,"P2":%d}}\n' \
    "$HITS_CONTENT" \
    "$TOTAL_HITS" \
    "$P0_HITS" \
    "$P1_HITS" \
    "$P2_HITS"
