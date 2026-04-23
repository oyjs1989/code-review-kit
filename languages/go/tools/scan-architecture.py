#!/usr/bin/env python3
"""
scan-architecture.py — Go Code Review Skill v7.0.0
Architecture pre-scan for Full-tier reviews.
Extracts module structure, layer hierarchy, interfaces, and high-risk modules.

Usage:
  python3 scan-architecture.py --files "src/auth/login.go src/service/order.go" [--gomod go.mod]
"""

import argparse
import json
import re
import sys
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────────────

SENSITIVE_PATH_RE = re.compile(r'(auth|crypto|payment|permission|admin)/')

# Layer detection patterns: directory name → layer label
LAYER_PATTERNS = [
    (re.compile(r'handler[s]?$', re.I), 'handler'),
    (re.compile(r'controller[s]?$', re.I), 'handler'),
    (re.compile(r'api$', re.I), 'handler'),
    (re.compile(r'router[s]?$', re.I), 'handler'),
    (re.compile(r'service[s]?$', re.I), 'service'),
    (re.compile(r'svc$', re.I), 'service'),
    (re.compile(r'biz$', re.I), 'service'),
    (re.compile(r'usecase[s]?$', re.I), 'service'),
    (re.compile(r'domain[s]?$', re.I), 'service'),
    (re.compile(r'repository$', re.I), 'repository'),
    (re.compile(r'repo[s]?$', re.I), 'repository'),
    (re.compile(r'dal$', re.I), 'repository'),
    (re.compile(r'dao$', re.I), 'repository'),
    (re.compile(r'store[s]?$', re.I), 'repository'),
    (re.compile(r'model[s]?$', re.I), 'model'),
    (re.compile(r'entity$', re.I), 'model'),
    (re.compile(r'pkg$', re.I), 'package'),
    (re.compile(r'util[s]?$', re.I), 'util'),
    (re.compile(r'helper[s]?$', re.I), 'util'),
    (re.compile(r'middleware[s]?$', re.I), 'middleware'),
]


def _detect_layer(directory: str) -> str | None:
    """Detect architectural layer from directory name."""
    parts = Path(directory).parts
    for part in reversed(parts):
        for pattern, layer in LAYER_PATTERNS:
            if pattern.match(part):
                return layer
    return None


# ── Go module parsing ───────────────────────────────────────────────────────────

