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

# ── Per-agent context slicing ────────────────────────────────────────────────────
# Entries ending with '-' are prefix patterns; others are exact rule IDs.
_AGENT_RULE_FILTER: dict[str, tuple] = {
    'safety':        ('SAFE-',),
    'data':          ('DATA-',),
    'quality':       ('QUAL-',),
    'observability': ('OBS-',),
    'naming':        ('QUAL-001', 'QUAL-008', 'QUAL-010'),  # subset of QUAL-*
    'design':        (),
    'business':      (),
}

# Top-level keys from diagnostics.json each agent needs; empty = none.
_AGENT_DIAG_KEYS: dict[str, tuple] = {
    'safety':        ('build_errors', 'gosec_issues'),
    'data':          ('vet_issues',),
    'quality':       ('vet_issues', 'staticcheck_issues'),
    'observability': (),
    'naming':        (),
    'design':        (),
    'business':      (),
}


def _filter_rule_hits_for_agent(agent: str, rule_hits_data: dict) -> dict:
    """Return rule_hits_data with only hits relevant to agent."""
    rule_filter = _AGENT_RULE_FILTER.get(agent)
    if rule_filter is None:  # unknown agent → pass through
        return rule_hits_data

    hits = rule_hits_data.get('hits', [])
    if not rule_filter:
        filtered: list = []
    else:
        def _matches(rule_id: str) -> bool:
            return any(
                rule_id.startswith(f) if f.endswith('-') else rule_id == f
                for f in rule_filter
            )
        filtered = [h for h in hits if _matches(h.get('rule_id', ''))]

    counts: dict[str, int] = {}
    for h in filtered:
        sev = h.get('severity', 'P2')
        counts[sev] = counts.get(sev, 0) + 1
    return {'hits': filtered, 'summary': {'total': len(filtered), **counts}}


