#!/bin/bash
# Code Review Kit - Scanner Runner
# Runs integrated code scanning tools based on detected language

set -e

TARGET="${1:-.}"
OUTPUT_DIR="${2:-.review/scanner-results}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "  Code Review Kit - Scanner Runner"
echo "========================================"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Detect language
detect_language() {
    local dir="$1"
    
    if [ -f "$dir/go.mod" ]; then
        echo "go"
    elif [ -f "$dir/requirements.txt" ] || [ -f "$dir/pyproject.toml" ] || [ -f "$dir/setup.py" ]; then
        echo "python"
    elif [ -f "$dir/build.gradle.kts" ] || [ -f "$dir/build.gradle" ]; then
        echo "kotlin"
    elif [ -f "$dir/package.json" ] || [ -f "$dir/tsconfig.json" ]; then
        echo "typescript"
    else
        # Check file extensions
        local go_count=$(find "$dir" -name "*.go" 2>/dev/null | wc -l)
        local py_count=$(find "$dir" -name "*.py" 2>/dev/null | wc -l)
        local kt_count=$(find "$dir" -name "*.kt" 2>/dev/null | wc -l)
        local ts_count=$(find "$dir" -name "*.ts" -o -name "*.tsx" 2>/dev/null | wc -l)
        
        if [ "$go_count" -gt "$py_count" ] && [ "$go_count" -gt "$kt_count" ] && [ "$go_count" -gt "$ts_count" ]; then
            echo "go"
        elif [ "$py_count" -gt 0 ]; then
            echo "python"
        elif [ "$kt_count" -gt 0 ]; then
            echo "kotlin"
        elif [ "$ts_count" -gt 0 ]; then
            echo "typescript"
        else
            echo "unknown"
        fi
    fi
}

# Check if command exists
check_tool() {
    command -v "$1" >/dev/null 2>&1
}

# Run Go scanners
run_go_scanners() {
    local target="$1"
    local results_dir="$2"
    
    echo -e "${YELLOW}Running Go scanners...${NC}"
    
    # Tier 1: Build check
    if check_tool "go"; then
        echo "  [go build] Compiling..."
        cd "$target"
        go build ./... 2>"$results_dir/go-build.json" || true
        cd - > /dev/null
    fi
    
    # Tier 2: go vet
    if check_tool "go"; then
        echo "  [go vet] Running..."
        cd "$target"
        go vet ./... 2>"$results_dir/go-vet.json" || true
        cd - > /dev/null
    fi
    
    # Tier 3: staticcheck
    if check_tool "staticcheck"; then
        echo "  [staticcheck] Running..."
        cd "$target"
        staticcheck -f json ./... > "$results_dir/staticcheck.json" 2>/dev/null || true
        cd - > /dev/null
    else
        echo -e "  ${YELLOW}[staticcheck] Not installed. Install: go install honnef.co/go/tools/cmd/staticcheck@latest${NC}"
    fi
    
    # Tier 3: gocognit (cognitive complexity)
    if check_tool "gocognit"; then
        echo "  [gocognit] Running..."
        cd "$target"
        gocognit -json "$target" > "$results_dir/gocognit.json" 2>/dev/null || true
        cd - > /dev/null
    fi
    
    # Tier 4: gosec (security)
    if check_tool "gosec"; then
        echo "  [gosec] Running security scan..."
        cd "$target"
        gosec -fmt json -out "$results_dir/gosec.json" ./... 2>/dev/null || true
        cd - > /dev/null
    else
        echo -e "  ${YELLOW}[gosec] Not installed. Install: go install github.com/securego/gosec/v2/cmd/gosec@latest${NC}"
    fi
    
    echo -e "${GREEN}Go scanners completed.${NC}"
}

