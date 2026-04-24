#!/usr/bin/env python3
"""
orchestrate-review.py — Go Code Review Skill v8.0.0
Deterministic orchestrator for all non-AI workflow steps.

Usage:
  python3 orchestrate-review.py --mode prepare \
    [--branch feat/xxx] [--base main] [--session-dir .review/run-abc-1234]

  python3 orchestrate-review.py --mode aggregate \
    --session-dir .review/run-abc-1234 [--output report.md]

Exit codes:
  0 = success
  1 = fatal error
  2 = TRIVIAL tier (no review needed)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).parent


# ── Helpers ─────────────────────────────────────────────────────────────────────

def ensure_session_dir(session_dir: str) -> Path:
    p = Path(session_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def run(cmd: list[str], input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_text, capture_output=True, text=True, check=check)


# ── Step 1: Collect diff ─────────────────────────────────────────────────────────

def collect_diff(source_branch: str, base_branch: str, session_dir: str) -> dict:
    """Collect git diff and file list. Returns metadata dict."""
    sd = ensure_session_dir(session_dir)

    diff_result = run(['git', 'diff', f'{base_branch}...{source_branch}', '--diff-filter=AM'], check=False)
    (sd / 'diff.txt').write_text(diff_result.stdout)

    files_result = run(['git', 'diff', f'{base_branch}...{source_branch}',
                        '--name-only', '--diff-filter=AM'], check=False)
    go_files = [f for f in files_result.stdout.splitlines() if f.endswith('.go')]
    (sd / 'files.txt').write_text('\n'.join(go_files) + ('\n' if go_files else ''))

    log_result = run(['git', 'log', '--oneline', '-5', f'{base_branch}..{source_branch}'], check=False)
    (sd / 'gitlog.txt').write_text(log_result.stdout)

    diff_lines = len(diff_result.stdout.splitlines())
    return {'diff_lines': diff_lines, 'go_files_changed': len(go_files), 'go_files': go_files}


# ── Step 2: Triage ───────────────────────────────────────────────────────────────

def triage(diff_lines: int, files_changed: int, session_dir: str) -> dict:
    """Classify diff tier via classify-diff.py. Returns classification dict."""
    sd = Path(session_dir)
    files_txt = (sd / 'files.txt').read_text().strip()
    files_str = ' '.join(files_txt.splitlines()) if files_txt else ''

    result = run([
        'python3', str(TOOLS_DIR / 'classify-diff.py'),
        '--diff-lines', str(diff_lines),
        '--files-changed', str(files_changed),
        '--files', files_str,
        '--diff-file', str(sd / 'diff.txt'),
    ])
    classification = json.loads(result.stdout)
    (sd / 'classification.json').write_text(json.dumps(classification, ensure_ascii=False, indent=2))
    return classification


# ── Step 3: Assemble context ─────────────────────────────────────────────────────

def assemble_context(classification: dict, session_dir: str) -> int:
    """Assemble context package. Returns assemble-context.py exit code."""
    sd = Path(session_dir)
    rules_file = classification.get('rules_file', '')
    rules_source = classification.get('rules_source', 'built_in')

    cmd = [
        'python3', str(TOOLS_DIR / 'assemble-context.py'),
        '--diff', str(sd / 'diff.txt'),
        '--rules-source', rules_source,
        '--git-log', str(sd / 'gitlog.txt'),
    ]
    if rules_file:
        cmd += ['--rules-file', rules_file]

    result = subprocess.run(cmd, capture_output=True, text=True)
    (sd / 'context-package.md').write_text(result.stdout)

    # stderr first line is JSON metadata
    stderr_lines = result.stderr.splitlines()
    meta_line = next((l for l in stderr_lines if l.startswith('{')), '{}')
    (sd / 'context-meta.json').write_text(meta_line)

    return result.returncode


# ── Step 3.5: Architecture scan (FULL only) ──────────────────────────────────────

def run_architecture_scan(go_files: list[str], session_dir: str) -> bool:
    """Architecture pre-scan. Returns True on success."""
    sd = Path(session_dir)
    if not go_files:
        return False

    files_str = ' '.join(go_files)
    try:
        result = subprocess.run(
            ['python3', str(TOOLS_DIR / 'scan-architecture.py'), '--files', files_str],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            (sd / 'architecture-context.json').write_text(result.stdout)
            return True
    except subprocess.TimeoutExpired:
        print('[orchestrate] architecture scan timed out, skipping', file=sys.stderr)
    return False


# ── Step 4 Tier 1: Go tools ──────────────────────────────────────────────────────

def run_tier1(go_files: list[str], session_dir: str) -> None:
    """Run go build/vet/staticcheck via run-go-tools.sh."""
    sd = Path(session_dir)
    files_input = '\n'.join(go_files)
    result = subprocess.run(
        ['bash', str(TOOLS_DIR / 'run-go-tools.sh')],
        input=files_input, capture_output=True, text=True
    )
    (sd / 'diagnostics.json').write_text(result.stdout or '{}')


# ── Step 4 Tier 2: Rule scan ─────────────────────────────────────────────────────

def run_tier2(go_files: list[str], session_dir: str) -> None:
    """Scan YAML rules via scan-rules.sh."""
    sd = Path(session_dir)
    files_input = '\n'.join(go_files)
    result = subprocess.run(
        ['bash', str(TOOLS_DIR / 'scan-rules.sh')],
        input=files_input, capture_output=True, text=True
    )
    (sd / 'rule-hits.json').write_text(result.stdout or '{"hits":[],"summary":{}}')


# ── Task list builder ────────────────────────────────────────────────────────────

def build_task_list(classification: dict, session_dir: str) -> list[dict]:
    """Build the list of AI agent tasks from classification."""
    agent_roster = classification.get('agent_roster', [])
    tasks = []
    for agent in agent_roster:
        tasks.append({
            'agent': agent,
            'context_file': str(Path(session_dir) / 'context-package.md'),
            'rule_hits_file': str(Path(session_dir) / 'rule-hits.json'),
            'diagnostics_file': str(Path(session_dir) / 'diagnostics.json'),
            'output_file': str(Path(session_dir) / f'findings-{agent}.md'),
        })
    return tasks


# ── Phase: prepare ───────────────────────────────────────────────────────────────

def phase_prepare(args) -> int:
    source_branch = args.branch or run(['git', 'branch', '--show-current'], check=False).stdout.strip()
    base_branch = args.base

    if not source_branch:
        print('ERROR: could not determine source branch', file=sys.stderr)
        return 1

    # Resolve session dir
    if args.session_dir:
        session_dir = args.session_dir
    else:
        head_sha = run(['git', 'rev-parse', source_branch], check=False).stdout.strip()[:8]
        session_dir = f'.review/run-{head_sha}-{os.getpid()}'

    print(f'[orchestrate] session_dir={session_dir}')

    # Step 1: Collect diff
    meta = collect_diff(source_branch, base_branch, session_dir)
    print(f'[1/3] diff={meta["diff_lines"]} lines, go_files={meta["go_files_changed"]}')

    if meta['diff_lines'] == 0 and meta['go_files_changed'] == 0:
        print('ERROR: diff is empty', file=sys.stderr)
        return 1

    if not meta['go_files']:
        print('ERROR: no Go files changed', file=sys.stderr)
        return 1

    # Step 2: Triage
    classification = triage(meta['diff_lines'], meta['go_files_changed'], session_dir)
    tier = classification['tier']
    print(f'[2/3] tier={tier} ({classification.get("trigger_reason", "")})')

    if tier == 'TRIVIAL':
        print('TRIVIAL: 变更为文档/配置类，无需审查')
        return 2

    # Step 3: Assemble context
    assemble_exit = assemble_context(classification, session_dir)
    if assemble_exit == 2:
        print('[3/3] WARNING: context truncated (change_set exceeds token limit)')
    print(f'[3/3] context package assembled (exit={assemble_exit})')

    # Step 3.5: Architecture scan (FULL only)
    if tier == 'FULL':
        ok = run_architecture_scan(meta['go_files'], session_dir)
        print(f'[3.5/3] architecture scan: {"ok" if ok else "skipped"}')

    # Step 4: Tier 1 + Tier 2
    run_tier1(meta['go_files'], session_dir)
    print('[T1] go tools complete')
    run_tier2(meta['go_files'], session_dir)
    print('[T2] rule scan complete')

    # Write task list
    tasks = build_task_list(classification, session_dir)
    task_list = {
        'tier': tier,
        'session_dir': session_dir,
        'tasks': tasks,
        'status': 'ready',
    }
    Path(session_dir, 'task-list.json').write_text(json.dumps(task_list, ensure_ascii=False, indent=2))
    print(f'[orchestrate] task-list.json written ({len(tasks)} agents)')
    print(f'[orchestrate] session_dir: {session_dir}')
    # Write session dir to a stable path for workflow scripts to read
    Path('.review/last-session-dir').write_text(session_dir)
    return 0


# ── Phase: aggregate ─────────────────────────────────────────────────────────────

def phase_aggregate(args) -> int:
    from datetime import datetime

    sd = Path(args.session_dir)
    if not sd.exists():
        print(f'ERROR: session_dir not found: {args.session_dir}', file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    output_file = args.output or f'.review/results/review-{timestamp}.md'
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        'python3', str(TOOLS_DIR / 'aggregate-findings.py'),
        '--findings-dir', str(sd),
        '--max-output', '15',
        '--output', output_file,
    ]
    for flag, path in [
        ('--classification-file', sd / 'classification.json'),
        ('--context-meta-file', sd / 'context-meta.json'),
        ('--rule-hits-file', sd / 'rule-hits.json'),
    ]:
        if path.exists():
            cmd += [flag, str(path)]

    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        print('ERROR: aggregate-findings.py failed', file=sys.stderr)
        return 1

    print(f'[orchestrate] report: {output_file}')
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Orchestrate deterministic Go review steps')
    parser.add_argument('--mode', required=True, choices=['prepare', 'aggregate'])
    parser.add_argument('--branch', default='', help='Source branch (default: current branch)')
    parser.add_argument('--base', default='main', help='Base branch (default: main)')
    parser.add_argument('--session-dir', default='', help='Session directory path')
    parser.add_argument('--output', default='', help='Output report path (aggregate mode)')
    parser.add_argument('--resume', action='store_true', help='Resume interrupted review')
    return parser.parse_args()


def main():
    args = parse_args()
    if args.mode == 'prepare':
        sys.exit(phase_prepare(args))
    else:
        sys.exit(phase_aggregate(args))


if __name__ == '__main__':
    main()
