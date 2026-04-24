import importlib.util
from pathlib import Path

# Load aggregate-findings.py via importlib (hyphen in filename prevents normal import)
spec = importlib.util.spec_from_file_location(
    "aggregate_findings",
    Path(__file__).parents[2] / "languages/go/tools/aggregate-findings.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

Finding = mod.Finding
SEVERITY_ORDER = mod.SEVERITY_ORDER


def test_finding_sort_key():
    f = Finding("SAFE-001", "P0", "main.go", 10)
    assert f.sort_key[0] == 0  # P0 → 0


def test_severity_order_complete():
    assert set(SEVERITY_ORDER.keys()) == {"P0", "P1", "P2", "P3"}


def test_build_review_assumptions_full_tier():
    classification = {
        "tier": "FULL",
        "trigger_reason": "diff_lines=500",
        "rules_source": "built_in",
        "agent_roster": ["safety", "data", "quality"],
    }
    context_meta = {
        "estimated_tokens": 12000,
        "token_limit": 16000,
        "truncated_sections": [],
    }
    result = mod.build_review_assumptions(classification, context_meta)
    assert "FULL" in result
    assert "safety, data, quality" in result
    assert "12000" in result
    assert "截断节：无" in result


def test_build_review_assumptions_with_truncation():
    classification = {
        "tier": "LITE",
        "trigger_reason": "diff_lines=100",
        "rules_source": "project_rules",
        "agent_roster": ["safety"],
    }
    context_meta = {
        "estimated_tokens": 14000,
        "token_limit": 16000,
        "truncated_sections": ["change_set"],
    }
    result = mod.build_review_assumptions(classification, context_meta)
    assert "change_set" in result