def _filter_diags_for_agent(agent: str, diags_data: dict) -> dict:
    """Return diags_data with only keys relevant to agent."""
    keys = _AGENT_DIAG_KEYS.get(agent)
    if keys is None:  # unknown agent → pass through
        return diags_data
    return {k: diags_data[k] for k in keys if k in diags_data}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def ensure_session_dir(session_dir: str) -> Path:
    p = Path(session_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def run(cmd: list[str], input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_text, capture_output=True, text=True, check=check)


def is_git_repo(path: str = '.') -> bool:
    """Return True if path is inside a git repository."""
    result = subprocess.run(
        ['git', '-C', str(path), 'rev-parse', '--git-dir'],
        capture_output=True, text=True
    )
    return result.returncode == 0


def find_workspace_repos(workspace_dir: str) -> list[Path]:
    """Return immediate subdirectories of workspace_dir that contain a .git directory."""
    repos = []
    for child in sorted(Path(workspace_dir).iterdir()):
        if child.is_dir() and (child / '.git').is_dir():
            repos.append(child)
    return repos


def collect_diff_workspace(repos: list[Path], branch: str, base_branch: str, session_dir: str) -> dict:
    """Collect and merge diffs from multiple git repos in a Go workspace."""
    sd = ensure_session_dir(session_dir)
    combined_diff_parts: list[str] = []
    all_go_files: list[str] = []
    log_parts: list[str] = []

    for repo in repos:
        repo_name = repo.name

        # Determine source branch for this repo
        if branch:
            src = branch
            check = subprocess.run(
                ['git', '-C', str(repo), 'rev-parse', '--verify', src],
                capture_output=True, text=True
            )
            if check.returncode != 0:
                print(f'[workspace] {repo_name}: branch {src!r} not found, skipping', file=sys.stderr)
                continue
        else:
            src = subprocess.run(
                ['git', '-C', str(repo), 'branch', '--show-current'],
                capture_output=True, text=True
            ).stdout.strip()
            if not src:
                print(f'[workspace] {repo_name}: detached HEAD, skipping', file=sys.stderr)
                continue

        # Skip repos whose source branch equals base (nothing to diff)
        check_base = subprocess.run(
            ['git', '-C', str(repo), 'rev-parse', '--verify', base_branch],
            capture_output=True, text=True
        )
        if check_base.returncode != 0:
            print(f'[workspace] {repo_name}: base branch {base_branch!r} not found, skipping', file=sys.stderr)
            continue

        diff_result = subprocess.run(
            ['git', '-C', str(repo), 'diff', f'{base_branch}...{src}', '--diff-filter=AM'],
            capture_output=True, text=True
        )
        files_result = subprocess.run(
            ['git', '-C', str(repo), 'diff', f'{base_branch}...{src}',
             '--name-only', '--diff-filter=AM'],
            capture_output=True, text=True
        )
        log_result = subprocess.run(
            ['git', '-C', str(repo), 'log', '--oneline', '-5', f'{base_branch}..{src}'],
            capture_output=True, text=True
        )

        if diff_result.stdout:
            combined_diff_parts.append(f'# === {repo_name} (branch: {src}) ===\n')
            combined_diff_parts.append(diff_result.stdout)

        for f in files_result.stdout.splitlines():
            if f.endswith('.go'):
                all_go_files.append(f'{repo_name}/{f}')

        if log_result.stdout:
            log_parts.append(f'# {repo_name}:\n{log_result.stdout}')

        repo_go_count = len([f for f in files_result.stdout.splitlines() if f.endswith('.go')])
        print(f'[workspace] {repo_name}: src={src}, go_files={repo_go_count}')

    combined_diff = ''.join(combined_diff_parts)
    (sd / 'diff.txt').write_text(combined_diff)
    (sd / 'files.txt').write_text('\n'.join(all_go_files) + ('\n' if all_go_files else ''))
    (sd / 'gitlog.txt').write_text('\n'.join(log_parts))

    return {
        'diff_lines': len(combined_diff.splitlines()),
        'go_files_changed': len(all_go_files),
        'go_files': all_go_files,
    }


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
    """Run Tier 1 scanning. Tries `codereview scan` (Python CLI) first, falls back to run-go-tools.sh."""
    import shutil

    sd = Path(session_dir)

    # Try codereview scan (Python CLI) — preferred path
    if shutil.which('codereview'):
        try:
            scan_output_dir = sd / 'scanner-results'
            scan_output_dir.mkdir(exist_ok=True)

            project_root = subprocess.run(
                ['git', 'rev-parse', '--show-toplevel'],
                capture_output=True, text=True
            ).stdout.strip() or '.'

            subprocess.run(
                ['codereview', 'scan', project_root, '--lang', 'go',
                 '--output', str(scan_output_dir), '--no-install'],
                capture_output=True, text=True, timeout=300
            )

            aggregated_files = sorted(scan_output_dir.glob('aggregated-*.json'), reverse=True)
            if aggregated_files:
                data = json.loads(aggregated_files[0].read_text())
                issues = data.get('issues', [])
                diagnostics = {
                    'build_errors': [i for i in issues if i.get('tool') == 'go' and i.get('severity') == 'error'],
                    'vet_issues': [i for i in issues if i.get('tool') == 'go' and i.get('severity') != 'error'],
                    'staticcheck_issues': [i for i in issues if i.get('tool') == 'staticcheck'],
                    'gosec_issues': [i for i in issues if i.get('tool') == 'gosec'],
                }
                (sd / 'diagnostics.json').write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2))
                print(f'[T1] codereview scan: {len(issues)} issues (build={len(diagnostics["build_errors"])}, vet={len(diagnostics["vet_issues"])}, static={len(diagnostics["staticcheck_issues"])}, sec={len(diagnostics["gosec_issues"])})')
                return
        except Exception as e:
            print(f'[T1] codereview scan failed ({e}), falling back to run-go-tools.sh', file=sys.stderr)

    # Fallback: run-go-tools.sh
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
    sd = Path(session_dir)

    # Load scan outputs once (files may not exist yet on error paths)
    rule_hits_data: dict = {'hits': [], 'summary': {}}
    diags_data: dict = {}
    rh_path = sd / 'rule-hits.json'
    diag_path = sd / 'diagnostics.json'
    if rh_path.exists():
        try:
            rule_hits_data = json.loads(rh_path.read_text())
        except json.JSONDecodeError:
            pass
    if diag_path.exists():
        try:
            diags_data = json.loads(diag_path.read_text())
        except json.JSONDecodeError:
            pass

    tasks = []
    for agent in agent_roster:
        sliced_rh = _filter_rule_hits_for_agent(agent, rule_hits_data)
        sliced_diag = _filter_diags_for_agent(agent, diags_data)

        rh_agent_path = sd / f'rule-hits-{agent}.json'
        diag_agent_path = sd / f'diagnostics-{agent}.json'
        rh_agent_path.write_text(json.dumps(sliced_rh, ensure_ascii=False, indent=2))
        diag_agent_path.write_text(json.dumps(sliced_diag, ensure_ascii=False, indent=2))

        tasks.append({
            'agent': agent,
            'context_file': str(sd / 'context-package.md'),
            'rule_hits_file': str(rh_agent_path),
            'diagnostics_file': str(diag_agent_path),
            'output_file': str(sd / f'findings-{agent}.md'),
        })
    return tasks


