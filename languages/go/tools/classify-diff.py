#!/usr/bin/env python3
"""
classify-diff.py — Go Code Review Skill v7.0.0
Classifies a diff into TRIVIAL / LITE / FULL tier and outputs routing JSON.
Also supports --generate-task-packs mode for Loop-mode task decomposition.

Usage:
  python3 classify-diff.py --diff-lines N --files-changed N --files "a.go b.go" [--diff-file path]
  python3 classify-diff.py --generate-task-packs --diff-file path --agent-roster "safety quality ..."
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────────

SENSITIVE_PATH_RE = re.compile(r'(auth|crypto|payment|permission|admin)/')

DOC_EXTENSIONS = {'.md', '.txt', '.rst'}
CONFIG_EXTENSIONS = {'.yml', '.yaml', '.toml', '.json', '.ini'}
# .env.example treated as config
CONFIG_NAMES = {'.env.example'}

LITE_AGENTS = ['safety', 'quality', 'observability']
FULL_AGENTS = ['safety', 'data', 'design', 'quality', 'observability', 'business', 'naming']

TASK_PACK_MAX_LINES = 150
TASK_PACK_MAX_PACKS = 20


# ── Rules-source detection ──────────────────────────────────────────────────────

def detect_rules_source():
    """Walk up from cwd looking for project rule files. Returns (source, file, has_redlines)."""
    # Priority 1: project redlines
    if Path('.claude/review-rules.md').exists():
        return 'project_redlines', '.claude/review-rules.md', True

    # Priority 2: general project rules
    for candidate in ['AGENTS.md', 'CLAUDE.md']:
        if Path(candidate).exists():
            return 'project_rules', candidate, False

    # Priority 3: docs/ style/rule/convention files
    if Path('docs').is_dir():
        for p in Path('docs').rglob('*.md'):
            name = p.name.lower()
            if any(kw in name for kw in ('style', 'rule', 'convention')):
                return 'project_rules', str(p), False

    return 'built_in', '', False


# ── Trivial detection helpers ───────────────────────────────────────────────────

def _is_doc_or_config(filepath: str) -> bool:
    p = Path(filepath)
    if p.name in CONFIG_NAMES:
        return True
    return p.suffix.lower() in DOC_EXTENSIONS | CONFIG_EXTENSIONS


def _has_only_comment_changes(diff_text: str) -> bool:
    """
    Return True if all added lines in .go files are comments or blank.
    Comment patterns: lines starting with // or /* or * (inside block comment).
    """
    in_go_section = False
    non_comment_adds = 0

    for line in diff_text.splitlines():
        # Track which file we're in
        if line.startswith('diff --git'):
            # Check if it's a .go file
            in_go_section = line.endswith('.go') or '.go ' in line
            continue
        if not in_go_section:
            continue
        # Added lines only (skip +++ header)
        if line.startswith('+') and not line.startswith('+++'):
            content = line[1:].strip()
            # Empty line is fine
            if not content:
                continue
            # Comment lines
            if content.startswith('//') or content.startswith('/*') or content.startswith('*'):
                continue
            non_comment_adds += 1

    return non_comment_adds == 0


def _is_trivial(diff_lines: int, files: list[str], diff_text: str | None) -> tuple[bool, str]:
    """Return (is_trivial, reason)."""
    if diff_lines >= 20:
        return False, f'diff_lines={diff_lines} >= 20'

    all_non_code = all(_is_doc_or_config(f) for f in files)
    if all_non_code:
        return True, f'diff_lines={diff_lines} < 20, all files are docs/config'

    # Check if .go files only have comment changes
    if diff_text is not None and _has_only_comment_changes(diff_text):
        return True, f'diff_lines={diff_lines} < 20, Go changes are comments-only'

    return False, f'diff_lines={diff_lines} < 20 but has code changes'


def _touches_sensitive(files: list[str]) -> tuple[bool, str]:
    for f in files:
        if SENSITIVE_PATH_RE.search(f):
            return True, f'sensitive path: {f}'
    return False, ''


# ── Triage ──────────────────────────────────────────────────────────────────────

def classify(diff_lines: int, files_changed: int, files: list[str], diff_text: str | None):
    rules_source, rules_file, has_redlines = detect_rules_source()

    # Step 1: Trivial?
    is_trivial, trivial_reason = _is_trivial(diff_lines, files, diff_text)
    if is_trivial:
        return {
            'tier': 'TRIVIAL',
            'trigger_reason': trivial_reason,
            'agent_roster': [],
            'rules_source': rules_source,
            'rules_file': rules_file,
            'has_redlines': has_redlines,
        }

    # Step 2: Full conditions
    full_reasons = []
    if diff_lines >= 400:
        full_reasons.append(f'diff_lines={diff_lines}')
    if files_changed >= 5:
        full_reasons.append(f'files_changed={files_changed}')
    sensitive, sensitive_reason = _touches_sensitive(files)
    if sensitive:
        full_reasons.append(sensitive_reason)

    if full_reasons:
        return {
            'tier': 'FULL',
            'trigger_reason': ', '.join(full_reasons),
            'agent_roster': FULL_AGENTS,
            'rules_source': rules_source,
            'rules_file': rules_file,
            'has_redlines': has_redlines,
        }

    # Step 3: Lite
    return {
        'tier': 'LITE',
        'trigger_reason': f'diff_lines={diff_lines}, files_changed={files_changed}',
        'agent_roster': LITE_AGENTS,
        'rules_source': rules_source,
        'rules_file': rules_file,
        'has_redlines': has_redlines,
    }


# ── Task pack generation (Loop mode) ────────────────────────────────────────────

def _parse_diff_files(diff_text: str) -> dict[str, list[str]]:
    """Parse diff into {filepath: [diff_lines]} mapping."""
    files: dict[str, list[str]] = {}
    current_file = None
    for line in diff_text.splitlines():
        if line.startswith('diff --git'):
            current_file = None
        elif line.startswith('+++ b/'):
            current_file = line[6:]
            if current_file not in files:
                files[current_file] = []
        elif current_file is not None:
            files[current_file].append(line)
    return files


def generate_task_packs(diff_file: str, agent_roster: list[str]) -> dict:
    """
    Decompose a large diff into task packs for Loop mode.
    Strategy: group files by directory, split packs that exceed TASK_PACK_MAX_LINES.
    Each task has task_id = "task-{pack_index}:{agent}".
    """
    diff_text = Path(diff_file).read_text(encoding='utf-8', errors='replace')
    file_diffs = _parse_diff_files(diff_text)

    # Group by directory
    dir_groups: dict[str, list[str]] = {}
    for filepath in file_diffs:
        if not filepath.endswith('.go'):
            continue
        directory = str(Path(filepath).parent)
        dir_groups.setdefault(directory, []).append(filepath)

    # Build packs: each dir group may be split if too many lines
    packs: list[dict] = []
    pack_index = 1

    for directory, dir_files in sorted(dir_groups.items()):
        # Calculate total lines for this directory group
        total_lines = sum(len(file_diffs.get(f, [])) for f in dir_files)

        if total_lines <= TASK_PACK_MAX_LINES:
            # Entire directory fits in one pack
            packs.append({
                'pack_index': pack_index,
                'files': dir_files,
                'directory': directory,
                'diff_lines': total_lines,
            })
            pack_index += 1
        else:
            # Split into sub-packs by individual files
            current_pack_files: list[str] = []
            current_pack_lines = 0

            for f in dir_files:
                file_lines = len(file_diffs.get(f, []))
                if current_pack_files and current_pack_lines + file_lines > TASK_PACK_MAX_LINES:
                    packs.append({
                        'pack_index': pack_index,
                        'files': current_pack_files,
                        'directory': directory,
                        'diff_lines': current_pack_lines,
                    })
                    pack_index += 1
                    current_pack_files = []
                    current_pack_lines = 0
                current_pack_files.append(f)
                current_pack_lines += file_lines

            if current_pack_files:
                packs.append({
                    'pack_index': pack_index,
                    'files': current_pack_files,
                    'directory': directory,
                    'diff_lines': current_pack_lines,
                })
                pack_index += 1

    # Enforce max pack limit by merging the smallest packs
    while len(packs) > TASK_PACK_MAX_PACKS:
        # Merge last two packs
        last = packs.pop()
        second_last = packs.pop()
        merged = {
            'pack_index': second_last['pack_index'],
            'files': second_last['files'] + last['files'],
            'directory': second_last['directory'],
            'diff_lines': second_last['diff_lines'] + last['diff_lines'],
        }
        packs.append(merged)

    # Expand packs × agents into tasks
    tasks = []
    for pack in packs:
        for agent in agent_roster:
            tasks.append({
                'task_id': f"task-{pack['pack_index']}:{agent}",
                'pack_index': pack['pack_index'],
                'agent': agent,
                'files': pack['files'],
                'directory': pack['directory'],
                'diff_lines': pack['diff_lines'],
            })

    return {
        'total_packs': len(packs),
        'total_tasks': len(tasks),
        'packs': packs,
        'tasks': tasks,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Classify diff tier for Go code review')
    parser.add_argument('--diff-lines', type=int, default=0)
    parser.add_argument('--files-changed', type=int, default=0)
    parser.add_argument('--files', type=str, default='',
                        help='Space-separated list of changed files')
    parser.add_argument('--diff-file', type=str, default='',
                        help='Path to diff file (for comment-only detection and task pack generation)')
    parser.add_argument('--generate-task-packs', action='store_true',
                        help='Generate Loop mode task packs from diff file')
    parser.add_argument('--agent-roster', type=str, default='',
                        help='Space-separated agent list for --generate-task-packs')
    args = parser.parse_args()

    # Task pack generation mode
    if args.generate_task_packs:
        if not args.diff_file:
            print('ERROR: --generate-task-packs requires --diff-file', file=sys.stderr)
            sys.exit(1)
        agents = args.agent_roster.split() if args.agent_roster else FULL_AGENTS
        result = generate_task_packs(args.diff_file, agents)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Standard triage mode
    files = [f for f in args.files.split() if f] if args.files else []

    diff_text = None
    if args.diff_file and Path(args.diff_file).exists():
        diff_text = Path(args.diff_file).read_text(encoding='utf-8', errors='replace')

    result = classify(args.diff_lines, args.files_changed, files, diff_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
