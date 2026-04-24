#!/usr/bin/env python3
"""
aggregate-findings.py — Go Code Review Skill v7.0.0
Reads agent findings files, deduplicates, filters, sorts, and outputs
the final Markdown review report.

Usage:
  python3 aggregate-findings.py \
    --findings-dir .review/run-abc123-1234 \
    [--redlines-file .claude/review-rules.md] \
    [--review-ignore-flags "security:src/auth.go:45,quality"] \
    [--max-output 15] \
    --output .review/results/review-20240101-120000.md

  # Lint JSON conversion mode:
  python3 aggregate-findings.py \
    --lint-json lint-results.json \
    --output findings-lint.md
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────────

SEVERITY_ORDER = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}

SEVERITY_LABELS = {
    'P0': 'P0（必须修复）',
    'P1': 'P1（强烈建议）',
    'P2': 'P2（建议优化）',
    'P3': 'P3（参考信息）',
}

# Category → rule prefix mapping for review:ignore
CATEGORY_PREFIX_MAP = {
    'security': ['SAFE-'],
    'data': ['DATA-'],
    'quality': ['QUAL-'],
    'style': ['QUAL-'],
    'architecture': ['ARCH-'],
    'performance': ['PERF-'],
    'observability': ['OBS-'],
    'business': ['BIZ-'],
    'naming': ['QUAL-'],
    'lint': ['LINT-'],
}

# Linter → (rule_id, default_severity) mapping for golangci-lint JSON
LINTER_SEVERITY_MAP = {
    'errcheck':    ('LINT-001', 'P1'),
    'govet':       ('LINT-002', 'P0'),
    'staticcheck': ('LINT-003', 'P1'),
    'ineffassign': ('LINT-004', 'P2'),
    'unused':      ('LINT-005', 'P1'),
    'gosec':       ('LINT-006', 'P0'),
    'gocognit':    ('LINT-007', 'P2'),
    'misspell':    ('LINT-008', 'P2'),
}
DEFAULT_LINT_RULE = ('LINT-000', 'P2')

ADJACENT_LINE_THRESHOLD = 3
MIN_CONFIDENCE = 0.75
FUZZY_THRESHOLD = 0.85
MAX_FUZZY_PER_CATEGORY = 3


# ── Finding data structure ──────────────────────────────────────────────────────

class Finding:
    """Represents a single review finding."""

    def __init__(self, rule_id, severity, filepath, line_start, line_end=None,
                 body='', confidence=1.0, needs_clarification=None, source_agent=''):
        self.rule_id = rule_id
        self.severity = severity
        self.filepath = filepath
        self.line_start = line_start
        self.line_end = line_end if line_end and line_end != line_start else line_start
        self.body = body
        self.confidence = confidence
        self.needs_clarification = needs_clarification
        self.source_agent = source_agent
        self.is_redline = False

    @property
    def category(self) -> str:
        """Extract category prefix from rule_id (e.g., 'SAFE' from 'SAFE-003')."""
        m = re.match(r'^([A-Z]+)-', self.rule_id)
        return m.group(1) if m else self.rule_id

    @property
    def sort_key(self):
        return (SEVERITY_ORDER.get(self.severity, 99), -self.confidence, self.filepath, self.line_start)

    def to_markdown(self) -> str:
        location = f'{self.filepath}:{self.line_start}'
        if self.line_end and self.line_end != self.line_start:
            location += f'-{self.line_end}'
        header = f'### [{self.severity}] {self.rule_id} · {location}'

        lines = [header]
        if self.source_agent:
            lines.append(f'**来源**: {self.source_agent}')
        lines.append(f'**置信度**: {self.confidence:.2f}')
        if self.needs_clarification:
            lines.append(f'**needs_clarification**: {self.needs_clarification}')
        if self.is_redline:
            lines.append('**redline**: true')
        lines.append('')
        if self.body.strip():
            lines.append(self.body.strip())
        return '\n'.join(lines)


# ── Finding parser ──────────────────────────────────────────────────────────────

# Matches: ### [P0] SAFE-003 · src/auth.go:42-47
FINDING_HEADER_RE = re.compile(
    r'^###\s+\[([P][0-3])\]\s+([A-Z]+-\d+)\s+[·•]\s+(.+?):(\d+)(?:-(\d+))?'
)
# Matches: **confidence**: 0.98  or  **confidence:** 0.98  or  **置信度**: 0.98
CONFIDENCE_RE = re.compile(r'^\*\*(?:confidence|置信度):?\*\*\s*:?\s*([0-9.]+)')
SOURCE_RE = re.compile(r'^\*\*(?:来源|source):?\*\*\s*:?\s*(.+)')
REDLINE_RE = re.compile(r'^\*\*redline:?\*\*\s*:?\s*')
# Matches: **needs_clarification**: ...
NC_RE = re.compile(r'^\*\*needs_clarification:?\*\*\s*:?\s*(.+)')
# Matches: **位置**: path/to/file.go:42  (legacy format)
LOCATION_RE = re.compile(r'^\*\*位置:?\*\*\s*:?\s*(.+?):(\d+)')
# Matches legacy: ### 问题 - [P0] category（来自：agent/RULE-ID）
LEGACY_SEV_RE = re.compile(r'\[(P[0-3])\]')
RULE_ID_RE = re.compile(r'\b([A-Z]+-\d+)\b')


def parse_findings_file(filepath: str, source_agent: str) -> list:
    """Parse a findings Markdown file into Finding objects."""
    try:
        text = Path(filepath).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []

    findings = []
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── v7 format: ### [P0] SAFE-003 · src/auth.go:42-47 ──
        m = FINDING_HEADER_RE.match(line)
        if m:
            severity = m.group(1)
            rule_id = m.group(2)
            fpath = m.group(3).strip()
            line_start = int(m.group(4))
            line_end = int(m.group(5)) if m.group(5) else line_start

            body_lines = []
            confidence = 1.0
            needs_clarification = None
            i += 1

            while i < len(lines) and not lines[i].startswith('### '):
                bl = lines[i]
                cm = CONFIDENCE_RE.match(bl)
                if cm:
                    try:
                        confidence = float(cm.group(1))
                    except ValueError:
                        pass
                    i += 1
                    continue
                nm = NC_RE.match(bl)
                if nm:
                    val = nm.group(1).strip()
                    needs_clarification = None if val.lower() in ('null', 'none', '') else val
                    i += 1
                    continue
                # Skip metadata lines that to_markdown() re-generates
                if SOURCE_RE.match(bl) or REDLINE_RE.match(bl):
                    i += 1
                    continue
                body_lines.append(bl)
                i += 1

            findings.append(Finding(
                rule_id=rule_id, severity=severity,
                filepath=fpath, line_start=line_start, line_end=line_end,
                body='\n'.join(body_lines), confidence=confidence,
                needs_clarification=needs_clarification, source_agent=source_agent,
            ))
            continue

        # ── Legacy format: ### 问题 - [P0] ... ──
        if line.startswith('### ') and '[P' in line:
            sev_m = LEGACY_SEV_RE.search(line)
            if sev_m:
                severity = sev_m.group(1)
                rule_ids = RULE_ID_RE.findall(line)
                rule_id = rule_ids[0] if rule_ids else 'MISC-000'
                fpath = ''
                line_start = 0
                line_end = 0
                body_lines = [line]
                confidence = 0.9
                needs_clarification = None
                i += 1

                while i < len(lines) and not (lines[i].startswith('### ') and '[P' in lines[i]):
                    bl = lines[i]
                    lm = LOCATION_RE.match(bl)
                    if lm and not fpath:
                        fpath = lm.group(1).strip()
                        line_start = int(lm.group(2))
                        line_end = line_start
                    cm = CONFIDENCE_RE.match(bl)
                    if cm:
                        try:
                            confidence = float(cm.group(1))
                        except ValueError:
                            pass
                    nm = NC_RE.match(bl)
                    if nm:
                        val = nm.group(1).strip()
                        needs_clarification = None if val.lower() in ('null', 'none', '') else val
                    body_lines.append(bl)
                    i += 1

                if fpath:
                    findings.append(Finding(
                        rule_id=rule_id, severity=severity,
                        filepath=fpath, line_start=line_start, line_end=line_end,
                        body='\n'.join(body_lines), confidence=confidence,
                        needs_clarification=needs_clarification, source_agent=source_agent,
                    ))
                continue

        i += 1

    return findings


# ── Deduplication ───────────────────────────────────────────────────────────────

def deduplicate(findings: list) -> list:
    """
    Merge findings at the same/adjacent location with the same rule category.
    Keeps highest severity and confidence of merged group.
    """
    if not findings:
        return []

    # Group by (filepath, category)
    groups: dict = {}
    for f in findings:
        key = (f.filepath, f.category)
        groups.setdefault(key, []).append(f)

    deduped = []
    for group in groups.values():
        group.sort(key=lambda f: f.line_start)

        merged = []
        for f in group:
            if merged and f.filepath == merged[-1].filepath and \
               abs(f.line_start - merged[-1].line_start) <= ADJACENT_LINE_THRESHOLD:
                prev = merged[-1]
                # Keep highest severity
                if SEVERITY_ORDER.get(f.severity, 99) < SEVERITY_ORDER.get(prev.severity, 99):
                    prev.severity = f.severity
                # Keep highest confidence
                if f.confidence > prev.confidence:
                    prev.confidence = f.confidence
                # Merge body if distinct
                if f.body.strip() and f.body.strip() not in prev.body:
                    prev.body += f'\n\n---\n{f.body}'
            else:
                merged.append(f)

        deduped.extend(merged)

    return deduped


# ── Redline detection ───────────────────────────────────────────────────────────

def load_redline_rule_ids(redlines_file: str) -> set:
    """Extract rule IDs from a project redlines/rules file."""
    try:
        text = Path(redlines_file).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return set()
    return set(RULE_ID_RE.findall(text))


def apply_redlines(findings: list, redline_ids: set) -> None:
    """Mark redline findings and enforce severity >= P1."""
    for f in findings:
        if f.rule_id in redline_ids:
            f.is_redline = True
            if SEVERITY_ORDER.get(f.severity, 99) > SEVERITY_ORDER['P1']:
                f.severity = 'P1'


# ── review:ignore filtering ─────────────────────────────────────────────────────

def _parse_ignore_flags(flags_str: str) -> list:
    """
    Parse review:ignore flags.
    Format: "category" or "category:filepath:line" (comma-separated).
    Returns list of (category, filepath_or_empty, line_or_0).
    """
    result = []
    for flag in flags_str.split(','):
        flag = flag.strip()
        if not flag:
            continue
        parts = flag.split(':', 2)
        category = parts[0].lower()
        filepath = parts[1] if len(parts) > 1 else ''
        try:
            line = int(parts[2]) if len(parts) > 2 else 0
        except ValueError:
            line = 0
        result.append((category, filepath, line))
    return result


def _category_matches_rule(category: str, rule_id: str) -> bool:
    prefixes = CATEGORY_PREFIX_MAP.get(category, [])
    return any(rule_id.startswith(p) for p in prefixes)


def apply_review_ignore(findings: list, ignore_flags_str: str) -> list:
    """Filter findings suppressed by review:ignore annotations."""
    if not ignore_flags_str:
        return findings
    ignore_rules = _parse_ignore_flags(ignore_flags_str)
    if not ignore_rules:
        return findings

    kept = []
    for f in findings:
        suppressed = False
        for category, filepath, line in ignore_rules:
            if not _category_matches_rule(category, f.rule_id):
                continue
            if filepath:
                # Location-specific suppression
                if f.filepath == filepath or f.filepath.endswith('/' + filepath):
                    if line == 0 or abs(f.line_start - line) <= ADJACENT_LINE_THRESHOLD:
                        suppressed = True
                        break
            else:
                # Global category suppression
                suppressed = True
                break
        if not suppressed:
            kept.append(f)
    return kept


# ── Confidence filtering ────────────────────────────────────────────────────────

def apply_confidence_filter(findings: list, min_confidence: float = MIN_CONFIDENCE) -> list:
    """Drop findings below confidence threshold; redline findings are exempt."""
    return [f for f in findings if f.is_redline or f.confidence >= min_confidence]


def apply_fuzzy_cap(
    findings: list,
    max_fuzzy: int = MAX_FUZZY_PER_CATEGORY,
    fuzzy_threshold: float = FUZZY_THRESHOLD,
) -> list:
    """
    Per category, keep at most max_fuzzy findings with confidence < fuzzy_threshold.
    Redline and high-confidence findings are always kept.
    """
    category_fuzzy_count: dict = {}
    kept = []

    for f in findings:
        if f.is_redline or f.confidence >= fuzzy_threshold:
            kept.append(f)
            continue
        cat = f.category
        count = category_fuzzy_count.get(cat, 0)
        if count < max_fuzzy:
            category_fuzzy_count[cat] = count + 1
            kept.append(f)
        # else: drop — excess low-confidence finding for this category

    return kept


def auto_verify(findings: list, rule_hits: dict) -> None:
    """
    Deterministic verifier: adjust confidence based on Tier2 rule hit correlation.
    Only affects P0/P1 findings with confidence < 0.92.
    Mutates findings in-place.
    """
    CONFIDENCE_CEILING = 0.92
    DOWNGRADE_AMOUNT = 0.10
    SAFE_DATA_PREFIXES = ('SAFE-', 'DATA-')

    # Build lookup: {(rule_id, filepath): [line_numbers]}
    hit_index: dict[tuple, list[int]] = {}
    for hit in rule_hits.get('hits', []):
        key = (hit.get('rule_id', ''), hit.get('file', ''))
        hit_index.setdefault(key, []).append(hit.get('line', 0))

    for f in findings:
        if f.severity not in ('P0', 'P1'):
            continue
        if f.confidence >= CONFIDENCE_CEILING:
            continue

        key = (f.rule_id, f.filepath)
        matched_lines = hit_index.get(key, [])

        if matched_lines:
            if any(abs(f.line_start - ln) <= ADJACENT_LINE_THRESHOLD for ln in matched_lines):
                f.confidence = 1.0
        elif any(f.rule_id.startswith(p) for p in SAFE_DATA_PREFIXES):
            f.confidence = max(0.0, f.confidence - DOWNGRADE_AMOUNT)


# ── golangci-lint JSON conversion ───────────────────────────────────────────────

def convert_lint_json(lint_json_file: str) -> list:
    """Convert golangci-lint JSON output to Finding objects."""
    try:
        data = json.loads(Path(lint_json_file).read_text(encoding='utf-8', errors='replace'))
    except (OSError, json.JSONDecodeError) as e:
        print(f'ERROR: could not parse lint JSON: {e}', file=sys.stderr)
        return []

    issues = data.get('Issues') or []
    findings = []

    for issue in issues:
        linter = issue.get('FromLinter', 'unknown')
        text = issue.get('Text', '')
        pos = issue.get('Pos', {})
        filepath = pos.get('Filename', '')
        line = pos.get('Line', 0)

        rule_id, severity = LINTER_SEVERITY_MAP.get(linter, DEFAULT_LINT_RULE)

        # gosec severity uses its own field
        if linter == 'gosec':
            sev = issue.get('Severity', 'medium').lower()
            severity = 'P0' if sev == 'high' else ('P1' if sev == 'medium' else 'P2')

        body = f'**工具**: {linter}\n**描述**: {text}'
        if issue.get('SourceLines'):
            src = '\n'.join(issue['SourceLines'])
            body += f'\n\n```go\n{src}\n```'

        findings.append(Finding(
            rule_id=rule_id, severity=severity,
            filepath=filepath, line_start=line,
            body=body, confidence=1.0,
            source_agent='golangci-lint',
        ))

    return findings


def write_findings_md(findings: list, output_file: str) -> None:
    """Write findings in the standard findings-*.md format."""
    lines = ['# Lint Findings\n']
    for f in findings:
        lines.append(f.to_markdown())
        lines.append('')
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text('\n'.join(lines), encoding='utf-8')


# ── Report generation ───────────────────────────────────────────────────────────

def build_review_assumptions(classification: dict, context_meta: dict) -> str:
    """Generate deterministic review assumptions section from metadata."""
    tier = classification.get('tier', 'UNKNOWN')
    trigger = classification.get('trigger_reason', '')
    rules_source = classification.get('rules_source', 'built_in')
    agents = classification.get('agent_roster', [])
    estimated = context_meta.get('estimated_tokens', 0)
    limit = context_meta.get('token_limit', 16000)
    truncated = context_meta.get('truncated_sections', [])

    lines = [
        '## 审查说明\n',
        f'- **处理档位**: {tier}（{trigger}）',
        f'- **规则来源**: {rules_source}',
        f'- **运行 Agents**: {", ".join(agents) if agents else "（无）"}',
        f'- **Token 估算**: {estimated} / {limit}',
        f'- **截断节**: {", ".join(truncated) if truncated else "无"}',
        '',
    ]
    return '\n'.join(lines)


def generate_report(
    findings: list,
    total_raw: int,
    total_after_dedup: int,
    total_filtered: int,
    max_output: int,
    output_file: str,
    classification: dict | None = None,
    context_meta: dict | None = None,
) -> None:
    """Generate final Markdown review report with optional Appendix."""
    displayed = findings[:max_output]
    appendix_findings = findings[max_output:]

    counts = {'P0': 0, 'P1': 0, 'P2': 0, 'P3': 0}
    for f in displayed:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    lines = ['# Go 代码审查报告\n']

    # Review assumptions (replaces Coordinator agent)
    if classification and context_meta:
        lines.append(build_review_assumptions(classification, context_meta))

    # Summary table
    lines.append('## 审查摘要\n')
    lines.append('| 指标 | 数量 |')
    lines.append('|------|------|')
    lines.append(f'| P0（必须修复） | {counts["P0"]} 个 |')
    lines.append(f'| P1（强烈建议） | {counts["P1"]} 个 |')
    lines.append(f'| P2（建议优化） | {counts["P2"]} 个 |')
    if counts.get('P3'):
        lines.append(f'| P3（参考信息） | {counts["P3"]} 个 |')
    lines.append(f'| 合计（展示） | {len(displayed)} 个 |')
    lines.append(f'| 合计（过滤后） | {len(findings)} 个 |')
    lines.append('')

    if total_raw > 0:
        lines.append(
            f'> 共检出 {total_raw} 条 → 去重后 {total_after_dedup} 条 '
            f'→ 过滤后 {total_filtered} 条\n'
        )

    # Findings sections by severity
    for sev in ['P0', 'P1', 'P2', 'P3']:
        sev_findings = [f for f in displayed if f.severity == sev]
        if not sev_findings:
            continue
        label = SEVERITY_LABELS.get(sev, sev)
        lines.append(f'## {label}\n')
        for f in sev_findings:
            lines.append(f.to_markdown())
            lines.append('')

    # Truncation notice
    if appendix_findings:
        n_extra = len(appendix_findings)
        lines.append(
            f'\n> 另有 {n_extra} 条问题因数量限制未显示，完整结果见 Appendix。\n'
        )

    # Appendix
    if appendix_findings:
        lines.append('---\n')
        lines.append('## Appendix\n')
        lines.append('*以下 findings 超出输出限制，仅供参考。*\n')
        for f in appendix_findings:
            lines.append(f.to_markdown())
            lines.append('')

    content = '\n'.join(lines)
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(output_file).write_text(content, encoding='utf-8')


# ── Main pipeline ───────────────────────────────────────────────────────────────

def aggregate(
    findings_dir: str,
    redlines_file: str | None,
    review_ignore_flags: str,
    max_output: int,
    output_file: str,
    classification_file: str | None = None,
    context_meta_file: str | None = None,
    rule_hits_file: str | None = None,
) -> None:
    """Full aggregation pipeline."""
    findings_dir_path = Path(findings_dir)
    if not findings_dir_path.exists():
        print(f'ERROR: findings_dir does not exist: {findings_dir}', file=sys.stderr)
        sys.exit(1)

    # Step 1: Parse all findings-*.md files
    all_raw: list = []
    for md_file in sorted(findings_dir_path.glob('findings-*.md')):
        agent_name = md_file.stem[len('findings-'):]
        parsed = parse_findings_file(str(md_file), agent_name)
        all_raw.extend(parsed)

    total_raw = len(all_raw)

    if not all_raw:
        print(f'INFO: no findings parsed from {findings_dir}', file=sys.stderr)
        generate_report([], 0, 0, 0, max_output, output_file)
        print(f'审查完成：未发现问题。报告：{output_file}')
        return

    # Step 2: Deduplicate
    findings = deduplicate(all_raw)
    total_after_dedup = len(findings)

    # Step 3: Redline priority
    if redlines_file:
        redline_ids = load_redline_rule_ids(redlines_file)
        apply_redlines(findings, redline_ids)

    # Step 2.5: Auto-verify (replaces Verifier agent)
    if rule_hits_file and Path(rule_hits_file).exists():
        try:
            rule_hits = json.loads(Path(rule_hits_file).read_text())
            auto_verify(findings, rule_hits)
        except json.JSONDecodeError:
            print(f'WARN: failed to parse {rule_hits_file}', file=sys.stderr)

    # Step 4: review:ignore filter
    findings = apply_review_ignore(findings, review_ignore_flags)

    # Step 5: Confidence filter
    findings = apply_confidence_filter(findings)

    # Step 6: Fuzzy cap
    findings = apply_fuzzy_cap(findings)

    total_filtered = len(findings)

    # Step 7: Sort
    findings.sort(key=lambda f: f.sort_key)

    # Step 8: Generate report (truncates to max_output, rest → Appendix)
    classification = None
    context_meta = None
    if classification_file and Path(classification_file).exists():
        try:
            classification = json.loads(Path(classification_file).read_text())
        except json.JSONDecodeError:
            print(f'WARN: failed to parse {classification_file}', file=sys.stderr)
    if context_meta_file and Path(context_meta_file).exists():
        try:
            context_meta = json.loads(Path(context_meta_file).read_text())
        except json.JSONDecodeError:
            print(f'WARN: failed to parse {context_meta_file}', file=sys.stderr)
    generate_report(
        findings, total_raw, total_after_dedup, total_filtered,
        max_output, output_file,
        classification=classification,
        context_meta=context_meta,
    )

    # Terminal summary
    displayed = findings[:max_output]
    counts = {'P0': 0, 'P1': 0, 'P2': 0, 'P3': 0}
    for f in displayed:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    print(f'审查完成：{total_raw} 条原始 → 去重 {total_after_dedup} → 过滤 {total_filtered} 条')
    print(f'P0: {counts["P0"]}  P1: {counts["P1"]}  P2: {counts["P2"]}  P3: {counts.get("P3", 0)}')
    if len(findings) > max_output:
        extra = len(findings) - max_output
        print(f'（另有 {extra} 条问题因数量限制未显示，完整报告见 {output_file}）')
    print(f'报告：{output_file}')


# ── CLI ──────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Aggregate Go code review findings')

    # Standard aggregation mode
    parser.add_argument('--findings-dir', default='',
                        help='Directory containing findings-*.md files')
    parser.add_argument('--redlines-file', default='',
                        help='Path to project redlines file')
    parser.add_argument('--review-ignore-flags', default='',
                        help='Comma-separated review:ignore flags (category[:file:line])')
    parser.add_argument('--max-output', type=int, default=15,
                        help='Max findings to display (default: 15)')
    parser.add_argument('--output', required=True,
                        help='Output file path for the report')

    # Lint JSON conversion mode
    parser.add_argument('--lint-json', default='',
                        help='golangci-lint JSON output to convert (conversion mode)')
    parser.add_argument('--classification-file', default='',
                        help='Path to classification.json (enables review assumptions section)')
    parser.add_argument('--context-meta-file', default='',
                        help='Path to context-meta.json (enables review assumptions section)')
    parser.add_argument('--rule-hits-file', default='',
                        help='Path to rule-hits.json from scan-rules.sh (enables auto-verify)')

    args = parser.parse_args()

    # Lint JSON conversion mode
    if args.lint_json:
        findings = convert_lint_json(args.lint_json)
        write_findings_md(findings, args.output)
        print(f'转换完成：{len(findings)} 条 lint 发现写入 {args.output}', file=sys.stderr)
        return

    # Standard aggregation mode
    if not args.findings_dir:
        print('ERROR: --findings-dir is required unless --lint-json is used', file=sys.stderr)
        sys.exit(1)

    aggregate(
        findings_dir=args.findings_dir,
        redlines_file=args.redlines_file or None,
        review_ignore_flags=args.review_ignore_flags,
        max_output=args.max_output,
        output_file=args.output,
        classification_file=args.classification_file or None,
        context_meta_file=args.context_meta_file or None,
        rule_hits_file=args.rule_hits_file or None,
    )


if __name__ == '__main__':
    main()
