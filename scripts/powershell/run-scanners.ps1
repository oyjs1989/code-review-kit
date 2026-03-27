# Code Review Kit - Scanner Runner (PowerShell)
# Runs integrated code scanning tools based on detected language

param(
    [string]$Target = ".",
    [string]$OutputDir = ".review\scanner-results"
)

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"

# Colors
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-Output "========================================"
Write-Output "  Code Review Kit - Scanner Runner"
Write-Output "========================================"
Write-Output ""

# Create output directory
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Detect language
function Detect-Language {
    param($dir)
    
    if (Test-Path "$dir\go.mod") {
        return "go"
    }
    elseif (Test-Path "$dir\requirements.txt" -or Test-Path "$dir\pyproject.toml" -or Test-Path "$dir\setup.py") {
        return "python"
    }
    elseif (Test-Path "$dir\build.gradle.kts" -or Test-Path "$dir\build.gradle") {
        return "kotlin"
    }
    elseif (Test-Path "$dir\package.json" -or Test-Path "$dir\tsconfig.json") {
        return "typescript"
    }
    else {
        # Check file extensions
        $goCount = (Get-ChildItem -Path $dir -Filter "*.go" -Recurse -ErrorAction SilentlyContinue).Count
        $pyCount = (Get-ChildItem -Path $dir -Filter "*.py" -Recurse -ErrorAction SilentlyContinue).Count
        $ktCount = (Get-ChildItem -Path $dir -Filter "*.kt" -Recurse -ErrorAction SilentlyContinue).Count
        $tsCount = (Get-ChildItem -Path $dir -Include "*.ts","*.tsx" -Recurse -ErrorAction SilentlyContinue).Count
        
        if ($goCount -gt $pyCount -and $goCount -gt $ktCount -and $goCount -gt $tsCount) {
            return "go"
        }
        elseif ($pyCount -gt 0) {
            return "python"
        }
        elseif ($ktCount -gt 0) {
            return "kotlin"
        }
        elseif ($tsCount -gt 0) {
            return "typescript"
        }
        else {
            return "unknown"
        }
    }
}

# Check if command exists
function Test-Command {
    param($command)
    $null -ne (Get-Command $command -ErrorAction SilentlyContinue)
}

# Run Go scanners
function Run-GoScanners {
    param($target, $resultsDir)
    
    Write-ColorOutput Yellow "Running Go scanners..."
    
    # Tier 1: Build check
    if (Test-Command "go") {
        Write-Output "  [go build] Compiling..."
        Push-Location $target
        go build ./... 2>&1 | Out-File "$resultsDir\go-build.json" -Encoding utf8
        Pop-Location
    }
    
    # Tier 2: go vet
    if (Test-Command "go") {
        Write-Output "  [go vet] Running..."
        Push-Location $target
        go vet ./... 2>&1 | Out-File "$resultsDir\go-vet.json" -Encoding utf8
        Pop-Location
    }
    
    # Tier 3: staticcheck
    if (Test-Command "staticcheck") {
        Write-Output "  [staticcheck] Running..."
        Push-Location $target
        staticcheck -f json ./... 2>&1 | Out-File "$resultsDir\staticcheck.json" -Encoding utf8
        Pop-Location
    }
    else {
        Write-ColorOutput Yellow "  [staticcheck] Not installed. Install: go install honnef.co/go/tools/cmd/staticcheck@latest"
    }
    
    # Tier 4: gosec (security)
    if (Test-Command "gosec") {
        Write-Output "  [gosec] Running security scan..."
        Push-Location $target
        gosec -fmt json -out "$resultsDir\gosec.json" ./... 2>&1
        Pop-Location
    }
    else {
        Write-ColorOutput Yellow "  [gosec] Not installed. Install: go install github.com/securego/gosec/v2/cmd/gosec@latest"
    }
    
    Write-ColorOutput Green "Go scanners completed."
}