def parse_gomod(gomod_path: str) -> dict:
    """Extract module name and key dependencies from go.mod."""
    result = {'module': '', 'dependencies': []}
    try:
        text = Path(gomod_path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return result

    for line in text.splitlines():
        line = line.strip()
        if line.startswith('module '):
            result['module'] = line.split()[1]
        elif line.startswith('require') or (result.get('_in_require') and line.startswith(')')):
            pass
        elif '\t' in line and '//' not in line.split('\t')[0]:
            # Dependency line inside require block
            parts = line.split()
            if parts:
                result['dependencies'].append(parts[0])

    return result


# ── Go source file analysis ─────────────────────────────────────────────────────

def _extract_package(source: str) -> str:
    """Extract package name from Go source."""
    m = re.search(r'^package\s+(\w+)', source, re.MULTILINE)
    return m.group(1) if m else ''


def _extract_interfaces(source: str, filepath: str) -> list[str]:
    """Extract interface type declarations as short signatures."""
    interfaces = []
    # Match: type Foo interface { ... }
    iface_re = re.compile(r'^type\s+(\w+)\s+interface\s*\{', re.MULTILINE)
    for m in iface_re.finditer(source):
        name = m.group(1)
        # Try to extract method names from the interface body
        start = m.end()
        # Find the closing brace — scan forward with brace counting
        depth = 1
        pos = start
        body_chars = []
        while pos < len(source) and depth > 0:
            c = source[pos]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    break
            body_chars.append(c)
            pos += 1

        body = ''.join(body_chars)
        # Extract method signatures (lines with parentheses)
        methods = []
        for line in body.splitlines():
            line = line.strip()
            if '(' in line and not line.startswith('//'):
                # Trim to just method name + params (first 60 chars)
                methods.append(line[:60])

        if methods:
            sig = f'type {name} interface {{ {"; ".join(methods[:3])} }}'
        else:
            sig = f'type {name} interface {{ ... }}'
        interfaces.append(sig)

    return interfaces


def analyze_file(filepath: str) -> dict:
    """Analyze a single Go source file."""
    result = {
        'filepath': filepath,
        'package': '',
        'directory': str(Path(filepath).parent),
        'interfaces': [],
        'error': None,
    }
    try:
        source = Path(filepath).read_text(encoding='utf-8', errors='replace')
        result['package'] = _extract_package(source)
        result['interfaces'] = _extract_interfaces(source, filepath)
    except OSError as e:
        result['error'] = str(e)
    return result


# ── Architecture context generation ────────────────────────────────────────────

def _build_architecture_context(
    module_map: dict[str, list[str]],
    layer_map: dict[str, str],
    high_risk_modules: list[str],
    gomod_module: str,
) -> str:
    """Generate a natural-language architecture_context description."""
    parts = []

    # Describe layer hierarchy
    layers_present: dict[str, list[str]] = {}
    for directory, layer in layer_map.items():
        layers_present.setdefault(layer, []).append(directory)

    layer_order = ['handler', 'service', 'repository', 'model', 'middleware', 'util', 'package']
    present_ordered = [l for l in layer_order if l in layers_present]
    unrecognized = [l for l in layers_present if l not in layer_order]
    present_ordered.extend(unrecognized)

    if len(present_ordered) >= 2:
        parts.append(f'分层架构：{" → ".join(present_ordered)}')
    elif present_ordered:
        parts.append(f'检测到层：{present_ordered[0]}')

    # Describe modules
    if module_map:
        module_names = list(module_map.keys())
        parts.append(f'本次变更涉及模块：{", ".join(module_names)}')

    # High-risk modules
    if high_risk_modules:
        parts.append(f'高风险模块（需重点审查）：{", ".join(high_risk_modules)}')

    # Project module name
    if gomod_module:
        parts.append(f'Go 模块：{gomod_module}')

    return '；'.join(parts) if parts else '未识别到明显分层结构'


# ── Main ────────────────────────────────────────────────────────────────────────

def scan(files: list[str], gomod_path: str) -> dict:
    """Perform architecture pre-scan on the given files."""
    gomod_info = parse_gomod(gomod_path) if Path(gomod_path).exists() else {'module': '', 'dependencies': []}

    module_map: dict[str, list[str]] = {}   # directory → [filenames]
    layer_map: dict[str, str] = {}           # directory → layer
    all_interfaces: list[str] = []
    high_risk_modules: list[str] = []
    skipped_files: list[str] = []

    for filepath in files:
        if not filepath.endswith('.go'):
            continue
        if not Path(filepath).exists():
            skipped_files.append(filepath)
            continue

        info = analyze_file(filepath)
        if info['error']:
            skipped_files.append(filepath)
            continue

        directory = info['directory']
        filename = Path(filepath).name

        # Build module map
        module_map.setdefault(directory, [])
        if filename not in module_map[directory]:
            module_map[directory].append(filename)

        # Detect layer
        if directory not in layer_map:
            layer = _detect_layer(directory)
            if layer:
                layer_map[directory] = layer

        # Collect interfaces
        all_interfaces.extend(info['interfaces'])

        # High-risk detection
        if SENSITIVE_PATH_RE.search(filepath):
            dir_basename = Path(directory).name
            if dir_basename not in high_risk_modules:
                high_risk_modules.append(dir_basename)

    architecture_context = _build_architecture_context(
        module_map, layer_map, high_risk_modules, gomod_info['module']
    )

    return {
        'module_map': module_map,
        'high_risk_modules': high_risk_modules,
        'key_interfaces': all_interfaces[:20],  # cap to 20
        'architecture_context': architecture_context,
        'layer_map': layer_map,
        'skipped_files': skipped_files,
        'go_module': gomod_info['module'],
    }


def main():
    parser = argparse.ArgumentParser(description='Architecture pre-scan for Go code review')
    parser.add_argument('--files', required=True,
                        help='Space-separated list of changed Go files')
    parser.add_argument('--gomod', default='go.mod',
                        help='Path to go.mod file (default: go.mod)')
    args = parser.parse_args()

    files = [f for f in args.files.split() if f]
    result = scan(files, args.gomod)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
