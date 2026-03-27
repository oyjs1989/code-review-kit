#!/usr/bin/env bash
# analyze-go.sh - Analyze Go source files for structural metrics
# Usage:
#   analyze-go.sh file1.go file2.go ...
#   find . -name '*.go' | analyze-go.sh
#
# Output: JSON to stdout with per-file and per-function metrics.

set -euo pipefail

# ---------------------------------------------------------------------------
# Collect file paths: from arguments or from stdin
# ---------------------------------------------------------------------------
declare -a FILES=()

if [[ $# -gt 0 ]]; then
    for arg in "$@"; do
        FILES+=("$arg")
    done
else
    while IFS= read -r line; do
        [[ -n "$line" ]] && FILES+=("$line")
    done
fi

if [[ ${#FILES[@]} -eq 0 ]]; then
    echo '{"files":[],"summary":{"files_over_800":0,"functions_over_80":0,"nesting_violations":0}}' >&1
    exit 0
fi

# ---------------------------------------------------------------------------
# Per-file analysis via awk
# ---------------------------------------------------------------------------
# We build a JSON array by processing files one at a time, then wrap with
# a summary object.

FILES_OVER_800=0
FUNCTIONS_OVER_80=0
NESTING_VIOLATIONS=0

# Accumulate JSON file entries into a temp file so we can count easily.
TMP_FILES_JSON=$(mktemp)
trap 'rm -f "$TMP_FILES_JSON"' EXIT

FIRST_FILE=1

for filepath in "${FILES[@]}"; do
    # Validate the file exists and is readable
    if [[ ! -f "$filepath" ]]; then
        echo "WARNING: file not found, skipping: $filepath" >&2
        continue
    fi
    if [[ ! -r "$filepath" ]]; then
        echo "WARNING: file not readable, skipping: $filepath" >&2
        continue
    fi

    # Run the heavy analysis in a single awk pass.
    # The awk script:
    #   1. Counts total lines.
    #   2. Detects function start lines (lines matching ^func ).
    #   3. Tracks brace depth to find function end and max nesting.
    #   4. Outputs one JSON block per function, plus a file summary line.
    #
    # Output format from awk (one record per line, tab-separated):
    #   FILE_LINES <total_lines>
    #   FUNC <name> <start_line> <func_line_count> <max_nesting>

    AWK_OUTPUT=$(awk '
    BEGIN {
        total_lines      = 0
        in_func          = 0
        func_name        = ""
        func_start       = 0
        brace_depth      = 0
        func_brace_start = 0
        max_nesting      = 0
    }

    # Helper: strip leading/trailing whitespace from a string
    function trim(s,    r) {
        r = s
        gsub(/^[ \t]+|[ \t]+$/, "", r)
        return r
    }

    # Helper: count occurrences of character c in string s
    function count_char(s, c,    i, n, cnt) {
        cnt = 0
        n = length(s)
        for (i = 1; i <= n; i++) {
            if (substr(s, i, 1) == c) cnt++
        }
        return cnt
    }

    # Helper: escape a string for JSON
    function json_escape(s,    r) {
        r = s
        gsub(/\\/, "\\\\", r)
        gsub(/"/, "\\\"", r)
        gsub(/\n/, "\\n", r)
        gsub(/\r/, "\\r", r)
        gsub(/\t/, "\\t", r)
        return r
    }

    {
        total_lines++
        line = $0

        # --- function detection: line starts with "func " (package-level) ---
        if (!in_func && match(line, /^func[[:space:]]+/)) {
            # Extract function name: text between "func[...](..." possibly
            # with receiver "(type) FuncName" pattern.
            fname = line
            # Remove leading "func "
            sub(/^func[[:space:]]+/, "", fname)
            # If receiver present: "(ReceiverType) MethodName(...)"
            if (substr(fname, 1, 1) == "(") {
                # Drop everything up to and including the closing ")"
                sub(/^\([^)]*\)[[:space:]]*/, "", fname)
            }
            # fname now starts with FuncName(...)
            # Extract up to first "("
            if (match(fname, /\(/)) {
                fname = substr(fname, 1, RSTART - 1)
            }
            fname = trim(fname)
            if (fname == "") fname = "<anonymous>"

            in_func          = 1
            func_name        = fname
            func_start       = total_lines
            brace_depth      = 0
            func_brace_start = 0
            max_nesting      = 0

            # Count braces on the same line as func declaration
            open_on_decl  = count_char(line, "{")
            close_on_decl = count_char(line, "}")
            brace_depth  += open_on_decl - close_on_decl
            if (open_on_decl > 0 && func_brace_start == 0) {
                func_brace_start = 1
            }
            # Nesting inside function body = brace_depth - 1 (subtract the
            # outermost function brace)
            body_depth = brace_depth - 1
            if (body_depth > max_nesting) max_nesting = body_depth

            # Check if the function ends on the same declaration line
            if (func_brace_start && brace_depth == 0) {
                func_lines = total_lines - func_start + 1
                printf "FUNC\t%s\t%d\t%d\t%d\n", json_escape(func_name), func_start, func_lines, max_nesting
                in_func = 0
            }
            next
        }

        # --- inside a function: track braces ---
        if (in_func) {
            open_cnt  = count_char(line, "{")
            close_cnt = count_char(line, "}")
            brace_depth += open_cnt - close_cnt
            if (open_cnt > 0 && func_brace_start == 0) {
                func_brace_start = 1
            }
            # Body nesting depth = brace_depth minus the outermost func brace
            body_depth = brace_depth - 1
            if (body_depth > max_nesting) max_nesting = body_depth

            # Detect function end: braces balanced back to 0 after opening
            if (func_brace_start && brace_depth <= 0) {
                func_lines = total_lines - func_start + 1
                printf "FUNC\t%s\t%d\t%d\t%d\n", json_escape(func_name), func_start, func_lines, max_nesting
                in_func          = 0
                func_name        = ""
                func_start       = 0
                brace_depth      = 0
                func_brace_start = 0
                max_nesting      = 0
            }
        }
    }

    END {
        printf "FILE_LINES\t%d\n", total_lines
    }
    ' "$filepath")

    # Parse awk output
    FILE_TOTAL_LINES=$(echo "$AWK_OUTPUT" | awk -F'\t' '$1=="FILE_LINES"{print $2}')
    FILE_TOTAL_LINES=${FILE_TOTAL_LINES:-0}

    OVER_800=false
    if [[ "$FILE_TOTAL_LINES" -gt 800 ]]; then
        OVER_800=true
        FILES_OVER_800=$((FILES_OVER_800 + 1))
    fi

    # Build function JSON array
    FUNC_JSON_ARRAY="[]"
    FUNC_ENTRIES=""
    FUNC_COUNT=0

    while IFS=$'\t' read -r rec_type fname fstart flines fnesting; do
        [[ "$rec_type" != "FUNC" ]] && continue

        OVER_80_LINES=false
        OVER_4_NESTING=false

        if [[ "$flines" -gt 80 ]]; then
            OVER_80_LINES=true
            FUNCTIONS_OVER_80=$((FUNCTIONS_OVER_80 + 1))
        fi
        if [[ "$fnesting" -gt 4 ]]; then
            OVER_4_NESTING=true
            NESTING_VIOLATIONS=$((NESTING_VIOLATIONS + 1))
        fi

        ENTRY=$(printf '{"name":"%s","start_line":%d,"lines":%d,"max_nesting":%d,"violations":{"over_80_lines":%s,"over_4_nesting":%s}}' \
            "$fname" "$fstart" "$flines" "$fnesting" "$OVER_80_LINES" "$OVER_4_NESTING")

        if [[ $FUNC_COUNT -gt 0 ]]; then
            FUNC_ENTRIES="${FUNC_ENTRIES},${ENTRY}"
        else
            FUNC_ENTRIES="${ENTRY}"
        fi
        FUNC_COUNT=$((FUNC_COUNT + 1))
    done <<< "$AWK_OUTPUT"

    if [[ -n "$FUNC_ENTRIES" ]]; then
        FUNC_JSON_ARRAY="[${FUNC_ENTRIES}]"
    fi

    # Escape the file path for JSON
    ESCAPED_PATH=$(printf '%s' "$filepath" | awk '{
        gsub(/\\/, "\\\\")
        gsub(/"/, "\\\"")
        print
    }')

    FILE_ENTRY=$(printf '{"path":"%s","lines":%d,"violations":{"over_800_lines":%s},"functions":%s}' \
        "$ESCAPED_PATH" "$FILE_TOTAL_LINES" "$OVER_800" "$FUNC_JSON_ARRAY")

    if [[ $FIRST_FILE -eq 1 ]]; then
        printf '%s' "$FILE_ENTRY" >> "$TMP_FILES_JSON"
        FIRST_FILE=0
    else
        printf ',%s' "$FILE_ENTRY" >> "$TMP_FILES_JSON"
    fi
done

# ---------------------------------------------------------------------------
# Assemble final JSON output
# ---------------------------------------------------------------------------
FILES_ARRAY_CONTENT=$(cat "$TMP_FILES_JSON")

printf '{"files":[%s],"summary":{"files_over_800":%d,"functions_over_80":%d,"nesting_violations":%d}}\n' \
    "$FILES_ARRAY_CONTENT" \
    "$FILES_OVER_800" \
    "$FUNCTIONS_OVER_80" \
    "$NESTING_VIOLATIONS"