# Run Python scanners
function Run-PythonScanners {
    param($target, $resultsDir)
    
    Write-ColorOutput Yellow "Running Python scanners..."
    
    # Tier 2: pylint
    if (Test-Command "pylint") {
        Write-Output "  [pylint] Running..."
        pylint --output-format=json $target 2>&1 | Out-File "$resultsDir\pylint.json" -Encoding utf8
    }
    else {
        Write-ColorOutput Yellow "  [pylint] Not installed. Install: pip install pylint"
    }
    
    # Tier 3: mypy
    if (Test-Command "mypy") {
        Write-Output "  [mypy] Type checking..."
        mypy --output json $target 2>&1 | Out-File "$resultsDir\mypy.json" -Encoding utf8
    }
    else {
        Write-ColorOutput Yellow "  [mypy] Not installed. Install: pip install mypy"
    }
    
    # Tier 2: flake8
    if (Test-Command "flake8") {
        Write-Output "  [flake8] Running..."
        flake8 --format=json $target 2>&1 | Out-File "$resultsDir\flake8.json" -Encoding utf8
    }
    else {
        Write-ColorOutput Yellow "  [flake8] Not installed. Install: pip install flake8"
    }
    
    # Tier 4: bandit (security)
    if (Test-Command "bandit") {
        Write-Output "  [bandit] Running security scan..."
        bandit -f json -r $target 2>&1 | Out-File "$resultsDir\bandit.json" -Encoding utf8
    }
    else {
        Write-ColorOutput Yellow "  [bandit] Not installed. Install: pip install bandit"
    }
    
    # Tier 2: ruff (fast linter)
    if (Test-Command "ruff") {
        Write-Output "  [ruff] Running..."
        ruff check --output-format json $target 2>&1 | Out-File "$resultsDir\ruff.json" -Encoding utf8
    }
    else {
        Write-ColorOutput Yellow "  [ruff] Not installed. Install: pip install ruff"
    }
    
    Write-ColorOutput Green "Python scanners completed."
}

# Run TypeScript/JavaScript scanners
function Run-TypeScriptScanners {
    param($target, $resultsDir)
    
    Write-ColorOutput Yellow "Running TypeScript/JavaScript scanners..."
    
    # Tier 1: Type check
    if (Test-Command "tsc") {
        Write-Output "  [tsc] Type checking..."
        tsc --noEmit --pretty false 2>&1 | Out-File "$resultsDir\tsc.json" -Encoding utf8
    }
    elseif (Test-Path "$target\node_modules\.bin\tsc") {
        Write-Output "  [tsc] Type checking..."
        Push-Location $target
        npx tsc --noEmit --pretty false 2>&1 | Out-File "$resultsDir\tsc.json" -Encoding utf8
        Pop-Location
    }
    else {
        Write-ColorOutput Yellow "  [tsc] Not installed."
    }
    
    # Tier 2: eslint
    if (Test-Command "eslint") {
        Write-Output "  [eslint] Running..."
        eslint --format json $target 2>&1 | Out-File "$resultsDir\eslint.json" -Encoding utf8
    }
    elseif (Test-Path "$target\node_modules\.bin\eslint") {
        Write-Output "  [eslint] Running..."
        Push-Location $target
        npx eslint --format json . 2>&1 | Out-File "$resultsDir\eslint.json" -Encoding utf8
        Pop-Location
    }
    else {
        Write-ColorOutput Yellow "  [eslint] Not installed. Install: npm install -g eslint"
    }
    
    Write-ColorOutput Green "TypeScript scanners completed."
}

# Aggregate results
function Aggregate-Results {
    param($resultsDir, $outputFile)
    
    Write-Output ""
    Write-Output "Aggregating results..."
    
    # Use Python to aggregate (if available)
    if (Test-Command "python") {
        python -c @"
import json
import os
from pathlib import Path

results = {
    'timestamp': '$Timestamp',
    'scanners': [],
    'issues': [],
    'summary': {
        'total': 0,
        'errors': 0,
        'warnings': 0,
        'info': 0
    }
}

results_dir = Path(r'$resultsDir')

for json_file in results_dir.glob('*.json'):
    if json_file.stat().st_size == 0:
        continue
    
    tool_name = json_file.stem
    try:
        with open(json_file, encoding='utf-8') as f:
            content = f.read()
            if not content.strip():
                continue
            data = json.loads(content)
            
            issues = []
            if isinstance(data, list):
                issues = data
            elif isinstance(data, dict):
                if 'issues' in data:
                    issues = data['issues']
                elif 'Results' in data:
                    issues = data['Results']
            
            for issue in issues:
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

with open(r'$outputFile', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)

print(f'Total issues: {results["summary"]["total"]}')
print(f'  Errors: {results["summary"]["errors"]}')
print(f'  Warnings: {results["summary"]["warnings"]}')
print(f'  Info: {results["summary"]["info"]}')
"@
    }
    else {
        Write-ColorOutput Yellow "Python not available, skipping aggregation"
    }
}

# Main
$Language = Detect-Language $Target

Write-Output "Detected language: $Language"
Write-Output ""

switch ($Language) {
    "go" {
        Run-GoScanners $Target $OutputDir
    }
    "python" {
        Run-PythonScanners $Target $OutputDir
    }
    "kotlin" {
        Write-Output "Kotlin scanner support coming soon..."
    }
    "typescript" {
        Run-TypeScriptScanners $Target $OutputDir
    }
    default {
        Write-ColorOutput Red "Error: Unknown or unsupported language."
        exit 1
    }
}

# Aggregate results
$AggregatedFile = "$OutputDir\aggregated-$Timestamp.json"
Aggregate-Results $OutputDir $AggregatedFile

Write-Output ""
Write-Output "========================================"
Write-Output "Results saved to: $AggregatedFile"
Write-Output "========================================"
