#!/usr/bin/env python3
"""
assemble-context.py — Go Code Review Skill v7.0.0
Assembles a Context Package from diff, git log, and rules file.

Outputs Markdown Context Package to stdout.
Outputs metadata JSON to stderr.

Usage:
  python3 assemble-context.py \
    --diff /path/to/diff.txt \
    --rules-source project_redlines \
    [--rules-file .claude/review-rules.md] \
    [--git-log /path/to/gitlog.txt] \
    [--architecture-context /path/to/architecture-context.json]
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────────

TOKEN_LIMIT = 16000
RULES_MAX_LINES = 300
CONTEXT_MAX_LINES = 200
FUNC_MAX_LINES = 80


# ── Token estimation ────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """
    Rough token estimate:
    - CJK characters: ~1.5 chars per token (each char ≈ 0.67 tokens)
    - ASCII: ~4 chars per token
    """
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f')
    ascii_count = len(text) - cjk_count
    return int(cjk_count / 1.5 + ascii_count / 4)


# ── Diff parsing ────────────────────────────────────────────────────────────────

def parse_changed_files(diff_text: str) -> dict[str, list[int]]:
    """
    Parse diff and return {filepath: [added_line_numbers]} for .go files.
    Line numbers are target (new file) line numbers.
    """
    result: dict[str, list[int]] = {}
    current_file = None
    tgt_line = 0
    hunk_re = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@')

    for line in diff_text.splitlines():
        if line.startswith('diff --git'):
            current_file = None
        elif line.startswith('+++ b/'):
            path = line[6:]
            if path.endswith('.go'):
                current_file = path
                result.setdefault(current_file, [])
            else:
                current_file = None
        elif current_file and (m := hunk_re.match(line)):
            tgt_line = int(m.group(1))
        elif current_file:
            if line.startswith('+') and not line.startswith('+++'):
                result[current_file].append(tgt_line)
                tgt_line += 1
            elif not line.startswith('-'):
                tgt_line += 1

    return result


# ── Function extraction ─────────────────────────────────────────────────────────

def _find_func_boundaries(source_lines: list[str]) -> list[tuple[int, int]]:
    """
    Return list of (start_line, end_line) tuples (1-based) for func declarations.
    Uses brace counting — handles simple cases without a full AST.
    """
    boundaries = []
    i = 0
    n = len(source_lines)
    func_re = re.compile(r'^func\s+')

    while i < n:
        line = source_lines[i]
        if func_re.match(line):
            start = i + 1  # 1-based
            brace_depth = 0
            j = i
            # Count braces to find end of function
            while j < n:
                brace_depth += source_lines[j].count('{') - source_lines[j].count('}')
                if brace_depth <= 0 and j > i:
                    boundaries.append((start, j + 1))
                    i = j + 1
                    break
                j += 1
            else:
                # Unterminated function — take to end
                boundaries.append((start, n))
                i = n
        else:
            i += 1

    return boundaries


def extract_changed_functions(filepath: str, changed_lines: list[int]) -> str:
    """
    Extract complete definitions of functions that contain changed lines.
    Falls back to signature-only if functions are too long.
    """
    try:
        source = Path(filepath).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return f'// Could not read {filepath}\n'

    source_lines = source.splitlines()
    boundaries = _find_func_boundaries(source_lines)

    changed_set = set(changed_lines)
    extracted: list[str] = []
    total_lines = 0

    for start, end in boundaries:
        # Check if any changed line falls within this function
        func_lines_range = set(range(start, end + 1))
        if not changed_set & func_lines_range:
            continue

        func_body = source_lines[start - 1:end]
        func_len = len(func_body)

        if total_lines + func_len > FUNC_MAX_LINES:
            # Only include signature
            sig = source_lines[start - 1]
            extracted.append(f'// {filepath}:{start} (signature only — function too long)\n{sig}\n')
            total_lines += 2
        else:
            extracted.append(f'// {filepath}:{start}-{end}\n' + '\n'.join(func_body) + '\n')
            total_lines += func_len + 1

        if total_lines >= FUNC_MAX_LINES * 2:
            extracted.append(f'// ... (additional functions in {filepath} omitted to stay within context limits)\n')
            break

    return '\n'.join(extracted) if extracted else f'// No changed functions found in {filepath}\n'


# ── Rules truncation ────────────────────────────────────────────────────────────

def truncate_rules(rules_text: str, changed_files: list[str]) -> tuple[str, bool]:
    """
    If rules_text exceeds RULES_MAX_LINES, keep only paragraphs/sections
    relevant to the changed files' package names and directory components.
    Returns (truncated_text, was_truncated).
    """
    lines = rules_text.splitlines()
    if len(lines) <= RULES_MAX_LINES:
        return rules_text, False

    # Extract relevant keywords from changed files
    keywords: set[str] = set()
    for f in changed_files:
        parts = Path(f).parts
        keywords.update(p.lower() for p in parts)

    # Walk sections: keep sections whose heading or content mentions keywords
    kept: list[str] = []
    current_section: list[str] = []
    section_relevant = False

    for line in lines:
        if line.startswith('#'):
            # Flush previous section
            if section_relevant and current_section:
                kept.extend(current_section)
            current_section = [line]
            section_relevant = any(kw in line.lower() for kw in keywords)
        else:
            current_section.append(line)
            if any(kw in line.lower() for kw in keywords):
                section_relevant = True

    if section_relevant and current_section:
        kept.extend(current_section)

    if not kept:
        # Fallback: take first RULES_MAX_LINES lines
        return '\n'.join(lines[:RULES_MAX_LINES]) + '\n... (truncated)', True

    result = '\n'.join(kept)
    return result, True


# ── Main assembly ───────────────────────────────────────────────────────────────

def assemble(
    diff_file: str,
    rules_source: str,
    rules_file: str | None,
    git_log_file: str | None,
    architecture_context_file: str | None,
) -> tuple[str, dict]:
    """
    Build the Context Package markdown and return (markdown, metadata).
    metadata is written to stderr as JSON.
    """
    sections_included: list[str] = []
    truncated_sections: list[str] = []

    # ── [Intent] ──
    intent_text = ''
    if git_log_file and Path(git_log_file).exists():
        intent_text = Path(git_log_file).read_text(encoding='utf-8', errors='replace').strip()
    if not intent_text:
        intent_text = '(no commit messages available)'
    sections_included.append('intent')

    # ── [Rules] ──
    rules_text = ''
    if rules_file and Path(rules_file).exists():
        raw_rules = Path(rules_file).read_text(encoding='utf-8', errors='replace')
        # We need changed_files to do keyword-based truncation, so parse diff first
        diff_text = Path(diff_file).read_text(encoding='utf-8', errors='replace') if Path(diff_file).exists() else ''
        changed_file_map = parse_changed_files(diff_text)
        changed_files = list(changed_file_map.keys())
        rules_text, rules_truncated = truncate_rules(raw_rules, changed_files)
        if rules_truncated:
            truncated_sections.append('rules')
    else:
        rules_text = f'(using {rules_source} — no local rules file found)'
    sections_included.append('rules')

    # ── [Change Set] ──
    diff_text = ''
    change_set_truncated = False
    if Path(diff_file).exists():
        diff_text = Path(diff_file).read_text(encoding='utf-8', errors='replace')
    if not diff_text:
        diff_text = '(no diff available)'
    sections_included.append('change_set')

    # ── [Context] — extract changed functions ──
    context_parts: list[str] = []
    if diff_text and diff_text != '(no diff available)':
        changed_file_map = parse_changed_files(diff_text)
        total_context_lines = 0
        for filepath, changed_lines in changed_file_map.items():
            if total_context_lines >= CONTEXT_MAX_LINES:
                context_parts.append(f'// Additional files omitted (context limit reached)\n')
                truncated_sections.append('context')
                break
            func_text = extract_changed_functions(filepath, changed_lines)
            context_parts.append(func_text)
            total_context_lines += func_text.count('\n')
    context_text = '\n'.join(context_parts) if context_parts else '(no Go source files changed)'
    sections_included.append('context')

    # ── [Architecture Context] (optional) ──
    arch_text = ''
    if architecture_context_file and Path(architecture_context_file).exists():
        try:
            arch_data = json.loads(Path(architecture_context_file).read_text())
            arch_text = arch_data.get('architecture_context', '')
        except (json.JSONDecodeError, KeyError):
            arch_text = ''
    if arch_text:
        sections_included.append('architecture_context')

    # ── Assemble markdown ──
    parts = [
        f'## [Intent]\n{intent_text}\n',
        f'## [Rules]\n{rules_text}\n',
        f'## [Change Set]\n```diff\n{diff_text}\n```\n',
        f'## [Context]\n```go\n{context_text}\n```\n',
    ]
    if arch_text:
        parts.append(f'## [Architecture Context]\n{arch_text}\n')

    markdown = '\n'.join(parts)

    # ── Token check ──
    estimated_tokens = estimate_tokens(markdown)

    # If total is way over limit, truncate Change Set as last resort
    if estimated_tokens > TOKEN_LIMIT and not change_set_truncated:
        # Trim diff to stay within budget
        available = TOKEN_LIMIT - estimate_tokens(markdown.replace(diff_text, ''))
        # Rough chars allowed for diff
        max_diff_chars = max(available * 4, 1000)
        if len(diff_text) > max_diff_chars:
            diff_text = diff_text[:max_diff_chars] + '\n... (diff truncated to fit context limit)'
            truncated_sections.append('change_set')
            # Rebuild
            parts[2] = f'## [Change Set]\n```diff\n{diff_text}\n```\n'
            markdown = '\n'.join(parts)
            estimated_tokens = estimate_tokens(markdown)

    metadata = {
        'estimated_tokens': estimated_tokens,
        'token_limit': TOKEN_LIMIT,
        'sections_included': sections_included,
        'truncated_sections': truncated_sections,
    }

    return markdown, metadata


# ── CLI ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Assemble Context Package for Go code review')
    parser.add_argument('--diff', required=True, help='Path to diff file')
    parser.add_argument('--rules-source', default='built_in',
                        help='Rules source type (project_redlines|project_rules|built_in)')
    parser.add_argument('--rules-file', default='', help='Path to rules file')
    parser.add_argument('--git-log', default='', help='Path to git log file')
    parser.add_argument('--architecture-context', default='',
                        help='Path to architecture-context.json from scan-architecture.py')
    args = parser.parse_args()

    markdown, metadata = assemble(
        diff_file=args.diff,
        rules_source=args.rules_source,
        rules_file=args.rules_file or None,
        git_log_file=args.git_log or None,
        architecture_context_file=args.architecture_context or None,
    )

    # Stdout: Context Package markdown
    sys.stdout.write(markdown)

    # Stderr: metadata JSON
    print(json.dumps(metadata, ensure_ascii=False), file=sys.stderr)

    # Exit with warning code if change_set was truncated
    if 'change_set' in metadata['truncated_sections']:
        print('TRUNCATION_WARNING: change_set', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