# Run Python scanners
run_python_scanners() {
    local target="$1"
    local results_dir="$2"
    
    echo -e "${YELLOW}Running Python scanners...${NC}"
    
    # Tier 1: Compile check
    if check_tool "python"; then
        echo "  [py_compile] Compiling..."
        python -m py_compile "$target"/*.py 2>"$results_dir/py-compile.json" || true
    fi
    
    # Tier 2: pylint
    if check_tool "pylint"; then
        echo "  [pylint] Running..."
        pylint --output-format=json "$target" > "$results_dir/pylint.json" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}[pylint] Not installed. Install: pip install pylint${NC}"
    fi
    
    # Tier 3: mypy
    if check_tool "mypy"; then
        echo "  [mypy] Type checking..."
        mypy --output json "$target" > "$results_dir/mypy.json" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}[mypy] Not installed. Install: pip install mypy${NC}"
    fi
    
    # Tier 2: flake8
    if check_tool "flake8"; then
        echo "  [flake8] Running..."
        flake8 --format=json "$target" > "$results_dir/flake8.json" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}[flake8] Not installed. Install: pip install flake8${NC}"
    fi
    
    # Tier 4: bandit (security)
    if check_tool "bandit"; then
        echo "  [bandit] Running security scan..."
        bandit -f json -r "$target" > "$results_dir/bandit.json" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}[bandit] Not installed. Install: pip install bandit${NC}"
    fi
    
    # Tier 2: ruff (fast linter)
    if check_tool "ruff"; then
        echo "  [ruff] Running..."
        ruff check --output-format json "$target" > "$results_dir/ruff.json" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}[ruff] Not installed. Install: pip install ruff${NC}"
    fi
    
    echo -e "${GREEN}Python scanners completed.${NC}"
}

# Run TypeScript/JavaScript scanners
run_typescript_scanners() {
    local target="$1"
    local results_dir="$2"
    
    echo -e "${YELLOW}Running TypeScript/JavaScript scanners...${NC}"
    
    # Tier 1: Type check
    if check_tool "tsc"; then
        echo "  [tsc] Type checking..."
        tsc --noEmit --pretty false > "$results_dir/tsc.json" 2>&1 || true
    elif [ -f "$target/node_modules/.bin/tsc" ]; then
        echo "  [tsc] Type checking..."
        cd "$target"
        npx tsc --noEmit --pretty false > "$results_dir/tsc.json" 2>&1 || true
        cd - > /dev/null
    else
        echo -e "  ${YELLOW}[tsc] Not installed.${NC}"
    fi
    
    # Tier 2: eslint
    if check_tool "eslint"; then
        echo "  [eslint] Running..."
        eslint --format json "$target" > "$results_dir/eslint.json" 2>/dev/null || true
    elif [ -f "$target/node_modules/.bin/eslint" ]; then
        echo "  [eslint] Running..."
        cd "$target"
        npx eslint --format json . > "$results_dir/eslint.json" 2>/dev/null || true
        cd - > /dev/null
    else
        echo -e "  ${YELLOW}[eslint] Not installed. Install: npm install -g eslint${NC}"
    fi
    
    echo -e "${GREEN}TypeScript scanners completed.${NC}"
}

# Aggregate results
aggregate_results() {
    local results_dir="$1"
    local output_file="$2"
    
    echo ""
    echo "Aggregating results..."
    
    # Create aggregated JSON
    python3 -c "
import json
import os
from pathlib import Path

results = {
    'timestamp': '$TIMESTAMP',
    'scanners': [],
    'issues': [],
    'summary': {
        'total': 0,
        'errors': 0,
        'warnings': 0,
        'info': 0
    }
}

results_dir = Path('$results_dir')

for json_file in results_dir.glob('*.json'):
    if json_file.stat().st_size == 0:
        continue
    
    tool_name = json_file.stem
    try:
        with open(json_file) as f:
            content = f.read()
            if not content.strip():
                continue
            data = json.loads(content)
            
            # Normalize format
            issues = []
            if isinstance(data, list):
                issues = data
            elif isinstance(data, dict):
                if 'issues' in data:
                    issues = data['issues']
                elif 'results' in data:
                    issues = data['results']
            
            for issue in issues:
                # Map to standard format
                normalized = {
                    'tool': tool_name,
                    'file': issue.get('file', issue.get('path', issue.get('filename', ''))),
                    'line': issue.get('line', issue.get('lineNumber', 0)),
                    'column': issue.get('column', issue.get('columnNumber', 0)),
                    'severity': issue.get('severity', issue.get('level', 'warning')).lower(),
                    'message': issue.get('message', issue.get('msg', issue.get('text', ''))),
                    'rule': issue.get('code', issue.get('rule', issue.get('check', ''))),
                }
                
                results['issues'].append(normalized)
                
                # Update summary
                results['summary']['total'] += 1
                if normalized['severity'] in ['error', 'critical']:
                    results['summary']['errors'] += 1
                elif normalized['severity'] in ['warning', 'warn']:
                    results['summary']['warnings'] += 1
                else:
                    results['summary']['info'] += 1
            
            results['scanners'].append({
                'tool': tool_name,
                'issues_found': len(issues)
            })
    except Exception as e:
        pass

with open('$output_file', 'w') as f:
    json.dump(results, f, indent=2)

print(f'Total issues: {results[\"summary\"][\"total\"]}')
print(f'  Errors: {results[\"summary\"][\"errors\"]}')
print(f'  Warnings: {results[\"summary\"][\"warnings\"]}')
print(f'  Info: {results[\"summary\"][\"info\"]}')
" || echo "Failed to aggregate results"
}

# Main
LANGUAGE=$(detect_language "$TARGET")

echo "Detected language: $LANGUAGE"
echo ""

case "$LANGUAGE" in
    go)
        run_go_scanners "$TARGET" "$OUTPUT_DIR"
        ;;
    python)
        run_python_scanners "$TARGET" "$OUTPUT_DIR"
        ;;
    kotlin)
        echo "Kotlin scanner support coming soon..."
        ;;
    typescript)
        run_typescript_scanners "$TARGET" "$OUTPUT_DIR"
        ;;
    *)
        echo -e "${RED}Error: Unknown or unsupported language.${NC}"
        exit 1
        ;;
esac

# Aggregate results
AGGREGATED_FILE="$OUTPUT_DIR/aggregated-$TIMESTAMP.json"
aggregate_results "$OUTPUT_DIR" "$AGGREGATED_FILE"

echo ""
echo "========================================"
echo "Results saved to: $AGGREGATED_FILE"
echo "========================================"