# ── Phase: prepare ───────────────────────────────────────────────────────────────

def phase_prepare(args) -> int:
    base_branch = args.base

    # ── Detect Go workspace (directory is not itself a git repo) ─────────────────
    if not is_git_repo('.'):
        if not Path('go.work').exists():
            print('ERROR: not a git repo and no go.work found', file=sys.stderr)
            return 1
        repos = find_workspace_repos('.')
        if not repos:
            print('ERROR: no git repos found in Go workspace', file=sys.stderr)
            return 1
        print(f'[orchestrate] Go workspace detected ({len(repos)} repos): {", ".join(r.name for r in repos)}')

        if args.session_dir:
            session_dir = args.session_dir
        else:
            import hashlib
            heads = []
            for repo in repos:
                h = subprocess.run(
                    ['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                    capture_output=True, text=True
                ).stdout.strip()[:8]
                if h:
                    heads.append(h)
            combined_hash = hashlib.md5(''.join(heads).encode()).hexdigest()[:8]
            session_dir = f'.review/run-ws-{combined_hash}-{os.getpid()}'

        print(f'[orchestrate] session_dir={session_dir}')
        meta = collect_diff_workspace(repos, args.branch, base_branch, session_dir)

    # ── Single-repo (original) path ───────────────────────────────────────────────
    else:
        source_branch = args.branch or run(['git', 'branch', '--show-current'], check=False).stdout.strip()

        if not source_branch:
            print('ERROR: could not determine source branch', file=sys.stderr)
            return 1

        if args.session_dir:
            session_dir = args.session_dir
        else:
            head_sha = run(['git', 'rev-parse', source_branch], check=False).stdout.strip()[:8]
            session_dir = f'.review/run-{head_sha}-{os.getpid()}'

        print(f'[orchestrate] session_dir={session_dir}')
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

    # Determine loop_mode deterministically (not left to the workflow Claude agent)
    loop_mode = (tier == 'FULL' and meta['diff_lines'] >= 400) or (assemble_exit == 2)
    if loop_mode:
        print(f'[orchestrate] loop_mode=true (diff_lines={meta["diff_lines"]}, assemble_exit={assemble_exit})')

    # Write task list
    tasks = build_task_list(classification, session_dir)
    task_list = {
        'tier': tier,
        'loop_mode': loop_mode,
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

    # Coverage check: detect .go files not mentioned in any agent findings
    files_txt = sd / 'files.txt'
    if files_txt.exists():
        expected_files = [f for f in files_txt.read_text().splitlines() if f.strip()]
        if expected_files:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                'aggregate_findings', TOOLS_DIR / 'aggregate-findings.py'
            )
            agg_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(agg_mod)
            gaps = agg_mod.detect_coverage_gaps(str(sd), expected_files)
            if gaps:
                gaps_path = sd / 'coverage-gaps.json'
                gaps_path.write_text(json.dumps({'uncovered_files': gaps}, ensure_ascii=False, indent=2))
                print(f'[orchestrate] ⚠ {len(gaps)} 个文件未被任何 agent 读取：')
                for f in gaps:
                    print(f'[orchestrate]   - {f}')
                print('[orchestrate] coverage-gaps.json 已写入，可针对缺漏文件补充审查')
            else:
                print('[orchestrate] ✓ 所有变更文件均已覆盖')

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
